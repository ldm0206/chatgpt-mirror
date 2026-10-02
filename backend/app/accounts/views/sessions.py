from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app.accounts.models import SiteSettings
from app.accounts.sessions import occupancy, promote_waiting, release
from app.permissions import IsSuperUser


class SessionLimitsSerializer(serializers.Serializer):
    max_active_sessions = serializers.IntegerField(min_value=0, max_value=100000)
    max_sessions_per_account = serializers.IntegerField(min_value=0, max_value=100000)
    session_idle_seconds = serializers.IntegerField(min_value=60, max_value=86400)
    revision = serializers.IntegerField(min_value=0)


class SessionOccupancyView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get(self, request):
        return Response(occupancy())


class SessionReleaseView(APIView):
    """按会话断开：只释放名额，不影响该用户的登录状态。"""

    permission_classes = (IsAuthenticated, IsAdminUser)

    def post(self, request):
        subject = str(request.data.get("subject") or "").strip()
        if not subject:
            raise ValidationError({"subject": "缺少会话标识"})
        if not release(subject):
            raise ValidationError({"subject": "该会话已不在使用中"})
        return Response({"message": "已断开该会话，排队中的会话会自动补位"})


class SessionLimitsView(APIView):
    permission_classes = (IsAuthenticated, IsSuperUser)

    def put(self, request):
        config, _ = SiteSettings.objects.get_or_create(pk=1)
        serializer = SessionLimitsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        revision = values.pop("revision")
        if revision != config.revision:
            raise ValidationError("配置已被更改，请关闭后重新打开")
        if not SiteSettings.objects.filter(pk=1, revision=revision).update(
            **values, revision=revision + 1,
        ):
            raise ValidationError("配置已被更改，请重新打开后保存")
        # Raising a cap should let the queue move immediately.
        promote_waiting()
        return Response({"message": "并发与排队设置已保存", **occupancy()})
