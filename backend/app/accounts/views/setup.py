from django.db import transaction
from django.middleware.csrf import get_token, rotate_token
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from app.accounts.authentication import ExpiringCookieTokenAuthentication, set_auth_cookie
from app.accounts.session_authority import set_gateway_auth_cookie
from app.accounts.models import User
from app.accounts.serializers import AdminSetupSerializer
from app.accounts.turnstile import turnstile_public_config
from app.accounts.views.login import LoginIpRateThrottle, issue_user_token, verify_turnstile
from app.settings import ADMIN_USERNAME
from app.utils import save_visit_log


def admin_exists():
    return User.objects.filter(is_superuser=True, is_active=True).exists()


class SetupIpRateThrottle(LoginIpRateThrottle):
    scope = "admin_setup"


class AdminSetupStatusView(APIView):
    authentication_classes = ()
    throttle_classes = (SetupIpRateThrottle,)

    def get(self, request):
        return Response({
            "needed": not admin_exists(),
            "admin_username": ADMIN_USERNAME,
            **turnstile_public_config(),
        })


class AdminSetupView(APIView):
    authentication_classes = ()
    throttle_classes = (SetupIpRateThrottle,)

    def post(self, request):
        ExpiringCookieTokenAuthentication._enforce_csrf(request)
        # 人机验证在密码校验之前，且不消耗限流额度。
        verify_turnstile(request, "setup")
        serializer = AdminSetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            # Re-checked inside the transaction: the wizard closes on first success.
            if admin_exists():
                raise PermissionDenied("初始化已完成，请使用管理员账号登录")
            if User.objects.filter(username=ADMIN_USERNAME).exists():
                raise ValidationError({"message": f"用户名 {ADMIN_USERNAME} 已被占用，无法创建管理员"})

            user = User(
                username=ADMIN_USERNAME,
                remark="超级管理员",
                isolated_session=False,
                is_staff=True,
                is_superuser=True,
                is_active=True,
                last_login=timezone.now(),
            )
            user.set_password(serializer.validated_data["password"])
            user.save()

            token = issue_user_token(user, rotate=True)
            request.user = user
            save_visit_log(request, "login")
            rotate_token(request)
            response = Response({
                "authenticated": True,
                "username": user.username,
                "is_admin": True,
                "is_superuser": True,
                "csrf_token": get_token(request),
            })
            set_auth_cookie(response, token)
            set_gateway_auth_cookie(response, user, token, user.username)
            return response
