from app.accounts.models import SiteSettings
from app.settings import TURNSTILE_ENABLED, TURNSTILE_SECRET_KEY, TURNSTILE_SITE_KEY


def turnstile_settings():
    """Resolve the active Turnstile pair.

    Keys saved in the panel win; clearing the site key hands the pair back to the
    environment, so an environment-supplied pair can only be switched off there.
    """
    panel = SiteSettings.objects.filter(pk=1).first()
    site_key = (panel.turnstile_site_key or "").strip() if panel else ""
    secret_key = (panel.turnstile_secret_key or "").strip() if panel else ""
    if site_key and secret_key:
        return {"enabled": True, "site_key": site_key, "secret_key": secret_key, "source": "panel"}
    if TURNSTILE_ENABLED:
        return {"enabled": True, "site_key": TURNSTILE_SITE_KEY, "secret_key": TURNSTILE_SECRET_KEY, "source": "env"}
    return {"enabled": False, "site_key": "", "secret_key": "", "source": ""}


def turnstile_public_config():
    config = turnstile_settings()
    return {
        "turnstile_enabled": config["enabled"],
        "turnstile_site_key": config["site_key"] if config["enabled"] else "",
    }
