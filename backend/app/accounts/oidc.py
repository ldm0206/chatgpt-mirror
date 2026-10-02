# -*- coding: utf-8 -*-
"""OIDC relying-party plumbing: config resolution, discovery, tokens, user binding."""
import base64
import hashlib
import re
import secrets
from urllib.parse import urlencode, urlsplit

import jwt
import requests
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired
from django.db import IntegrityError, transaction
from django.utils.crypto import constant_time_compare

from app.accounts.models import OidcIdentity, SiteSettings, User
from app.settings import ADMIN_USERNAME, FREE_ACCOUNT_USERNAME


STATE_SALT = "chatgpt-mirror.oidc-state.v1"
STATE_MAX_AGE_SECONDS = 600
DISCOVERY_CACHE_SECONDS = 3600
HTTP_TIMEOUT_SECONDS = 5
CLOCK_SKEW_SECONDS = 60

ALLOWED_ALGORITHMS = frozenset({
    "RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512",
})
# Hosts that only appear when the gateway forwards its own service name instead of the
# public one, so a derived redirect URI could never match what is registered at the IdP.
UNFORWARDED_HOSTS = frozenset({"django", "chatgpt-mirror", "cfbypass", "gateway"})
USERNAME_DISALLOWED = re.compile(r"[^\w.@+-]")


