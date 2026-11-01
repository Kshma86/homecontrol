#!/usr/bin/env python3
"""Interactive X10 cloud login; credentials stay in the operator's terminal."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import runpy
import subprocess
import sys
import threading
from urllib.parse import urlsplit


CONTAINER_INSTALL = r'''
import json
import os
from pathlib import Path
import tempfile

import config
import sys


class SessionInstallError(Exception):
    pass


def save_auth(path, auth):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected an existing regular auth file")
    previous = path.read_bytes()
    # Retain a private previous copy, including when the final replacement fails.
    fd, backup = tempfile.mkstemp(prefix=path.name + ".previous.", dir=path.parent)
    with os.fdopen(fd, "wb") as stream:
        stream.write(previous)
        stream.flush()
        os.fsync(stream.fileno())
    fd, temporary = tempfile.mkstemp(prefix=".x10-auth-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(auth, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def install():
    auth = json.load(sys.stdin)
    keys = {"country", "userId", "ssecurity", "serviceToken"}
    if not isinstance(auth, dict) or set(auth) != keys or not all(auth.values()):
        raise SessionInstallError("Hiányos felhőmunkamenet; nem történt csere.")
    path = Path(config.XIAOMI_CLOUD_AUTH)
    if path.is_symlink() or not path.is_file():
        raise SessionInstallError("A korábbi munkamenetfájl nem szabályos fájl; nincs csere.")
    old = json.loads(path.read_text())
    if str(auth["userId"]) != str(old["userId"]):
        raise SessionInstallError("Másik Xiaomi-fiókba léptél be; nem történt csere.")
    if auth["country"] != old.get("country", config.XIAOMI_CLOUD_COUNTRY):
        raise SessionInstallError("Eltérő Xiaomi-régió; nem történt csere.")
    save_auth(path, auth)
    print("Felhőbelépés ellenőrizve, munkamenet atomikusan cserélve (0600).")
    print("Az előző munkamenet privát .previous. másolata megmaradt.")
    print("A bridge nem indult újra; következik a felügyelt térképellenőrzés.")


if __name__ == "__main__":
    try:
        install()
    except KeyboardInterrupt:
        print("Belépés megszakítva.", file=__import__("sys").stderr)
        raise SystemExit(130)
    except SessionInstallError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        # Exception URLs and HTTP payloads can include credentials. Never print them.
        print("Belépés/mentés sikertelen (" + type(exc).__name__ +
              "); ne töröld a korábbi munkamenetfájlt.", file=__import__("sys").stderr)
        raise SystemExit(1)
'''


class LoginError(Exception):
    """Only fixed, credential-free operator messages belong here."""


class LoginImagePreview:
    """Show the current CAPTCHA/QR image over a temporary loopback listener."""

    def __init__(self, port=31415, browser_port=31416):
        self.port = port
        self.browser_port = browser_port
        self.server = None
        self.thread = None
        self.image = None

    def show(self, image_content, **unused):
        data = bytes(image_content)
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            content_type = 'image/png'
        elif data.startswith(b'\xff\xd8\xff'):
            content_type = 'image/jpeg'
        elif data.startswith((b'GIF87a', b'GIF89a')):
            content_type = 'image/gif'
        elif data.startswith(b'RIFF') and data[8:12] == b'WEBP':
            content_type = 'image/webp'
        else:
            raise LoginError("A Xiaomi képe nem támogatott formátumú; belépés megszakítva.")
        self.image = (data, content_type)
        if self.server is None:
            preview = self

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if urlsplit(self.path).path not in ('/', '/image'):
                        self.send_error(404)
                        return
                    body, mime = preview.image
                    self.send_response(200)
                    self.send_header('Content-Type', mime)
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *args):
                    pass

            try:
                self.server = HTTPServer(('127.0.0.1', self.port), Handler)
            except OSError:
                raise LoginError("A HC 31415-ös képszerver-portja foglalt/nem elérhető. "
                                 "Lépj ki a korábbi tokenkinyerőből, majd indítsd újra a segédet.") from None
            self.thread = threading.Thread(target=self.server.serve_forever,
                                           kwargs={'poll_interval': .1}, daemon=True)
            self.thread.start()
        print("CAPTCHA/QR-kép a fejlesztői PC böngészőjében (SSH-alagúttal):")
        print("  http://127.0.0.1:" + str(self.browser_port) + "/")
        print("Új kép esetén frissítsd ezt az oldalt. A megoldást itt a terminálban add meg.")

    def close(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
            self.server = None
            self.thread = None
        self.image = None


class SessionCaptured(Exception):
    def __init__(self, auth):
        super().__init__("Validated Xiaomi session captured")
        self.auth = auth


def validated_session(connector, country):
    auth = dict(country=country, userId=connector.userId,
                ssecurity=connector._ssecurity, serviceToken=connector._serviceToken)
    if not all(auth.values()):
        raise LoginError("A belépés nem adott teljes felhőmunkamenetet; nincs csere.")
    result = connector.get_dev_cnt(country)
    if not isinstance(result, dict) or result.get("code") != 0:
        raise LoginError("A belépés utáni felhőellenőrzés sikertelen; nincs csere.")
    return auth


def capture_login(original, country):
    def login(connector, *args, **kwargs):
        if not original(connector, *args, **kwargs):
            raise LoginError("A Xiaomi-belépés sikertelen; a korábbi munkamenet megmaradt.")
        raise SessionCaptured(validated_session(connector, country))
    return login


def refresh(extractor=None):
    extractor = Path(extractor or Path.home() / "Xiaomi-cloud-tokens-extractor/token_extractor.py")
    if not extractor.is_file():
        raise LoginError("A működő tokenkinyerő nem található a saját Xiaomi-cloud-tokens-extractor könyvtáradban.")
    # Check the target before asking for any login. Only the region is returned.
    result = subprocess.run(["docker", "exec", "homecontrol-xiaomi-x10", "python", "-c",
        'import json,config;from pathlib import Path;'
        'a=json.loads(Path(config.XIAOMI_CLOUD_AUTH).read_text());'
        'print(a.get("country",config.XIAOMI_CLOUD_COUNTRY))'],
        capture_output=True, text=True)
    if result.returncode or result.stdout.strip() not in {"cn", "de", "us", "ru", "tw", "sg", "in", "i2"}:
        raise LoginError("Az X10 konténer/régió előellenőrzése sikertelen; belépést nem indítottam.")
    country = result.stdout.strip()
    previous_argv = sys.argv
    try:
        sys.argv = [str(extractor)]
        namespace = runpy.run_path(str(extractor), run_name="hc_x10_login")
        classes = [namespace[name] for name in ("PasswordXiaomiCloudConnector", "QrCodeXiaomiCloudConnector")]
        originals = [(cls, cls.login) for cls in classes]
        image_globals = namespace['main'].__globals__
        previous_image = image_globals.get('present_image_image')
        preview = LoginImagePreview()
        try:
            if previous_image is not None:
                image_globals['present_image_image'] = preview.show
            for cls, original in originals:
                cls.login = capture_login(original, country)
            try:
                namespace["main"]()
            except SessionCaptured as session:
                # No credentials appear in argv, environment or a staging file.
                result = subprocess.run(["docker", "exec", "-i", "homecontrol-xiaomi-x10",
                    "python", "-c", CONTAINER_INSTALL], input=json.dumps(session.auth), text=True)
                return result.returncode
            raise LoginError("Nem jött létre menthető Xiaomi-munkamenet; nincs csere.")
        finally:
            if previous_image is not None:
                image_globals['present_image_image'] = previous_image
            preview.close()
            for cls, original in originals:
                cls.login = original
    finally:
        sys.argv = previous_argv


def main():
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit("A HC saját interaktív SSH-termináljában futtasd; jelszót ne küldj a chatbe.")
    print("A nálad működő helyi tokenkinyerő belépését használjuk (p vagy q).")
    print("Ugyanazzal a Xiaomi-fiókkal és belépési móddal lépj be, amelyik az eszközlistánál működött.")
    print("A sikeres belépés munkamenetét mentjük; az eszköztokeneket nem listázzuk.")
    print("Kép megjelenítéséhez a fejlesztői PC egy másik termináljában tartsd nyitva:")
    print("ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:31416:127.0.0.1:31415 a@192.168.1.133")
    try:
        return refresh()
    except LoginError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ModuleNotFoundError as exc:
        print("Hiányzó Python-modul: " + str(exc.name) +
              ". Ugyanabban a Python-környezetben indítsd, ahol a tokenkinyerő működött.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Belépés megszakítva.", file=sys.stderr)
        return 130
    except Exception as exc:
        print("A helyi belépés/mentés elakadt (" + type(exc).__name__ +
              "). Titokérték nélkül ezt a hibatípust jelezd.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
