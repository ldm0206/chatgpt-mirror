import time
from urllib.parse import urlsplit

from django.core.cache import cache
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.exceptions import ValidationError
from django.middleware.csrf import get_token

from app.accounts.models import SiteSettings, VisitLog
from app.accounts.oidc import oidc_public_config
from app.accounts.serializers import TurnstileSettingsSerializer
from app.accounts.turnstile import (
    turnstile_env_configured, turnstile_public_config, turnstile_settings,
)
from app.permissions import IsSuperUser
from app.settings import SHOW_GITHUB
from app.utils import req_gateway, get_client_ip, get_request_subject
from app.accounts.views.login import LoginIpRateThrottle

EGRESS_LOG_TYPE = "egress-blocked"
EGRESS_DEDUPE_SECONDS = 3600
EGRESS_MAX_EVENTS = 50
EGRESS_MAX_RECORDS = 10


class LoginBootstrapThrottle(LoginIpRateThrottle):
    scope = "login_bootstrap"


class VersionConfig(APIView):
    authentication_classes = ()
    throttle_classes = (LoginBootstrapThrottle,)

    def get(self, request):
        return Response({
            'csrf_token': get_token(request),
            'show_github': SHOW_GITHUB,
            **turnstile_public_config(),
            **oidc_public_config(),
        })


class TurnstileSettingsView(APIView):
    permission_classes = (IsAuthenticated, IsSuperUser)

    def payload(self, config, active):
        return {
            **TurnstileSettingsSerializer(config).data,
            "active_source": active["source"],
            "active_enabled": active["enabled"],
            "env_enabled": turnstile_env_configured(),
        }

    def get(self, request):
        config, _ = SiteSettings.objects.get_or_create(pk=1)
        active = turnstile_settings()
        return Response(self.payload(config, active))

    def put(self, request):
        config, _ = SiteSettings.objects.get_or_create(pk=1)
        serializer = TurnstileSettingsSerializer(config, data=request.data)
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
        active = turnstile_settings()
        return Response({
            "message": "人机验证配置已保存",
            **self.payload(config, active),
        })


class AccessControlView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get(self, request):
        res = req_gateway("get", "/api/blocked-paths")
        return Response(res)

    def post(self, request):
        paths = request.data.get("paths", request.data.get("hash_paths", []))
        res = req_gateway("post", "/api/blocked-paths", json={"paths": paths})
        return Response(res)


class PoliticalModerationConfigView(APIView):
    permission_classes = (IsAuthenticated, IsSuperUser)

    @staticmethod
    def payload(request, force_enabled=None):
        enabled = request.data.get("enabled", False)
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
        if force_enabled is not None:
            enabled = force_enabled
        return {
            "enabled": bool(enabled),
            "protocol": request.data.get("protocol") or "openai_chat",
            "model": request.data.get("model") or "",
            "api_key": request.data.get("api_key") or "",
            "base_url": request.data.get("base_url") or "https://api.openai.com/v1",
            "mode": request.data.get("mode") or "relaxed",
            "custom_terms": request.data.get("custom_terms") or [],
            "limit_per_minute": request.data.get("limit_per_minute", 10),
            "limit_per_five_minutes": request.data.get("limit_per_five_minutes", 30),
            "limit_per_hour": request.data.get("limit_per_hour", 120),
        }

    def get(self, request):
        return Response(req_gateway("get", "/api/political-moderation-config"))

    def post(self, request):
        return Response(req_gateway(
            "post",
            "/api/political-moderation-config",
            json=self.payload(request),
        ))


class PoliticalModerationTestView(PoliticalModerationConfigView):
    def post(self, request):
        return Response(req_gateway(
            "post",
            "/api/political-moderation-config/test",
            json=self.payload(request, force_enabled=True),
        ))


class EgressReportView(APIView):
    """接收镜像页面外联防护脚本上报的拦截记录，落库到访问日志。"""

    permission_classes = (IsAuthenticated,)

    def post(self, request):
        events = request.data.get("events")
        if not isinstance(events, list):
            raise ValidationError({"events": "格式错误"})

        subject = get_request_subject(request)
        ip = get_client_ip(request)
        user_agent = request.headers.get("User-Agent") or ""
        now = int(time.time())
        recorded = 0

        for item in events[:EGRESS_MAX_EVENTS]:
            if recorded >= EGRESS_MAX_RECORDS:
                break
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()[:500]
            if not url:
                continue
            try:
                host = (urlsplit(url).hostname or "")[:150]
            except ValueError:
                host = ""
            target = host or url[:150]
            # 同一用户对同一域名的拦截一小时只记一条，防止页面抖动刷爆日志
            dedupe_key = f"egress-report:{subject}:{target}"
            if cache.get(dedupe_key):
                continue
            cache.set(dedupe_key, 1, EGRESS_DEDUPE_SECONDS)
            VisitLog.save_data({
                "ip": ip,
                "log_type": EGRESS_LOG_TYPE,
                "chatgpt_username": target,
                "username": request.user.username,
                "created_at": now,
                "user_agent": user_agent,
            })
            recorded += 1

        return Response({"message": "已记录", "recorded": recorded})
