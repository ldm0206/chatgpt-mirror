# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import transaction
from django.http import HttpResponseRedirect
from django.middleware.csrf import get_token, rotate_token
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app.accounts import oidc
from app.accounts.authentication import set_auth_cookie
from app.accounts.models import SiteSettings
from app.accounts.serializers import OidcSettingsSerializer
from app.accounts.views.login import LoginIpRateThrottle, issue_user_token
from app.permissions import IsSuperUser
from app.utils import save_visit_log


STATE_COOKIE_NAME = "oidc_state"
STATE_COOKIE_PATH = "/0x/user/oidc/"
LOGIN_PAGE = "/admin/#/login"
ADMIN_HOME = "/admin/#/account/user"
USER_HOME = "/admin/#/login-chatgpt"

ERROR_MESSAGES = {
    "disabled": "OIDC 登录未启用",
    "config": "回调地址无法自动推导，请在管理面板显式配置回调地址",
    "provider": "无法连接身份提供方，请稍后重试",
    "state": "登录会话已失效，请重新登录",
    "token": "身份验证失败，请重新登录",
    "no_account": "该账号尚未开通镜像权限，请联系管理员",
    "conflict": "该账号不能自动绑定，请联系管理员",
    "inactive": "账号已停用，请联系管理员",
    "expired": "账号已过期，请联系管理员",
}


class OidcLoginThrottle(LoginIpRateThrottle):
    scope = "oidc_login"


class OidcCallbackThrottle(LoginIpRateThrottle):
    scope = "oidc_callback"


def _error_message(code):
    return ERROR_MESSAGES.get(code, "登录失败，请稍后重试")


class OidcLoginView(APIView):
    """Hands the browser an authorize URL plus the signed flow cookie to come back with."""

    authentication_classes = ()
    throttle_classes = (OidcLoginThrottle,)

    def get(self, request):
        config = oidc.oidc_settings()
        try:
            if not config["enabled"]:
                raise oidc.OidcError("disabled")
            redirect_uri = oidc.oidc_redirect_uri(request, config)
            document = oidc.discovery(config)
        except oidc.OidcError as error:
            raise ValidationError({"message": _error_message(error.code)})

        flow = oidc.new_flow_state(redirect_uri)
        response = Response({
            "authorize_url": oidc.build_authorize_url(config, document, flow),
            "display_name": config["display_name"],
        })
        response.set_cookie(
            STATE_COOKIE_NAME,
            oidc.dump_flow_state(flow),
            max_age=oidc.STATE_MAX_AGE_SECONDS,
            httponly=True,
            secure=settings.SESSION_COOKIE_SECURE,
            samesite="Lax",
            path=STATE_COOKIE_PATH,
        )
        return response


class OidcCallbackView(APIView):
    """Validates the provider response, then issues the same session a password login would."""

    authentication_classes = ()
    throttle_classes = (OidcCallbackThrottle,)

    def get(self, request):
        config = oidc.oidc_settings()
        try:
            if not config["enabled"]:
                raise oidc.OidcError("disabled")
            if request.query_params.get("error") or not request.query_params.get("code"):
                raise oidc.OidcError("provider")
            flow = oidc.load_flow_state(request.COOKIES.get(STATE_COOKIE_NAME, ""))
            if not constant_time_compare(flow["state"], str(request.query_params.get("state") or "")):
                raise oidc.OidcError("state")

            document = oidc.discovery(config)
            tokens = oidc.exchange_code(config, document, flow, request.query_params["code"])
            claims = oidc.verify_id_token(config, document, tokens["id_token"], flow["nonce"])
            # Some providers keep profile claims out of the id_token; only then ask userinfo,
            # which must never override what the signed token already asserted.
            if not any(isinstance(claims.get(field), str) and claims.get(field)
                       for field in ("preferred_username", "email", config["username_claim"])):
                for claim, value in oidc.fetch_userinfo(document, tokens.get("access_token")).items():
                    if claims.get(claim) in (None, ""):
                        claims[claim] = value
            user, identity = oidc.resolve_user(config, claims)
            if not user.is_active:
                raise oidc.OidcError("inactive")
            if user.expired_date and user.expired_date <= timezone.localdate():
                raise oidc.OidcError("expired")
        except oidc.OidcError as error:
            return self._redirect_to_login(error.code)

        with transaction.atomic():
            token = issue_user_token(user, rotate=True)
            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])
            identity.username = oidc.derive_username(config, claims)
            identity.last_login_at = timezone.now()
            identity.save(update_fields=["username", "last_login_at"])

            request.user = user
            save_visit_log(request, "login")
            rotate_token(request)
            get_token(request)

        destination = ADMIN_HOME if (user.is_staff or user.is_superuser) else USER_HOME
        response = HttpResponseRedirect(destination)
        set_auth_cookie(response, token)
        response.delete_cookie(STATE_COOKIE_NAME, path=STATE_COOKIE_PATH, samesite="Lax")
        return response

    def _redirect_to_login(self, code):
        response = HttpResponseRedirect(f"{LOGIN_PAGE}?oidc_error={code}")
        response.delete_cookie(STATE_COOKIE_NAME, path=STATE_COOKIE_PATH, samesite="Lax")
        return response


class OidcSettingsView(APIView):
    permission_classes = (IsAuthenticated, IsSuperUser)

    def get(self, request):
        config, _ = SiteSettings.objects.get_or_create(pk=1)
        active = oidc.oidc_settings()
        try:
            suggested = oidc.derive_redirect_uri(request)
        except oidc.OidcError:
            suggested = ""
        return Response({
            **OidcSettingsSerializer(config).data,
            "active_source": active["source"],
            "active_enabled": active["enabled"],
            "redirect_uri_suggested": suggested,
        })

    def put(self, request):
        config, _ = SiteSettings.objects.get_or_create(pk=1)
        serializer = OidcSettingsSerializer(config, data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        revision = values.pop("revision")
        if revision != config.revision:
            raise ValidationError("配置已被更改，请关闭后重新打开")
        if not SiteSettings.objects.filter(pk=1, revision=revision).update(
            **values, revision=revision + 1,
        ):
            raise ValidationError("配置已被更改，请重新打开后保存")
        config.refresh_from_db()
        active = oidc.oidc_settings()
        try:
            suggested = oidc.derive_redirect_uri(request)
        except oidc.OidcError:
            suggested = ""
        return Response({
            "message": "OIDC 配置已保存",
            **OidcSettingsSerializer(config).data,
            "active_source": active["source"],
            "active_enabled": active["enabled"],
            "redirect_uri_suggested": suggested,
        })
