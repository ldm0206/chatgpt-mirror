import hashlib
import ipaddress
import json
import time
import uuid
from datetime import timedelta
from http.cookies import SimpleCookie

import requests
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.utils import timezone
from requests.exceptions import RequestException
from rest_framework.exceptions import ValidationError

from app.accounts.models import VisitLog
from app.settings import (
    CHATGPT_GATEWAY_URL,
    FREE_ACCOUNT_USERNAME,
    GATEWAY_CONNECT_TIMEOUT_SECONDS,
    GATEWAY_READ_TIMEOUT_SECONDS,
)
from app.settings import GATEWAY_ADMIN_SECRET

FREE_SESSION_SALT = "chatgpt-mirror.free-session.v1"
FREE_SESSION_MAX_AGE = 7 * 24 * 60 * 60


def generate_md5(input_string):
    md5_object = hashlib.md5()
    md5_object.update(input_string.encode('utf-8'))
    return md5_object.hexdigest()

def get_client_ip(request):
    candidates = (
        request.META.get("HTTP_X_CHATGPT_MIRROR_CLIENT_IP"),
        request.META.get("HTTP_CF_CONNECTING_IP"),
        request.META.get("HTTP_TRUE_CLIENT_IP"),
        request.META.get("HTTP_X_REAL_IP"),
        request.META.get("HTTP_X_FORWARDED_FOR"),
        request.META.get("REMOTE_ADDR"),
    )
    for candidate in candidates:
        if not candidate:
            continue
        for value in candidate.split(","):
            value = value.strip().strip("[]")
            try:
                return str(ipaddress.ip_address(value))
            except ValueError:
                continue
    return ""


def create_free_session():
    """Register a visitor session and return its (sid, signed cookie value)."""
    from app.accounts.models import User, VisitorSession

    sid = uuid.uuid4().hex
    VisitorSession.objects.create(
        sid=sid, user=User.objects.get(username=FREE_ACCOUNT_USERNAME),
        expires_at=timezone.now() + timedelta(seconds=FREE_SESSION_MAX_AGE),
    )
    return sid, signing.dumps({"sid": sid}, salt=FREE_SESSION_SALT, compress=True)


def issue_free_session():
    return create_free_session()[1]


def get_request_subject(request):
    if request.user.username != FREE_ACCOUNT_USERNAME:
        return request.user.username

    token = request.COOKIES.get("free_session", "").strip()
    try:
        payload = signing.loads(
            token,
            salt=FREE_SESSION_SALT,
            max_age=FREE_SESSION_MAX_AGE,
        )
    except (BadSignature, SignatureExpired):
        raise ValidationError({"message": "免费访客会话已失效，请重新进入"})

    sid = str(payload.get("sid", "")).strip()
    if len(sid) != 32 or not all(char in "0123456789abcdef" for char in sid):
        raise ValidationError({"message": "免费访客会话无效"})
    from app.accounts.models import VisitorSession
    if not VisitorSession.objects.filter(
        sid=sid, user=request.user, expires_at__gt=timezone.now(),
    ).exists():
        raise ValidationError({"message": "免费访客会话已撤销，请重新进入"})
    return f"{FREE_ACCOUNT_USERNAME}:{sid}"

def req_gateway_with_response(method, uri, *args, **kwargs):
    """req_gateway variant that also returns the raw response, e.g. to relay its cookies."""
    url = CHATGPT_GATEWAY_URL + uri
    headers = {
        "Authorization": "Bearer {}".format(GATEWAY_ADMIN_SECRET),
    }
    try:
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = (
                GATEWAY_CONNECT_TIMEOUT_SECONDS,
                GATEWAY_READ_TIMEOUT_SECONDS,
            )
        res = requests.request(method, url, headers=headers, *args, **kwargs, allow_redirects=False)
    except RequestException as e:
        raise ValidationError("请求异常, 网关服务未正常启用")

    if res.status_code != 200:
        try:
            err_msg = res.json()
        except Exception:
            err_msg = res.text

        raise ValidationError(err_msg)

    return res.json(), res


def req_gateway(method, uri, *args, **kwargs):
    return req_gateway_with_response(method, uri, *args, **kwargs)[0]


def forward_gateway_cookies(gateway_response, response):
    """Relay the gateway's Set-Cookie headers to the browser.

    Django talks to the gateway server-side, so a session cookie the gateway issues
    during login would otherwise never reach the browser. The gateway fronts this
    API on the same origin, so relayed cookies land on the host it serves.
    """
    values = []
    raw_headers = getattr(getattr(gateway_response, "raw", None), "headers", None)
    if raw_headers is not None and hasattr(raw_headers, "getlist"):
        try:
            values = [value for value in raw_headers.getlist("Set-Cookie") if value]
        except Exception:
            values = []
    if not values:
        single = gateway_response.headers.get("Set-Cookie") if gateway_response is not None else None
        if single:
            values = [single]

    for header in values:
        jar = SimpleCookie()
        try:
            jar.load(header)
        except Exception:
            # 透传是尽力而为：解析失败的 Cookie 丢掉，不影响登录本身。
            continue
        for morsel in jar.values():
            max_age = morsel["max-age"]
            try:
                max_age = int(max_age) if max_age else None
            except (TypeError, ValueError):
                max_age = None
            response.set_cookie(
                morsel.key,
                morsel.value,
                max_age=max_age,
                expires=morsel["expires"] or None,
                path=morsel["path"] or "/",
                domain=morsel["domain"] or None,
                secure=bool(morsel["secure"]),
                httponly=bool(morsel["httponly"]),
                samesite=morsel["samesite"] or None,
            )


def clean_int_list(data_list):
    if isinstance(data_list, str):
        data_list = json.loads(data_list)

    new_list = []
    for i in data_list:
        if isinstance(i, int):
            new_list.append(i)
        elif isinstance(i, str) and i.isdigit():
            new_list.append(int(i))

    return new_list


def get_browser_ip(request):
    # Untrusted browser report: keep separate from get_client_ip and all access controls.
    data = getattr(request, "data", {})
    value = data.get("browser_ip") if hasattr(data, "get") else None
    if not isinstance(value, str) or len(value) > 45 or "%" in value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def save_visit_log(request, log_type, chatgpt_username=None):

    VisitLog.save_data({
        "ip": get_client_ip(request),
        "browser_ip": get_browser_ip(request),
        "log_type": log_type,
        "chatgpt_username": chatgpt_username,
        "username": request.user.username,
        "created_at": int(time.time()),
        "user_agent": request.headers.get('User-Agent') or "",
    })
