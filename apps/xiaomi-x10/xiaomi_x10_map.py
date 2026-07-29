import ast
import json
import base64
import zlib
import sys
import subprocess
import re
from pathlib import Path

import requests
from PIL import Image

import config

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
        cmd = [
            MIIOCLI,
            "dreamevacuum",
            "--ip", ROBOT_IP,
            "--token", ROBOT_TOKEN,
            "get_property_by",
            str(siid),
            str(piid),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)

        lines = [line.strip() for line in result.stdout.splitlines()]
        data_line = next((line for line in lines if line.startswith("[{")), None)

        if not data_line:
            raise RuntimeError(f"Could not parse miiocli output:\n{result.stdout}")

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
        file_url = self.get_file_url(object_name)

        response = requests.get(file_url, timeout=30)
        response.raise_for_status()

        path = self.output_dir / filename
        path.write_bytes(response.content)
        return path

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

    def _extract_rooms(self, meta):
        rooms = []

        seg_inf = meta.get("seg_inf")
        if not isinstance(seg_inf, dict):
            return rooms

        for seg_id, seg in seg_inf.items():
            if not isinstance(seg, dict):
                continue

            rooms.append({
                "segment_id": int(seg_id) if str(seg_id).isdigit() else seg_id,
                "name": seg.get("name"),
                "type": seg.get("type"),
                "roomID": seg.get("roomID"),
                "neighbors": seg.get("nei_id"),
            })

        return rooms

    def render_single_map_to_png(self, raw, png_path):
        header = self._header_from_raw(raw)
        width = header["width"]
        height = header["height"]

        pixels = raw[27:27 + width * height]

        img = Image.new("L", (width, height))
        img.putdata(list(pixels))
        img = img.resize((width * 4, height * 4))

        img.save(png_path)
        return png_path

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

            rooms = self._extract_rooms(meta)

            safe_name = self._safe_filename(name)
            png_name = f"{item_id}_{safe_name}.png"
            raw_name = f"{item_id}_{safe_name}.decoded"

            png_path = self.output_dir / png_name
            raw_path = self.output_dir / raw_name

            raw_path.write_bytes(raw)
            self.render_single_map_to_png(raw, png_path)

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
