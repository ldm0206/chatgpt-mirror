from app.accounts.models import SiteSettings
from app.settings import TURNSTILE_ENABLED, TURNSTILE_SECRET_KEY, TURNSTILE_SITE_KEY


def turnstile_settings():
    """Resolve the active Turnstile pair.

    The panel switch is authoritative: an explicit False turns verification off even
    when the environment supplies a complete pair. While it stays True a panel pair
    wins over the environment, and an empty panel pair falls back to the environment,
    so an installation that only ever configured `.env` keeps behaving as before.
    """
    panel = SiteSettings.objects.filter(pk=1).first()
    site_key = (panel.turnstile_site_key or "").strip() if panel else ""
    secret_key = (panel.turnstile_secret_key or "").strip() if panel else ""
    panel_enabled = panel.turnstile_enabled if panel else True
    if panel_enabled:
        if site_key and secret_key:
            return {"enabled": True, "site_key": site_key, "secret_key": secret_key, "source": "panel"}
        if TURNSTILE_ENABLED:
            return {"enabled": True, "site_key": TURNSTILE_SITE_KEY, "secret_key": TURNSTILE_SECRET_KEY, "source": "env"}
    return {"enabled": False, "site_key": "", "secret_key": "", "source": ""}


def turnstile_env_configured():
    return bool(TURNSTILE_ENABLED and TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY)


def turnstile_public_config():
    config = turnstile_settings()
    return {
        "turnstile_enabled": config["enabled"],
        "turnstile_site_key": config["site_key"] if config["enabled"] else "",
    }
