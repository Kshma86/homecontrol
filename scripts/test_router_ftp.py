#!/usr/bin/env python3
"""Standalone router FTP upload/download probe; no HC settings are changed."""

import argparse
from datetime import datetime, timezone
import ftplib
import getpass
import hashlib
import os
import ssl
import sys
import tempfile
import time
import uuid


BLOCK_SIZE = 256 * 1024
PAYLOAD_NAME = "random-test.bin"


def ftp_text(value):
    if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise argparse.ArgumentTypeError("Üres érték vagy vezérlőkarakter nem használható.")
    return value


def probe(ftp, size_mib, keep_remote=False):
    """Use an already authenticated connection in the selected parent folder."""
    parent = ftp.pwd()
    run_name = "hc-ftp-test-{}-{}".format(
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), uuid.uuid4().hex
    )
    remote_path = parent.rstrip("/") + "/" + run_name
    made_directory = False
    inside_directory = False
    file_attempted = False
    verified = False
    cleanup_ok = True
    try:
        with tempfile.TemporaryDirectory(prefix="hc-ftp-test-") as temporary:
            local_path = os.path.join(temporary, PAYLOAD_NAME)
            expected = hashlib.sha256()
            total_bytes = size_mib * 1024 * 1024
            print(f"Tesztadat készítése: {size_mib} MiB véletlen adat", flush=True)
            with open(local_path, "wb") as output:
                remaining = total_bytes
                while remaining:
                    chunk = os.urandom(min(remaining, BLOCK_SIZE))
                    output.write(chunk)
                    expected.update(chunk)
                    remaining -= len(chunk)

            ftp.mkd(run_name)
            made_directory = True
            ftp.cwd(run_name)
            inside_directory = True
            print(f"Külön tesztkönyvtár: {remote_path}", flush=True)
            print("Feltöltés…", flush=True)
            start = time.monotonic()
            with open(local_path, "rb") as source:
                file_attempted = True
                ftp.storbinary("STOR " + PAYLOAD_NAME, source, BLOCK_SIZE)
            upload_seconds = time.monotonic() - start
            print(f"Feltöltés kész: {upload_seconds:.2f} s, "
                  f"{size_mib / max(upload_seconds, 0.001):.2f} MiB/s", flush=True)

            received = 0
            actual = hashlib.sha256()

            def consume(chunk):
                nonlocal received
                received += len(chunk)
                if received > total_bytes:
                    raise ValueError("A visszatöltött fájl a vártnál nagyobb.")
                actual.update(chunk)

            print("Visszatöltés és SHA-256 ellenőrzés…", flush=True)
            start = time.monotonic()
            ftp.retrbinary("RETR " + PAYLOAD_NAME, consume, BLOCK_SIZE)
            download_seconds = time.monotonic() - start
            if received != total_bytes or actual.digest() != expected.digest():
                raise ValueError("Hibás visszaolvasás: a méret vagy a SHA-256 nem egyezik.")
            verified = True
            print(f"SHA-256 EGYEZIK: {expected.hexdigest()}", flush=True)
            print(f"Visszatöltés kész: {download_seconds:.2f} s, "
                  f"{size_mib / max(download_seconds, 0.001):.2f} MiB/s", flush=True)
    finally:
        if made_directory:
            if keep_remote:
                print(f"A tesztadat megmarad itt: {remote_path}", flush=True)
            else:
                # Only this invocation's exact file/directory; never recursive deletion.
                try:
                    if inside_directory:
                        if file_attempted:
                            ftp.delete(PAYLOAD_NAME)
                        ftp.cwd(parent)
                    ftp.rmd(run_name)
                    print("A saját távoli tesztkönyvtár törölve.", flush=True)
                except (OSError, EOFError, ftplib.Error) as error:
                    cleanup_ok = False
                    print(f"A tesztkönyvtár törlése nem sikerült ({type(error).__name__}). "
                          f"Ellenőrizendő: {remote_path}", file=sys.stderr)
    if verified and not cleanup_ok:
        raise RuntimeError("Az adatellenőrzés sikerült, a takarítás nem sikerült.")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Router FTP-próba: véletlen tesztadat feltöltése, visszaolvasása és SHA-256 ellenőrzése.",
        epilog="A jelszót interaktívan kéri be. Meglévő mentést és HC-beállítást nem módosít."
    )
    parser.add_argument("--host", required=True, type=ftp_text, help="A router LAN IP-je vagy neve, ftp:// előtag nélkül")
    parser.add_argument("--user", required=True, type=ftp_text, help="FTP-felhasználó")
    parser.add_argument("--directory", default="/", type=ftp_text, help="Meglévő FTP-mappa (alapérték: /)")
    parser.add_argument("--port", type=int, default=21)
    parser.add_argument("--size-mib", type=int, default=16, help="Tesztméret MiB-ban: 1–4096 (alapérték: 16)")
    parser.add_argument("--timeout", type=int, default=30, help="Hálózati műveletenkénti időkorlát másodpercben")
    parser.add_argument("--tls", action="store_true", help="Explicit FTPS, hiteles tanúsítvánnyal; csak ha a router támogatja")
    parser.add_argument("--list", action="store_true", help="Csak a kiválasztott mappa listázása, feltöltés nélkül")
    parser.add_argument("--keep-remote", action="store_true", help="A saját tesztkönyvtár megtartása későbbi ellenőrzéshez")
    args = parser.parse_args(argv)
    if not (1 <= args.port <= 65535 and 1 <= args.size_mib <= 4096 and args.timeout > 0):
        parser.error("Hibás port, tesztméret vagy időkorlát.")
    if not sys.stdin.isatty():
        parser.error("Interaktív terminálból indítsd: a jelszót rejtetten kérjük be.")

    ftp = None
    password = ""
    try:
        password = getpass.getpass("FTP-jelszó (nem jelenik meg): ")
        if not password or any(char in password for char in "\r\n\x00"):
            raise ValueError("Üres jelszó vagy CR/LF/NUL karakter nem használható.")
        if args.tls:
            ftp = ftplib.FTP_TLS(timeout=args.timeout, context=ssl.create_default_context())
        else:
            ftp = ftplib.FTP(timeout=args.timeout)
        print(f"Csatlakozás: {args.host}:{args.port} ({'FTPS' if args.tls else 'FTP'}), passzív mód", flush=True)
        ftp.connect(args.host, args.port)
        ftp.login(args.user, password)
        if args.tls:
            ftp.prot_p()
        ftp.set_pasv(True)
        ftp.cwd(args.directory)
        if args.list:
            ftp.dir()
        else:
            probe(ftp, args.size_mib, args.keep_remote)
            print("SIKERES PRÓBA: a feltöltött és visszaolvasott adat azonos.")
        return 0
    except KeyboardInterrupt:
        print("\nA próba megszakítva.", file=sys.stderr)
        return 130
    except (OSError, EOFError, ftplib.Error, ValueError, RuntimeError) as error:
        # Servers may echo command arguments; never include the entered password.
        detail = str(error).replace(password, "[REJTETT]") if password else str(error)
        print(f"HIBA ({type(error).__name__}): {detail}", file=sys.stderr)
        return 1
    finally:
        if ftp is not None:
            ftp.close()


if __name__ == "__main__":
    raise SystemExit(main())
