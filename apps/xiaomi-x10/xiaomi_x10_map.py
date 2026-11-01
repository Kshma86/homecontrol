import ast
import json
import base64
from collections import Counter
import hashlib
import zlib
import sys
import re
from pathlib import Path

import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from PIL import Image, ImageDraw

import config
from x10_runtime import run_miio

sys.path.append(str(Path(__file__).parent / "Xiaomi-cloud-tokens-extractor"))

from token_extractor import PasswordXiaomiCloudConnector


ROBOT_IP = config.ROBOT_IP
ROBOT_TOKEN = config.ROBOT_TOKEN
MIIOCLI = str(config.MIIOCLI)


class XiaomiX10MapClient:
    def __init__(self, country="de", output_dir="x10_maps"):
        self.country = country
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.connector = PasswordXiaomiCloudConnector()
        self.base_url = None

    def login(self):
        if not self.connector.login():
            raise RuntimeError("Xiaomi Cloud login failed")

        self.base_url = self.connector.get_api_url(self.country)

        auth = {
            "country": self.country,
            "userId": self.connector.userId,
            "ssecurity": self.connector._ssecurity,
            "serviceToken": self.connector._serviceToken,
        }

        auth_path = self.output_dir / "xiaomi_cloud_auth.json"
        auth_path.write_text(json.dumps(auth, indent=2), encoding="utf-8")
        auth_path.chmod(0o600)

        print(f"Auth saved: {auth_path}")

    def load_auth(self, auth_file):
        auth_file = Path(auth_file)
        auth = json.loads(auth_file.read_text(encoding="utf-8"))

        self.country = auth.get("country", self.country)
        self.connector.userId = auth["userId"]
        self.connector._ssecurity = auth["ssecurity"]
        self.connector._serviceToken = auth["serviceToken"]
        self.base_url = self.connector.get_api_url(self.country)

        print(f"Loaded auth from {auth_file}")

    def get_robot_property(self, siid, piid):
        output = run_miio(["get_property_by", str(siid), str(piid)])

        lines = [line.strip() for line in output.splitlines()]
        data_line = next((line for line in lines if line.startswith("[{")), None)

        if not data_line:
            raise RuntimeError("Could not parse X10 MIIO property output")

        data = ast.literal_eval(data_line)

        if not data or data[0].get("code") != 0:
            raise RuntimeError(f"Property read failed: {data}")

        return data[0].get("value")

    def get_current_map_object_from_robot(self):
        value = self.get_robot_property(6, 8)
        parsed = json.loads(value)

        object_name = parsed.get("object_name")
        md5 = parsed.get("md5")

        if not object_name:
            raise RuntimeError(f"No object_name in 6/8: {value}")

        return {
            "object_name": object_name,
            "md5": md5,
            "siid": 6,
            "piid": 8,
        }

    def get_file_url(self, object_name):
        url = self.base_url + "/v2/home/get_interim_file_url"
        params = {
            "data": json.dumps(
                {"obj_name": object_name},
                separators=(",", ":")
            )
        }

        res = self.connector.execute_api_call_encrypted(url, params)

        if not res or res.get("code") != 0:
            raise RuntimeError(f"Failed to get file URL: {res}")

        return res["result"]["url"]

    def download_object(self, object_name, filename):
        content = self.download_object_bytes(object_name)

        path = self.output_dir / filename
        path.write_bytes(content)
        return path

    def download_object_bytes(self, object_name):
        response = requests.get(self.get_file_url(object_name), timeout=30)
        response.raise_for_status()
        return response.content

    def decode_live_map(self, raw_map, key=None, iv=None):
        if isinstance(raw_map, bytes):
            raw_map = raw_map.decode("utf-8")
        if "," in raw_map and not key:
            raw_map, key = raw_map.split(",", 1)
        encrypted = base64.decodebytes(
            raw_map.replace("_", "/").replace("-", "+").encode("utf-8")
        )
        if key:
            aes_key = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32].encode("utf-8")
            decryptor = Cipher(
                algorithms.AES(aes_key),
                modes.CBC((iv or "").encode("utf-8")),
                backend=default_backend(),
            ).decryptor()
            encrypted = decryptor.update(encrypted) + decryptor.finalize()
        raw = zlib.decompress(encrypted)
        if len(raw) < 27:
            raise RuntimeError("Live map frame has an invalid header")
        return raw, self._header_from_raw(raw)

    def _decode_raw_map(self, raw_map):
        return zlib.decompress(
            base64.decodebytes(
                raw_map.replace("_", "/").replace("-", "+").encode()
            )
        )

    def _safe_filename(self, name):
        name = name.strip().replace(" ", "_")
        name = re.sub(r"[^0-9A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű_.-]", "_", name)
        return name

    def _header_from_raw(self, raw):
        def i8(off):
            return int.from_bytes(raw[off:off + 1], "big", signed=True)

        def i16(off):
            return int.from_bytes(raw[off:off + 2], "little", signed=True)

        return {
            "map_id": i16(0),
            "frame_id": i16(2),
            "frame_type": i8(4),
            "robot_x": i16(5),
            "robot_y": i16(7),
            "robot_angle": i16(9),
            "dock_x": i16(11),
            "dock_y": i16(13),
            "dock_angle": i16(15),
            "grid_size": i16(17),
            "width": i16(19),
            "height": i16(21),
            "left": i16(23),
            "top": i16(25),
            "raw_size": len(raw),
        }

    def _extract_meta_json(self, raw, width, height):
        image_size = 27 + width * height
        meta_raw = raw[image_size:]

        if not meta_raw:
            return {}

        try:
            return json.loads(meta_raw.decode("utf-8"))
        except Exception:
            return {}

    def _extract_rooms(self, meta, pixels=None, width=None, height=None):
        rooms = []

        seg_inf = meta.get("seg_inf")
        if not isinstance(seg_inf, dict):
            return rooms

        for seg_id, seg in seg_inf.items():
            if not isinstance(seg, dict):
                continue

            room = {
                "segment_id": int(seg_id) if str(seg_id).isdigit() else seg_id,
                "name": seg.get("name"),
                "type": seg.get("type"),
                "roomID": seg.get("roomID"),
                "neighbors": seg.get("nei_id"),
            }
            if pixels is not None and width and height and str(seg_id).isdigit():
                target = int(seg_id)
                coords = [
                    (index % width, index // width)
                    for index, pixel in enumerate(pixels)
                    if not (pixel >> 7) and (pixel & 0x3F) == target
                ]
                if coords:
                    room["center_px"] = {
                        "x": round(sum(item[0] for item in coords) / len(coords), 2),
                        "y": round(sum(item[1] for item in coords) / len(coords), 2),
                    }
            rooms.append(room)

        return rooms

    def render_single_map_to_png(self, raw, png_path, meta=None):
        header = self._header_from_raw(raw)
        width = header["width"]
        height = header["height"]

        pixels = raw[27:27 + width * height]

        palette = [
            (185, 136, 210), (113, 164, 215), (111, 190, 194),
            (218, 154, 112), (202, 181, 91), (143, 193, 143),
            (189, 137, 155), (125, 173, 207),
        ]
        colors = []
        for pixel in pixels:
            segment_id = pixel & 0x3F
            if pixel >> 7:
                colors.append((43, 48, 61, 255))
            elif segment_id:
                color = palette[(segment_id - 1) % len(palette)]
                colors.append((*color, 255))
            else:
                colors.append((13, 16, 23, 255))

        img = Image.new("RGBA", (width, height))
        img.putdata(colors)
        img = img.resize((width * 4, height * 4), Image.Resampling.NEAREST)

        vw = (meta or {}).get("vw") or {}
        draw = ImageDraw.Draw(img, "RGBA")

        def point(x, y):
            return (
                round((x - header["left"]) / header["grid_size"] * 4),
                round((y - header["top"]) / header["grid_size"] * 4),
            )

        for zone in vw.get("mop", []):
            if len(zone) >= 4:
                p1, p2 = point(zone[0], zone[1]), point(zone[2], zone[3])
                box = (min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1]))
                draw.rectangle(box, fill=(147, 51, 234, 65), outline=(192, 132, 252, 235), width=3)
        for zone in vw.get("rect", []):
            if len(zone) >= 4:
                p1, p2 = point(zone[0], zone[1]), point(zone[2], zone[3])
                box = (min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1]))
                draw.rectangle(box, fill=(239, 68, 68, 65), outline=(248, 113, 113, 245), width=3)
        for wall in vw.get("line", []):
            if len(wall) >= 4:
                draw.line((point(wall[0], wall[1]), point(wall[2], wall[3])), fill=(248, 64, 64, 255), width=4)

        img.save(png_path)
        return png_path

    """
    LEGACY LIVE MAP RENDERER (disabled 2026-09-07)

    Kept unchanged as an immediate fallback while the standardized renderer
    below is being validated on every physical floor.

    def render_live_overlay(self, base_png, raw, output_path, target_header):
        live_header = self._header_from_raw(raw)
        width, height = live_header["width"], live_header["height"]
        pixels = raw[27:27 + width * height]
        meta = self._extract_meta_json(raw, width, height)
        image = Image.open(base_png).convert("RGBA")
        draw = ImageDraw.Draw(image, "RGBA")
        scale = 4
        origin_distance = max(
            abs(live_header["left"] - target_header["left"]),
            abs(live_header["top"] - target_header["top"]),
        )
        flip_live = origin_distance > (target_header["grid_size"] * 20)

        # Live frames use a cropped, moving canvas. Match their occupied cells
        # to the saved map so paths remain aligned when that crop changes.
        base_cells = set()
        base_pixels = image.load()
        target_width = int(target_header["width"])
        target_height = int(target_header["height"])
        for cell_y in range(target_height):
            for cell_x in range(target_width):
                if base_pixels[cell_x * scale + scale // 2, cell_y * scale + scale // 2][:3] != (13, 16, 23):
                    base_cells.add((cell_x, cell_y))
        live_cells = {
            (
                width - 1 - (index % width) if flip_live else index % width,
                height - 1 - (index // width) if flip_live else index // width,
            )
            for index, pixel in enumerate(pixels)
            if pixel != 0
        }
        alignment_key = f'{target_header.get("map_id", "default")}:{"flip" if flip_live else "native"}'
        alignment_cache = getattr(self, "_live_alignment_offsets", {})
        fixed_offsets = {
            # Calibrated against the saved first-floor map.  Keeping the
            # effective offset fixed prevents first-frame/restart drift.
            "197:native": (129, 250),
            # Calibrated from the complete second-floor frame. The live canvas
            # grows upward, so this intentionally anchors its far edge.
            "44:native": (169, 152),
        }
        cached_offset = fixed_offsets.get(alignment_key) or alignment_cache.get(alignment_key)
        alignment_dx = alignment_dy = 0
        if cached_offset is not None:
            alignment_dx = cached_offset[0] - (width - 1)
            alignment_dy = cached_offset[1] - (height - 1)
        elif base_cells and live_cells:
            base_sample = list(base_cells)[::max(1, len(base_cells) // 600)]
            live_sample = list(live_cells)[::max(1, len(live_cells) // 600)]
            offsets = Counter(
                (base_x - live_x, base_y - live_y)
                for base_x, base_y in base_sample
                for live_x, live_y in live_sample
            )
            alignment_dx, alignment_dy = offsets.most_common(1)[0][0]
            alignment_cache[alignment_key] = (
                width - 1 + alignment_dx,
                height - 1 + alignment_dy,
            )
            self._live_alignment_offsets = alignment_cache
        is_native_first_floor = str(target_header.get("map_id")) == "197" and not flip_live
        alignment_x_px = 8 if is_native_first_floor else 0
        alignment_y_px = -6 if is_native_first_floor else 0
        meta["alignment_dx_cells"] = alignment_dx
        meta["alignment_dy_cells"] = alignment_dy
        meta["alignment_x_px"] = alignment_x_px
        meta["alignment_y_px"] = alignment_y_px
        meta["flip_live"] = flip_live

        canvas_shift_x = canvas_shift_y = 0
        if str(target_header.get("map_id")) == "44" and live_cells:
            mapped_pixels = {}
            for index, pixel in enumerate(pixels):
                if not pixel:
                    continue
                source_x, source_y = index % width, index // width
                mapped_x = (width - 1 - source_x if flip_live else source_x) + alignment_dx
                mapped_y = (height - 1 - source_y if flip_live else source_y) + alignment_dy
                mapped_pixels[(mapped_x, mapped_y)] = pixel

            extension_caches = getattr(self, "_live_extension_cells", {})
            extension_cells = extension_caches.setdefault(alignment_key, {})
            for (mapped_x, mapped_y), pixel in mapped_pixels.items():
                if not (0 <= mapped_x < target_width and 0 <= mapped_y < target_height):
                    extension_cells[(mapped_x, mapped_y)] = pixel
            self._live_extension_cells = extension_caches

            mapped_cells = set(mapped_pixels) | set(extension_cells)
            min_x = min(0, min(cell_x for cell_x, _ in mapped_cells))
            min_y = min(0, min(cell_y for _, cell_y in mapped_cells))
            max_x = max(target_width - 1, max(cell_x for cell_x, _ in mapped_cells))
            max_y = max(target_height - 1, max(cell_y for _, cell_y in mapped_cells))
            canvas_shift_x = -min_x
            canvas_shift_y = -min_y
            canvas_width = max_x - min_x + 1
            canvas_height = max_y - min_y + 1
            if canvas_width != target_width or canvas_height != target_height:
                expanded = Image.new("RGBA", (canvas_width * scale, canvas_height * scale), (13, 16, 23, 255))
                image = expanded
                draw = ImageDraw.Draw(image, "RGBA")

                palette = [
                    (185, 136, 210), (113, 164, 215), (111, 190, 194),
                    (218, 154, 112), (202, 181, 91), (143, 193, 143),
                    (189, 137, 155), (125, 173, 207),
                ]
                # The robot's saved second-floor PNG is the obsolete, smaller
                # map.  The current live frame already contains the complete
                # expanded floor, so drawing both creates two maps in one
                # canvas.  Build this view solely from the live cells.
                for (mapped_x, mapped_y), pixel in mapped_pixels.items():
                    dest_x = (mapped_x + canvas_shift_x) * scale
                    dest_y = (mapped_y + canvas_shift_y) * scale
                    segment_id = pixel & 0x3F
                    color = (80, 87, 101, 255) if pixel >> 7 else (*palette[(segment_id - 1) % len(palette)], 255)
                    draw.rectangle((dest_x, dest_y, dest_x + scale - 1, dest_y + scale - 1), fill=color)
            else:
                canvas_width, canvas_height = target_width, target_height
        else:
            canvas_width, canvas_height = target_width, target_height
        meta["canvas_shift_x_cells"] = canvas_shift_x
        meta["canvas_shift_y_cells"] = canvas_shift_y
        meta["canvas_width_cells"] = canvas_width
        meta["canvas_height_cells"] = canvas_height

        def target_point(x, y):
            local_x = (x - live_header["left"]) / live_header["grid_size"]
            local_y = (y - live_header["top"]) / live_header["grid_size"]
            return (
                round((width - 1 - local_x if flip_live else local_x) * scale),
                round((height - 1 - local_y if flip_live else local_y) * scale),
            )

        def aligned_target_point(x, y):
            px, py = target_point(x, y)
            return (
                px + (alignment_dx + canvas_shift_x) * scale + alignment_x_px,
                py + (alignment_dy + canvas_shift_y) * scale + alignment_y_px,
            )

        # Live high-bit pixels are walls and small newly detected obstacles.
        # On the second floor the high bit describes the expanding temporary
        # SLAM canvas as well, not only newly detected walls. Drawing it would
        # cover most of the saved map with a moving grey mass.
        draw_live_walls = str(target_header.get("map_id")) != "44"
        for index, pixel in enumerate(pixels):
            if not draw_live_walls:
                break
            if not (pixel >> 7):
                continue
            source_x, source_y = index % width, index // width
            world_x = live_header["left"] + source_x * live_header["grid_size"]
            world_y = live_header["top"] + source_y * live_header["grid_size"]
            px, py = aligned_target_point(world_x, world_y)
            draw.rectangle((px, py, px + scale - 1, py + scale - 1), fill=(80, 87, 101, 235))

        path_text = meta.get("tr")
        if path_text:
            current = None
            for match in re.finditer(r"(?P<operator>[MWSLl])(?P<x>-?\d+),(?P<y>-?\d+)", path_text):
                operator = match.group("operator")
                x, y = int(match.group("x")), int(match.group("y"))
                if operator == "L" and current is not None:
                    next_point = (current[0] + x, current[1] + y)
                    draw.line((aligned_target_point(*current), aligned_target_point(*next_point)), fill=(241, 245, 249, 235), width=2)
                    current = next_point
                elif operator == "l" and current is not None:
                    next_point = (x, y)
                    draw.line((aligned_target_point(*current), aligned_target_point(*next_point)), fill=(241, 245, 249, 235), width=2)
                    current = next_point
                else:
                    current = (x, y)

        for obstacle in meta.get("ai_obstacle", []):
            if len(obstacle) >= 2:
                px, py = aligned_target_point(float(obstacle[0]), float(obstacle[1]))
                draw.rectangle((px - 3, py - 3, px + 3, py + 3), fill=(107, 114, 128, 245), outline=(229, 231, 235, 255))

        output_path = Path(output_path)
        temporary_path = output_path.with_name(f".{output_path.stem}.tmp{output_path.suffix}")
        image.save(temporary_path, format="PNG")
        temporary_path.replace(output_path)
        return output_path, meta
    """

    def _standard_live_canvas_size(self, live_header, target_header):
        """Return one common minimum canvas, while never cropping a live map."""
        widths = [int(live_header["width"]), int(target_header.get("width") or 0)]
        heights = [int(live_header["height"]), int(target_header.get("height") or 0)]
        index_path = self.output_dir / "maps_index.json"
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            for item in index.get("maps", []):
                header = item.get("header") or {}
                widths.append(int(header.get("width") or 0))
                heights.append(int(header.get("height") or 0))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return max(widths), max(heights)

    def render_live_overlay(self, base_png, raw, output_path, target_header):
        """Render every live map with the same map-independent transform."""
        live_header = self._header_from_raw(raw)
        width, height = live_header["width"], live_header["height"]
        pixels = raw[27:27 + width * height]
        meta = self._extract_meta_json(raw, width, height)
        scale = 4

        canvas_width, canvas_height = self._standard_live_canvas_size(
            live_header, target_header
        )
        offset_x = (canvas_width - width) // 2
        offset_y = (canvas_height - height) // 2
        image = Image.new(
            "RGBA",
            (canvas_width * scale, canvas_height * scale),
            (13, 16, 23, 255),
        )
        draw = ImageDraw.Draw(image, "RGBA")
        palette = [
            (185, 136, 210), (113, 164, 215), (111, 190, 194),
            (218, 154, 112), (202, 181, 91), (143, 193, 143),
            (189, 137, 155), (125, 173, 207),
        ]

        for index, pixel in enumerate(pixels):
            if not pixel:
                continue
            cell_x = index % width + offset_x
            cell_y = index // width + offset_y
            segment_id = pixel & 0x3F
            if pixel >> 7:
                color = (43, 48, 61, 255)
            elif segment_id:
                color = (*palette[(segment_id - 1) % len(palette)], 255)
            else:
                continue
            px, py = cell_x * scale, cell_y * scale
            draw.rectangle((px, py, px + scale - 1, py + scale - 1), fill=color)

        def live_point(x, y):
            return (
                round(((x - live_header["left"]) / live_header["grid_size"] + offset_x) * scale),
                round(((y - live_header["top"]) / live_header["grid_size"] + offset_y) * scale),
            )

        path_text = meta.get("tr")
        if path_text:
            current = None
            for match in re.finditer(r"(?P<operator>[MWSLl])(?P<x>-?\d+),(?P<y>-?\d+)", path_text):
                operator = match.group("operator")
                x, y = int(match.group("x")), int(match.group("y"))
                if operator == "L" and current is not None:
                    next_point = (current[0] + x, current[1] + y)
                    draw.line((live_point(*current), live_point(*next_point)), fill=(241, 245, 249, 235), width=2)
                    current = next_point
                elif operator == "l" and current is not None:
                    next_point = (x, y)
                    draw.line((live_point(*current), live_point(*next_point)), fill=(241, 245, 249, 235), width=2)
                    current = next_point
                else:
                    current = (x, y)

        for obstacle in meta.get("ai_obstacle", []):
            if len(obstacle) >= 2:
                px, py = live_point(float(obstacle[0]), float(obstacle[1]))
                draw.rectangle(
                    (px - 3, py - 3, px + 3, py + 3),
                    fill=(107, 114, 128, 245),
                    outline=(229, 231, 235, 255),
                )

        rooms = self._extract_rooms(meta, pixels, width, height)
        for room in rooms:
            center = room.get("center_px")
            if center:
                center["x"] += offset_x
                center["y"] += offset_y

        meta.update({
            "standalone_live_canvas": True,
            "alignment_dx_cells": 0,
            "alignment_dy_cells": 0,
            "alignment_x_px": 0,
            "alignment_y_px": 0,
            "flip_live": False,
            "canvas_shift_x_cells": offset_x,
            "canvas_shift_y_cells": offset_y,
            "canvas_width_cells": canvas_width,
            "canvas_height_cells": canvas_height,
            "rooms": rooms,
        })

        output_path = Path(output_path)
        temporary_path = output_path.with_name(f".{output_path.stem}.tmp{output_path.suffix}")
        image.save(temporary_path, format="PNG")
        temporary_path.replace(output_path)
        return output_path, meta

    def render_all_maps(self, json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        map_items = data.get("mapstr", [])
        if not map_items:
            raise RuntimeError("No mapstr found in map JSON")

        current_map_id = data.get("curr_id")

        index = {
            "current_map_id": current_map_id,
            "source_file": str(json_path),
            "maps": [],
        }

        for item in map_items:
            name = item.get("name") or f"map_{item.get('id')}"
            item_id = item.get("id")
            angle = item.get("angle")

            raw_map = item.get("map")
            if not raw_map:
                continue

            raw = self._decode_raw_map(raw_map)
            header = self._header_from_raw(raw)

            meta = self._extract_meta_json(
                raw,
                header["width"],
                header["height"],
            )

            pixels = raw[27:27 + header["width"] * header["height"]]
            rooms = self._extract_rooms(meta, pixels, header["width"], header["height"])

            safe_name = self._safe_filename(name)
            png_name = f"{item_id}_{safe_name}.png"
            raw_name = f"{item_id}_{safe_name}.decoded"

            png_path = self.output_dir / png_name
            raw_path = self.output_dir / raw_name

            raw_path.write_bytes(raw)
            self.render_single_map_to_png(raw, png_path, meta)

            map_info = {
                "id_from_json": item_id,
                "name": name,
                "angle": angle,
                "is_current": header.get("map_id") == current_map_id,
                "png": str(png_path),
                "decoded": str(raw_path),
                "header": header,
                "rooms": rooms,
                "meta_keys": sorted(list(meta.keys())),
            }

            index["maps"].append(map_info)

            print(f"Rendered: {name} -> {png_path}")

        index_path = self.output_dir / "maps_index.json"
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(f"Index saved: {index_path}")
        return index_path


if __name__ == "__main__":
    client = XiaomiX10MapClient(
        country=config.XIAOMI_CLOUD_COUNTRY,
        output_dir=config.MAP_OUTPUT_DIR,
    )

    AUTH_FILE = config.XIAOMI_CLOUD_AUTH

    if Path(AUTH_FILE).exists():
        client.load_auth(AUTH_FILE)
    else:
        print("Auth file not found")
        print("Starting Xiaomi login")
        client.login()

    print("Reading current map object from robot...")
    map_object = client.get_current_map_object_from_robot()

    print(json.dumps(map_object, indent=2, ensure_ascii=False))

    object_name = map_object["object_name"]
    md5 = map_object.get("md5") or "no_md5"

    map_json_name = f"map_object_{md5}.json"

    print(f"Downloading map object: {object_name}")
    map_json = client.download_object(object_name, map_json_name)
    print(f"Saved: {map_json}")

    index_path = client.render_all_maps(map_json)

    print("Done.")
