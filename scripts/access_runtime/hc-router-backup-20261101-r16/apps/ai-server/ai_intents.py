"""Compatibility import; HC fact rendering lives in one canonical module."""
try:
    from ai_domain_replies import climate_power_reply
except ModuleNotFoundError as exc:
    if exc.name != 'ai_domain_replies':
        raise
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'infra/backend'))
    from ai_domain_replies import climate_power_reply