class OidcError(Exception):
    """Carries the short code the login page maps to a message; never provider text."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def oidc_settings():
    """Resolve the active provider. Panel credentials win, clearing them hands back to env."""
    panel = SiteSettings.objects.filter(pk=1).first()
    if panel and panel.oidc_issuer and panel.oidc_client_id and panel.oidc_client_secret:
        return {
            "enabled": True,
            "source": "panel",
            "issuer": panel.oidc_issuer.strip().rstrip("/"),
            "client_id": panel.oidc_client_id,
            "client_secret": panel.oidc_client_secret,
            "scopes": panel.oidc_scopes.strip() or "openid profile email",
            "display_name": panel.oidc_display_name.strip() or "SSO",
            "redirect_uri": panel.oidc_redirect_uri.strip(),
            "auto_provision": panel.oidc_auto_provision,
            "auto_link_by_username": panel.oidc_auto_link_by_username,
            "link_admins": panel.oidc_link_admins,
            "username_claim": panel.oidc_username_claim.strip() or "preferred_username",
        }
    if settings.OIDC_ISSUER and settings.OIDC_CLIENT_ID and settings.OIDC_CLIENT_SECRET:
        return {
            "enabled": True,
            "source": "env",
            "issuer": settings.OIDC_ISSUER.rstrip("/"),
            "client_id": settings.OIDC_CLIENT_ID,
            "client_secret": settings.OIDC_CLIENT_SECRET,
            "scopes": settings.OIDC_SCOPES or "openid profile email",
            "display_name": settings.OIDC_DISPLAY_NAME or "SSO",
            "redirect_uri": settings.OIDC_REDIRECT_URI,
            "auto_provision": settings.OIDC_AUTO_PROVISION,
            "auto_link_by_username": settings.OIDC_AUTO_LINK_USERNAME,
            "link_admins": settings.OIDC_LINK_ADMINS,
            "username_claim": settings.OIDC_USERNAME_CLAIM or "preferred_username",
        }
    return {
        "enabled": False,
        "source": "",
        "issuer": "",
        "client_id": "",
        "client_secret": "",
        "scopes": "openid profile email",
        "display_name": "SSO",
        "redirect_uri": "",
        "auto_provision": True,
        "auto_link_by_username": True,
        "link_admins": False,
        "username_claim": "preferred_username",
    }


def oidc_public_config():
    config = oidc_settings()
    return {
        "oidc_enabled": config["enabled"],
        "oidc_display_name": config["display_name"] if config["enabled"] else "",
    }


def derive_redirect_uri(request):
    derived = request.build_absolute_uri("/0x/user/oidc/callback")
    parts = urlsplit(derived)
    if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() in UNFORWARDED_HOSTS:
        raise OidcError("config")
    return derived


def oidc_redirect_uri(request, config):
    configured = (config.get("redirect_uri") or "").strip()
    return configured or derive_redirect_uri(request)


def _cache_key(prefix, value):
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"oidc:{prefix}:{digest}"


def discovery(config):
    """Provider metadata, cached per issuer. Raises OidcError('provider') on any failure."""
    issuer = config["issuer"].rstrip("/")
    cache_key = _cache_key("discovery", issuer)
    document = cache.get(cache_key)
    if document:
        return document

    try:
        response = requests.get(
            issuer + "/.well-known/openid-configuration",
            headers={"Accept": "application/json"},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        document = response.json()
    except (requests.RequestException, ValueError):
        raise OidcError("provider")

    if not isinstance(document, dict) or str(document.get("issuer") or "").rstrip("/") != issuer:
        raise OidcError("provider")
    for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        endpoint = str(document.get(field) or "")
        if not endpoint.startswith(("http://", "https://")):
            raise OidcError("provider")

    cache.set(cache_key, document, DISCOVERY_CACHE_SECONDS)
    return document


def _jwks(document, *, refresh=False):
    uri = str(document["jwks_uri"])
    cache_key = _cache_key("jwks", uri)
    if not refresh:
        cached = cache.get(cache_key)
        if cached:
            return cached

    try:
        response = requests.get(uri, headers={"Accept": "application/json"}, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        raise OidcError("provider")
    if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
        raise OidcError("provider")

    cache.set(cache_key, payload, DISCOVERY_CACHE_SECONDS)
    return payload


def _signing_key(document, kid, algorithm):
    for refresh in (False, True):
        keys = _jwks(document, refresh=refresh)
        candidates = [key for key in keys["keys"] if isinstance(key, dict)]
        if kid:
            candidates = [key for key in candidates if key.get("kid") == kid]
        elif len(candidates) > 1:
            candidates = []
        if candidates:
            break
    else:
        raise OidcError("token")

    try:
        return jwt.PyJWK(candidates[0], algorithm=algorithm).key
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise OidcError("token")


def verify_id_token(config, document, id_token, nonce):
    supported = document.get("id_token_signing_alg_values_supported") or []
    algorithms = [value for value in supported if value in ALLOWED_ALGORITHMS] or ["RS256"]

    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError:
        raise OidcError("token")
    algorithm = header.get("alg")
    if algorithm not in algorithms:
        raise OidcError("token")

    key = _signing_key(document, header.get("kid"), algorithm)
    try:
        claims = jwt.decode(
            id_token,
            key,
            algorithms=[algorithm],
            audience=config["client_id"],
            # Compare against the provider's own issuer string, trailing slash included:
            # PyJWT compares it byte for byte with the `iss` claim.
            issuer=str(document.get("issuer") or config["issuer"]),
            leeway=CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
    except jwt.PyJWTError:
        raise OidcError("token")

    if not constant_time_compare(str(claims.get("nonce") or ""), str(nonce)):
        raise OidcError("token")
    authorized_party = claims.get("azp")
    if authorized_party and authorized_party != config["client_id"]:
        raise OidcError("token")
    return claims


def new_flow_state(redirect_uri):
    code_verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return {
        "state": secrets.token_urlsafe(32),
        "nonce": secrets.token_urlsafe(32),
        "code_verifier": code_verifier,
        "code_challenge": challenge,
        "redirect_uri": redirect_uri,
    }


def dump_flow_state(payload):
    return signing.dumps(payload, salt=STATE_SALT, compress=True)


def load_flow_state(raw):
    try:
        payload = signing.loads(raw or "", salt=STATE_SALT, max_age=STATE_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        raise OidcError("state")
    if not isinstance(payload, dict):
        raise OidcError("state")
    for field in ("state", "nonce", "code_verifier", "code_challenge", "redirect_uri"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise OidcError("state")
    return payload


def build_authorize_url(config, document, flow):
    params = {
        "response_type": "code",
        "client_id": config["client_id"],
        "redirect_uri": flow["redirect_uri"],
        "scope": config["scopes"],
        "state": flow["state"],
        "nonce": flow["nonce"],
        "code_challenge": flow["code_challenge"],
        "code_challenge_method": "S256",
    }
    endpoint = document["authorization_endpoint"]
    separator = "&" if "?" in endpoint else "?"
    return endpoint + separator + urlencode(params)


def exchange_code(config, document, flow, code):
    """Swap the authorization code for tokens; raises OidcError('provider'|'token')."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": flow["redirect_uri"],
        "code_verifier": flow["code_verifier"],
    }
    headers = {"Accept": "application/json"}
    supported = document.get("token_endpoint_auth_methods_supported") or []
    if "client_secret_post" not in supported and "client_secret_basic" in supported:
        credentials = f"{config['client_id']}:{config['client_secret']}".encode("utf-8")
        headers["Authorization"] = "Basic " + base64.b64encode(credentials).decode("ascii")
    else:
        data["client_id"] = config["client_id"]
        data["client_secret"] = config["client_secret"]

    try:
        response = requests.post(
            document["token_endpoint"], data=data, headers=headers, timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        if getattr(exc, "response", None) is None:
            raise OidcError("provider")
        raise OidcError("token")

    try:
        payload = response.json()
    except ValueError:
        raise OidcError("provider")
    if not isinstance(payload, dict) or not payload.get("id_token"):
        raise OidcError("token")
    return payload


def fetch_userinfo(document, access_token):
    """Best-effort profile lookup for providers that keep claims out of the id_token."""
    endpoint = document.get("userinfo_endpoint")
    if not endpoint or not access_token:
        return {}
    try:
        response = requests.get(
            endpoint, headers={"Authorization": "Bearer " + access_token}, timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _clean_username(value):
    cleaned = USERNAME_DISALLOWED.sub("", str(value or "").strip())[:150]
    return cleaned if len(cleaned) >= 4 else ""


def derive_username(config, claims):
    candidates = [claims.get(config["username_claim"])]
    if config["username_claim"] != "preferred_username":
        candidates.append(claims.get("preferred_username"))
    email = claims.get("email")
    if isinstance(email, str) and "@" in email:
        candidates.append(email.split("@", 1)[0])

    for candidate in candidates:
        if isinstance(candidate, str):
            cleaned = _clean_username(candidate)
            if cleaned:
                return cleaned
    subject = str(claims.get("sub") or "")
    return "oidc-" + hashlib.sha256(subject.encode("utf-8")).hexdigest()[:8]


def _match_user(username_hint):
    user = User.objects.filter(username=username_hint).first()
    if user:
        return user
    matches = list(User.objects.filter(username__iexact=username_hint)[:2])
    return matches[0] if len(matches) == 1 else None


def _unique_username(base):
    protected = {ADMIN_USERNAME.lower(), FREE_ACCOUNT_USERNAME.lower()}
    candidate = base[:150]
    index = 1
    while candidate.lower() in protected or User.objects.filter(username__iexact=candidate).exists():
        index += 1
        suffix = f"-{index}"
        candidate = base[:150 - len(suffix)] + suffix
    return candidate


def _bind(issuer, subject, user, username_hint):
    try:
        with transaction.atomic():
            return OidcIdentity.objects.create(
                issuer=issuer, subject=subject, user=user, username=username_hint[:150],
            )
    except IntegrityError:
        # Two first-time logins raced on the same subject; the loser adopts the winner.
        identity = OidcIdentity.objects.select_related("user").filter(
            issuer=issuer, subject=subject,
        ).first()
        if identity is None:
            raise
        return identity


def resolve_user(config, claims):
    """Map verified claims onto a mirror user, binding or provisioning when allowed."""
    issuer = config["issuer"].rstrip("/")
    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise OidcError("token")

    identity = OidcIdentity.objects.select_related("user").filter(
        issuer=issuer, subject=subject,
    ).first()
    if identity:
        return identity.user, identity

    username_hint = derive_username(config, claims)
    if config["auto_link_by_username"] and username_hint:
        user = _match_user(username_hint)
        if user is not None:
            if user.username == FREE_ACCOUNT_USERNAME:
                raise OidcError("conflict")
            # Without the explicit opt-in the provider must not be able to claim a
            # privileged local account just by asserting its username.
            if (user.is_staff or user.is_superuser) and not config["link_admins"]:
                raise OidcError("conflict")
            identity = _bind(issuer, subject, user, username_hint)
            return identity.user, identity

    if not config["auto_provision"]:
        raise OidcError("no_account")

    user = User(username=_unique_username(username_hint), remark="OIDC 自动创建", is_active=True)
    user.set_unusable_password()
    user.save()
    identity = _bind(issuer, subject, user, username_hint)
    return identity.user, identity
