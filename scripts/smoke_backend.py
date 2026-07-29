#!/usr/bin/env python3
import argparse
import json
import time
import urllib.error
import urllib.request


CHECKS = [
    ("GET", "/health", None, {200, 503}),
    ("GET", "/api/ai/status", None, {200, 502}),
    ("POST", "/api/ai/chat", {"message": ""}, {400}),
    ("GET", "/api/context", None, {200, 207}),
    ("GET", "/api/context/ai/summary", None, {200, 207}),
    ("GET", "/api/context?full=1", None, {200, 207}),
    ("GET", "/api/context/irrigation", None, {200, 404}),
    ("GET", "/api/context/scheduler", None, {200, 404}),
    ("GET", "/api/context/backup", None, {200, 404}),
    ("GET", "/api/backup", None, {200, 207}),
    ("GET", "/api/homecontrol/statistics", None, {200, 207}),
    ("GET", "/api/performance", None, {200, 207}),
]
DEFAULT_BUDGETS_MS = {
    "/health": 500,
    "/api/context": 250,
    "/api/context/ai/summary": 900,
    "/api/context/scheduler": 500,
    "/api/context/irrigation": 250,
    "/api/context/backup": 250,
    "/api/backup": 250,
    "/api/performance": 500,
}


def request_json(base_url, method, path, body, timeout):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    payload = {}
    if raw:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {"raw": raw.decode("utf-8", errors="replace")[:500]}
    return status, elapsed_ms, payload


def main():
    parser = argparse.ArgumentParser(description="Smoke-test the HomeControl backend HTTP API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--no-perf-budget", action="store_true", help="Only validate status codes.")
    args = parser.parse_args()

    failures = []
    for method, path, body, allowed in CHECKS:
        status, elapsed_ms, payload = request_json(args.base_url.rstrip("/"), method, path, body, args.timeout)
        budget_ms = DEFAULT_BUDGETS_MS.get(path)
        status_ok = status in allowed
        budget_ok = args.no_perf_budget or budget_ms is None or elapsed_ms <= budget_ms
        ok = status_ok and budget_ok
        marker = "OK" if ok else "FAIL"
        budget_text = f" budget={budget_ms}ms" if budget_ms is not None and not args.no_perf_budget else ""
        print(f"{marker} {method} {path} -> {status} {elapsed_ms}ms{budget_text}")
        if not ok:
            failures.append({
                "method": method,
                "path": path,
                "status": status,
                "allowed_statuses": sorted(allowed),
                "elapsed_ms": elapsed_ms,
                "budget_ms": budget_ms,
                "payload": payload,
            })

    if failures:
        print(json.dumps({"ok": False, "failures": failures}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "checks": len(CHECKS)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
