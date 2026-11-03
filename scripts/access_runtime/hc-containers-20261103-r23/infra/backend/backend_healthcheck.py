"""Read-only HTTP probe; importing the application is deliberately avoided."""
import argparse
import urllib.request

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('live', 'ready', 'workers'), default='workers')
    mode = parser.parse_args().mode
    try:
        with urllib.request.urlopen('http://127.0.0.1:5000/health/' + mode, timeout=2) as response:
            ok = response.status == 200
    except (OSError, ValueError):
        ok = False
    raise SystemExit(0 if ok else 1)
