#!/usr/bin/env python3
"""Read-only HC bring-up checklist; no token/password, login or rover mutation."""
import argparse
import json
import re
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def checklist(snapshot, operator, releases):
    identity = snapshot.get("identity") or {}
    crc = identity.get("profile_crc")
    vg = (identity.get("contract") == "3.1.0" and identity.get("stm_remote_update") is True
          and identity.get("update_service_abi") == 2 and identity.get("stm_flash_layout") == "H743_1M_QSPI2"
          and identity.get("stm_image_max_bytes") == 524288 and type(crc) is str
          and re.fullmatch(r"[0-9A-F]{8}", crc) is not None and crc != "00000000"
          and "stm_confirmed_slot" in identity and identity["stm_confirmed_slot"] is None
          and "stm_inactive_slot" in identity and identity["stm_inactive_slot"] is None)
    return {"hc_rover_configured": snapshot.get("configured") is True,
            "hc_operator_configured": operator.get("configured") is True,
            "ordinary_stm_fresh": snapshot.get("freshness", {}).get("fresh") is True,
            "operational_contract_compatible": identity.get("compatible") is True,
            "vg_updater_advertised": bool(vg), "native_update_locked": identity.get("update_locked") if type(identity.get("update_locked")) is bool else None,
            "reviewed_release_count": len(releases.get("releases", [])) if type(releases.get("releases")) is list else 0,
            "hardware_qualified": False, "mutations_sent": 0}


def service_checklist(snapshot):
    service = snapshot.get("service") or {}
    configuration = snapshot.get("configuration") or {}
    return {"hc_rover_configured": snapshot.get("configured") is True,
            "origin_configured": configuration.get("origin_configured") is True,
            "token_configured": configuration.get("token_configured") is True,
            "connection": snapshot.get("connection", {}).get("status"),
            "service_mode": service.get("mode"), "service_abi": service.get("service_abi"),
            "stm_fresh": snapshot.get("freshness", {}).get("fresh") is True,
            "esp_firmware": service.get("esp_firmware"), "stm_firmware": service.get("stm_firmware"),
            "stm_uid": service.get("stm_uid"), "storage": service.get("storage"), "revision": service.get("revision"),
            "motion_permitted": service.get("motion_permitted"), "applied": service.get("applied"),
            "hardware_qualified": False, "mutations_sent": 0}


def bringup_checklist(snapshot):
    identity, state, update, health = (snapshot.get(key) or {} for key in ("identity", "state", "update", "health"))
    return {"hc_rover_configured": snapshot.get("configured") is True, "read_only": snapshot.get("read_only") is True,
            "connection": snapshot.get("connection", {}).get("status"), "mode": identity.get("mode"),
            "esp_firmware": identity.get("esp_fw"), "stm_firmware": identity.get("stm_fw"),
            "esp_boot": identity.get("esp_boot"), "stm_boot": identity.get("stm_boot"),
            "stm_fresh": snapshot.get("freshness", {}).get("fresh") is True,
            "source_seq": state.get("source_seq"), "control_epoch": state.get("control_epoch"),
            "stm_state": state.get("state"), "physical_stop_proven": False,
            "motion_permitted": identity.get("motion_permitted"), "commissioned": identity.get("commissioned"),
            "wifi_connected": health.get("wifi_connected"), "rssi_dbm": health.get("rssi_dbm"),
            "update_locked": update.get("locked"), "update_error": update.get("error"),
            "can_finish": update.get("can_finish"), "hardware_qualified": False, "mutations_sent": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1", help="HC origin, not rover origin")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--service", action="store_true", help="Read historical FIRST_INSTALL_SERVICE snapshot only")
    mode.add_argument("--bringup", action="store_true", help="Read native HC_BRINGUP diagnostics only")
    mode.add_argument("--operational", action="store_true", help="Read preserved operational v3.1 checklist instead of the default bringup view")
    args = parser.parse_args()
    args.bringup = not args.service and not args.operational
    parsed = urllib.parse.urlsplit(args.url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        parser.error("Pontos HC HTTP(S) origin kell; token, userinfo és útvonal nélkül.")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    def read(path):
        request = urllib.request.Request(args.url.rstrip("/")+path, headers={"Accept":"application/json"})
        with opener.open(request, timeout=14 if args.bringup else 8 if args.service else 5) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError()
        result = json.loads(raw)
        if type(result) is not dict or result.get("ok") is not True:
            raise ValueError()
        return result
    try:
        result = bringup_checklist(read("/api/mower/v3/bringup/snapshot")) if args.bringup else service_checklist(read("/api/mower/v3/service/snapshot")) if args.service else checklist(
            read("/api/mower/v3/snapshot"), read("/api/mower/v3/operator"), read("/api/mower/v3/firmware/releases"))
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, urllib.error.URLError):
        print("A HC ellenőrzése nem fejeződött be; nem indult módosító kérés.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
