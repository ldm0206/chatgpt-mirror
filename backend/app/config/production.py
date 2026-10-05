import os
from pathlib import Path

DEBUG = False

FREE_ACCOUNT_USERNAME = "free_account"

def required_env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"{key} must be set in production")
    return value


ADMIN_USERNAME = required_env("ADMIN_USERNAME")
# 留空则跳过启动时初始化，改由首次访问网页的向导创建管理员。
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
GATEWAY_ADMIN_SECRET = required_env("GATEWAY_ADMIN_SECRET")
CHATGPT_GATEWAY_URL = required_env("CHATGPT_GATEWAY_URL")
ALLOW_REGISTER = os.environ.get("ALLOW_REGISTER", "false") == "true"
SHOW_GITHUB = os.environ.get("SHOW_GITHUB", "true") == "true"

TURNSTILE_MODE = os.environ.get("CLOUDFLARE_TURNSTILE", "disable").strip().lower()
if TURNSTILE_MODE not in {"enable", "disable"}:
    raise RuntimeError("CLOUDFLARE_TURNSTILE must be enable or disable")
TURNSTILE_ENABLED = TURNSTILE_MODE == "enable"
TURNSTILE_SITE_KEY = os.environ.get("CLOUDFLARE_TURNSTILE_SITE_KEY", "").strip()
TURNSTILE_SECRET_KEY = os.environ.get("CLOUDFLARE_TURNSTILE_SECRET_KEY", "").strip()
if TURNSTILE_ENABLED and (not TURNSTILE_SITE_KEY or not TURNSTILE_SECRET_KEY):
    raise RuntimeError(
        "CLOUDFLARE_TURNSTILE_SITE_KEY and CLOUDFLARE_TURNSTILE_SECRET_KEY "
        "must be set when CLOUDFLARE_TURNSTILE=enable"
    )

# OIDC 单点登录：三要素齐全即启用，面板里保存的值优先于这里。
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "").strip()
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "").strip()
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "").strip()
OIDC_SCOPES = os.environ.get("OIDC_SCOPES", "openid profile email").strip()
OIDC_DISPLAY_NAME = os.environ.get("OIDC_DISPLAY_NAME", "SSO").strip()
OIDC_REDIRECT_URI = os.environ.get("OIDC_REDIRECT_URI", "").strip()
OIDC_AUTO_PROVISION = os.environ.get("OIDC_AUTO_PROVISION", "true") == "true"
OIDC_AUTO_LINK_USERNAME = os.environ.get("OIDC_AUTO_LINK_USERNAME", "false") == "true"
OIDC_LINK_ADMINS = os.environ.get("OIDC_LINK_ADMINS", "false") == "true"
OIDC_USERNAME_CLAIM = os.environ.get("OIDC_USERNAME_CLAIM", "preferred_username").strip()

BASE_DIR = Path(__file__).resolve().parent.parent
