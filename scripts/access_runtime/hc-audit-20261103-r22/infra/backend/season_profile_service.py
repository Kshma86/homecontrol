import json
from startup_schema_contract import check_domain
from typing import Any, Callable, Dict


class SeasonProfileService:
    DOMAINS = ("irrigation", "climate")
    PROFILES = ("summer", "winter")
    DEFAULTS = {
        "irrigation": {
            "summer": {
                "manual_watering": True,
                "scheduled_watering": True,
                "solar_pump_automation": True,
                "maintenance_controls": True,
                "measurements_logging": True,
            },
            "winter": {
                "manual_watering": False,
                "scheduled_watering": False,
                "solar_pump_automation": False,
                "maintenance_controls": False,
                "measurements_logging": True,
            },
        },
        "climate": {"summer": {}, "winter": {}},
    }

    def __init__(
        self,
        fetch_all: Callable[..., Any],
        fetch_one: Callable[..., Any],
        execute_one: Callable[..., Any],
        execute_sql: Callable[..., Any],
        invalidate_context: Callable[..., Any],
    ):
        self.fetch_all = fetch_all
        self.fetch_one = fetch_one
        self.execute_one = execute_one
        self.execute_sql = execute_sql
        self.invalidate_context = invalidate_context
        self._schema_ready = False

    def ensure_schema(self):
        if self._schema_ready:
            return
        check_domain(self.fetch_one, "season")
        self._schema_ready = True

    def _validate(self, domain: str, profile: str = None):
        if domain not in self.DOMAINS:
            raise ValueError("unknown seasonal profile domain")
        if profile is not None and profile not in self.PROFILES:
            raise ValueError("profile must be summer or winter")

    def payload(self) -> Dict[str, Any]:
        self.ensure_schema()
        rows = self.fetch_all(
            """
            select p.domain, p.profile, p.settings, p.updated_at,
                   (a.profile = p.profile) as is_active, a.activated_at
            from hc.domain_season_profile p
            join hc.domain_season_active a on a.domain = p.domain
            order by p.domain, p.profile
            """
        )
        domains: Dict[str, Any] = {}
        for domain in self.DOMAINS:
            domain_rows = [dict(row) for row in rows if row["domain"] == domain]
            active = next((row["profile"] for row in domain_rows if row["is_active"]), "summer")
            domains[domain] = {
                "domain": domain,
                "active_profile": active,
                "profiles": {row["profile"]: row for row in domain_rows},
            }
        return {"ok": True, "domains": domains, "profiles": list(self.PROFILES)}

    def active(self, domain: str) -> Dict[str, Any]:
        self._validate(domain)
        self.ensure_schema()
        row = self.fetch_one(
            """
            select a.domain, a.profile, p.settings, a.activated_at, p.updated_at
            from hc.domain_season_active a
            join hc.domain_season_profile p on p.domain = a.domain and p.profile = a.profile
            where a.domain = %s
            """,
            (domain,),
        )
        return dict(row) if row else {
            "domain": domain,
            "profile": "summer",
            "settings": dict(self.DEFAULTS[domain]["summer"]),
        }

    def control_allowed(self, domain: str) -> bool:
        settings = self.active(domain).get("settings") or {}
        return settings.get("control_enabled", True) is not False

    def capability_allowed(self, domain: str, capability: str) -> bool:
        active = self.active(domain)
        settings = active.get("settings") or {}
        default = self.DEFAULTS.get(domain, {}).get(active.get("profile"), {}).get(capability, True)
        if capability in settings:
            return settings[capability] is not False
        if "control_enabled" in settings and capability in {
            "manual_watering", "scheduled_watering", "solar_pump_automation", "maintenance_controls"
        }:
            return settings["control_enabled"] is not False
        return default is not False

    def update_profile(self, domain: str, profile: str, data: Dict[str, Any]):
        self._validate(domain, profile)
        self.ensure_schema()
        current = self.fetch_one(
            "select settings from hc.domain_season_profile where domain=%s and profile=%s",
            (domain, profile),
        ) or {"settings": {}}
        settings = dict(current.get("settings") or {})
        supplied = data.get("settings") if isinstance(data.get("settings"), dict) else data
        if domain == "irrigation":
            allowed_keys = {
                "manual_watering", "scheduled_watering", "solar_pump_automation", "maintenance_controls"
            }
            for key in allowed_keys:
                if key not in supplied:
                    continue
                if not isinstance(supplied[key], bool):
                    raise ValueError(f"{key} must be boolean")
                settings[key] = supplied[key]
            settings["measurements_logging"] = True
            settings.pop("control_enabled", None)
        row = self.execute_one(
            """
            update hc.domain_season_profile
            set settings=%s::jsonb, updated_at=now()
            where domain=%s and profile=%s
            returning domain, profile, settings, updated_at
            """,
            (json.dumps(settings), domain, profile),
        )
        self._invalidate(domain)
        return {"ok": True, "profile": row}

    def activate(self, domain: str, profile: str):
        self._validate(domain, profile)
        self.ensure_schema()
        row = self.execute_one(
            """
            update hc.domain_season_active
            set profile=%s, activated_at=now()
            where domain=%s
            returning domain, profile, activated_at
            """,
            (profile, domain),
        )
        self._invalidate(domain)
        return {"ok": True, "active": row}

    def _invalidate(self, domain: str):
        if domain == "climate":
            self.invalidate_context("climate", "climate_schedules", "scheduler", "scheduler_ai")
        else:
            self.invalidate_context("irrigation", "irrigation_pilot", "scheduler", "scheduler_ai")
