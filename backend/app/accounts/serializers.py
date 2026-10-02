import re
from urllib.parse import urlsplit

from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.accounts.models import Announcement, SiteSettings, User, VisitLog
from app.chatgpt.models import ChatgptAccount
from app.settings import ADMIN_USERNAME


class ShowVisitLogModelSerializer(serializers.ModelSerializer):
    is_protected = serializers.SerializerMethodField()

    def get_is_protected(self, obj):
        return obj.username == ADMIN_USERNAME and obj.log_type == "login"

    class Meta:
        model = VisitLog
        fields = "__all__"


class ShowUserAccountModelSerializer(serializers.ModelSerializer):
    last_login = serializers.DateTimeField(format="%Y-%m-%d %H:%M")
    date_joined = serializers.DateTimeField(format="%Y-%m-%d %H:%M")
    use_count = serializers.SerializerMethodField()
    chatgpt_count = serializers.SerializerMethodField()
    conversation_count = serializers.SerializerMethodField()
    message_count = serializers.SerializerMethodField()
    model_message_counts = serializers.SerializerMethodField()

    def __init__(self, *args, use_count_dict=None, conversation_stats_dict=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_count_dict = use_count_dict or {}
        self.conversation_stats_dict = conversation_stats_dict or {}

    def get_chatgpt_count(self, obj):
        return ChatgptAccount.get_by_gptcar_list(obj.gptcar_list).count()

    def get_use_count(self, obj):
        return self.use_count_dict.get(obj.username, 0)

    def get_conversation_count(self, obj):
        return self.conversation_stats_dict.get(obj.username, {}).get("conversation_count", 0)

    def get_message_count(self, obj):
        return self.conversation_stats_dict.get(obj.username, {}).get("message_count", 0)

    def get_model_message_counts(self, obj):
        return self.conversation_stats_dict.get(obj.username, {}).get("model_message_counts", {})

    class Meta:
        model = User
        exclude = (
            "password", "is_superuser", "first_name", "last_name", "email", "is_staff",
            "groups", "user_permissions", "capability_account_id",
            "capability_policy_initialized", "mcp_allowlist", "skills_allowlist",
            "model_policies",
        )
        # fields = "__all__"


class AddUserAccountSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    is_active = serializers.BooleanField()
    username = serializers.CharField(min_length=4)
    password = serializers.CharField(required=False)
    gptcar_list = serializers.JSONField(default=list)
    model_limit = serializers.JSONField(default=dict)
    remark = serializers.CharField(default="", allow_blank=True)
    isolated_session = serializers.BooleanField()
    mcp_isolation = serializers.BooleanField(required=False, default=True)
    skills_isolation = serializers.BooleanField(required=False, default=True)
    model_isolation = serializers.BooleanField(required=False, default=True)
    expired_date = serializers.DateField(required=False, allow_null=True)
    daily_quota = serializers.IntegerField(required=False, min_value=0, default=0)
    monthly_quota = serializers.IntegerField(required=False, min_value=0, default=0)
    force_chat_mode = serializers.BooleanField(required=False)

    def validate_password(self, value):
        if not value:
            return value
        try:
            validate_password(
                value,
                User(username=str(self.initial_data.get("username") or "")),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class UserCapabilityPolicySerializer(serializers.Serializer):
    account_id = serializers.IntegerField(min_value=1)
    mcp_allowed_ids = serializers.ListField(
        child=serializers.CharField(max_length=300), allow_empty=True, max_length=1000
    )
    skills_allowed_ids = serializers.ListField(
        child=serializers.CharField(max_length=300), allow_empty=True, max_length=1000
    )


class UserModelPolicySerializer(serializers.Serializer):
    account_id = serializers.IntegerField(min_value=1)
    model_allowed_ids = serializers.ListField(
        child=serializers.CharField(max_length=200), allow_empty=True, max_length=500
    )
    model_hourly_limits = serializers.DictField(
        child=serializers.IntegerField(min_value=0, max_value=100000), required=False, default=dict
    )
    model_rate_limits = serializers.JSONField(required=False, default=dict)

    def validate_model_rate_limits(self, value):
        if not isinstance(value, dict) or len(value) > 500:
            raise serializers.ValidationError("模型频率限制格式无效")
        normalized = {}
        for raw_model_id, raw_limits in value.items():
            model_id = str(raw_model_id or "").strip().lower()
            if not model_id or len(model_id) > 200 or not isinstance(raw_limits, dict):
                raise serializers.ValidationError("模型频率限制格式无效")
            limits = {}
            for key, default, maximum in (
                ("hour_window_hours", 1, 8760),
                ("hour_limit", 0, 100000),
                ("week_limit", 0, 100000),
                ("month_limit", 0, 100000),
            ):
                raw_value = raw_limits.get(key, default)
                if isinstance(raw_value, bool) or not isinstance(raw_value, int):
                    raise serializers.ValidationError(f"{model_id} 的 {key} 必须是整数")
                minimum = 1 if key == "hour_window_hours" else 0
                if raw_value < minimum or raw_value > maximum:
                    raise serializers.ValidationError(f"{model_id} 的 {key} 超出允许范围")
                limits[key] = raw_value
            normalized[model_id] = limits
        return normalized


class BatchModelLimitSerializer(serializers.Serializer):
    user_id_list = serializers.ListField(child=serializers.IntegerField())
    model_limit = serializers.JSONField()


class UserBindChatGPTSerializer(serializers.Serializer):
    user_id_list = serializers.ListField(child=serializers.IntegerField())
    gptcar_id_list = serializers.ListField(child=serializers.IntegerField())


class BatchUserActionSerializer(serializers.Serializer):
    user_id_list = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=200
    )
    action = serializers.ChoiceField(choices=["activate", "deactivate", "delete"])


class UserRegisterSerializer(serializers.Serializer):
    username = serializers.CharField(min_length=4)
    password = serializers.CharField()
    chatgpt_token = serializers.CharField()

    def validate_password(self, value):
        try:
            validate_password(
                value,
                User(username=str(self.initial_data.get("username") or "")),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class AdminSetupSerializer(serializers.Serializer):
    # The administrator name is fixed by ADMIN_USERNAME: user management, log protection
    # and account registration all key off it, so the wizard must not invent another one.
    password = serializers.CharField()
    confirm_password = serializers.CharField()

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "两次输入的密码不一致"})
        try:
            validate_password(attrs["password"], User(username=ADMIN_USERNAME))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs


class TurnstileSettingsSerializer(serializers.ModelSerializer):
    turnstile_secret_key = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=256, trim_whitespace=False
    )
    secret_configured = serializers.SerializerMethodField()
    revision = serializers.IntegerField(min_value=0)

    class Meta:
        model = SiteSettings
        fields = ("turnstile_site_key", "turnstile_secret_key", "secret_configured", "revision")

    def get_secret_configured(self, obj):
        return bool(obj.turnstile_secret_key)

    @staticmethod
    def _clean(value, label):
        value = value.strip()
        if len(value) > 256 or any(char.isspace() for char in value):
            raise serializers.ValidationError(f"{label}格式无效")
        return value

    def validate_turnstile_site_key(self, value):
        return self._clean(value, "站点密钥")

    def validate_turnstile_secret_key(self, value):
        if value.startswith("enc:v1:"):
            raise serializers.ValidationError("请填写原始密钥")
        return self._clean(value, "密钥")

    def validate(self, attrs):
        site_key = attrs.get("turnstile_site_key", self.instance.turnstile_site_key or "").strip()
        secret_key = attrs.get("turnstile_secret_key") or self.instance.turnstile_secret_key or ""
        if site_key and not secret_key:
            raise serializers.ValidationError({"turnstile_secret_key": "填写站点密钥后需同时填写密钥"})
        if not site_key:
            # Clearing the site key hands the pair back to the environment.
            attrs["turnstile_secret_key"] = ""
        return attrs


class OidcSettingsSerializer(serializers.ModelSerializer):
    oidc_client_secret = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=512, trim_whitespace=False
    )
    secret_configured = serializers.SerializerMethodField()
    revision = serializers.IntegerField(min_value=0)

    SCOPE_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
    CLAIM_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")

    class Meta:
        model = SiteSettings
        fields = (
            "oidc_issuer",
            "oidc_client_id",
            "oidc_client_secret",
            "oidc_scopes",
            "oidc_display_name",
            "oidc_redirect_uri",
            "oidc_auto_provision",
            "oidc_auto_link_by_username",
            "oidc_link_admins",
            "oidc_username_claim",
            "secret_configured",
            "revision",
        )

    def get_secret_configured(self, obj):
        return bool(obj.oidc_client_secret)

    @staticmethod
    def _no_whitespace(value, label):
        value = value.strip()
        if any(char.isspace() for char in value):
            raise serializers.ValidationError(f"{label}不能包含空白字符")
        return value

    @staticmethod
    def _absolute_url(value, label):
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment:
            raise serializers.ValidationError(f"{label}必须是绝对 http(s) 地址")
        return value

    def validate_oidc_issuer(self, value):
        value = self._no_whitespace(value, "Issuer")
        if not value:
            return ""
        return self._absolute_url(value, "Issuer").rstrip("/")

    def validate_oidc_client_id(self, value):
        return self._no_whitespace(value, "Client ID")

    def validate_oidc_client_secret(self, value):
        if value.startswith("enc:v1:"):
            raise serializers.ValidationError("请填写原始密钥")
        return self._no_whitespace(value, "密钥") if value else value

    def validate_oidc_scopes(self, value):
        scopes = value.split()
        if not scopes:
            return "openid profile email"
        if "openid" not in scopes:
            raise serializers.ValidationError("scope 必须包含 openid")
        if len(scopes) > 12 or len(" ".join(scopes)) > 256:
            raise serializers.ValidationError("scope 数量超出限制")
        for scope in scopes:
            if not self.SCOPE_PATTERN.match(scope):
                raise serializers.ValidationError(f"scope {scope} 含非法字符")
        return " ".join(scopes)

    def validate_oidc_display_name(self, value):
        value = value.strip()
        if any(char in value for char in "\r\n"):
            raise serializers.ValidationError("显示名称不能包含换行")
        return value or "SSO"

    def validate_oidc_redirect_uri(self, value):
        value = self._no_whitespace(value, "回调地址")
        if not value:
            return ""
        return self._absolute_url(value, "回调地址")

    def validate_oidc_username_claim(self, value):
        value = value.strip() or "preferred_username"
        if not self.CLAIM_PATTERN.match(value):
            raise serializers.ValidationError("声明名只能包含字母、数字和 . _ : -")
        return value

    def validate(self, attrs):
        instance = self.instance

        def current(field):
            return getattr(instance, field, "") if instance else ""

        issuer = attrs.get("oidc_issuer", current("oidc_issuer")).strip()
        client_id = attrs.get("oidc_client_id", current("oidc_client_id")).strip()
        secret = attrs.get("oidc_client_secret") or current("oidc_client_secret")

        if not issuer:
            # Clearing the issuer hands the provider back to the environment.
            attrs.update({
                "oidc_issuer": "", "oidc_client_id": "", "oidc_client_secret": "", "oidc_redirect_uri": "",
            })
            return attrs
        if not client_id:
            raise serializers.ValidationError({"oidc_client_id": "填写 Issuer 后需同时填写 Client ID"})
        if not secret:
            raise serializers.ValidationError({"oidc_client_secret": "填写 Issuer 后需同时填写密钥"})
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField()
    new_password = serializers.CharField()

    def validate_new_password(self, value):
        try:
            validate_password(value, self.context.get("user"))
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class ConversationTitlePrivacySerializer(serializers.Serializer):
    allow_admin_view_conversation_titles = serializers.BooleanField()


class AnnouncementSerializer(serializers.ModelSerializer):
    target_user_id = serializers.IntegerField(read_only=True, allow_null=True)
    target_username = serializers.CharField(source="target_user.username", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    status = serializers.SerializerMethodField()

    @staticmethod
    def get_status(obj):
        now = timezone.now()
        if not obj.is_active:
            return "disabled"
        if obj.start_at > now:
            return "scheduled"
        if obj.end_at is not None and obj.end_at <= now:
            return "history"
        return "current"

    class Meta:
        model = Announcement
        fields = (
            "id",
            "title",
            "content",
            "scope",
            "target_user_id",
            "target_username",
            "is_active",
            "start_at",
            "end_at",
            "display_timezone",
            "status",
            "created_by_username",
            "created_at",
            "updated_at",
        )


class AnnouncementWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=120)
    content = serializers.CharField(max_length=10000)
    scope = serializers.ChoiceField(
        choices=(Announcement.SCOPE_GLOBAL, Announcement.SCOPE_PERSONAL)
    )
    target_user_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    is_active = serializers.BooleanField(required=False, default=True)
    start_at = serializers.DateTimeField(required=False, allow_null=True)
    end_at = serializers.DateTimeField(required=False, allow_null=True)
    display_timezone = serializers.CharField(required=False, default="Asia/Shanghai", max_length=64)

    def validate(self, attrs):
        display_timezone = attrs.get("display_timezone", "Asia/Shanghai").strip()
        try:
            ZoneInfo(display_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError({"display_timezone": "请选择有效的 IANA 时区"})
        attrs["display_timezone"] = display_timezone

        start_at = attrs.get("start_at")
        if start_at is None:
            start_at = self.instance.start_at if self.instance is not None else timezone.now()
            attrs["start_at"] = start_at
        end_at = attrs.get("end_at")
        if end_at is not None and end_at <= start_at:
            raise serializers.ValidationError({"end_at": "结束时间必须晚于开始时间"})

        target_user_id = attrs.pop("target_user_id", None)
        if attrs["scope"] == Announcement.SCOPE_GLOBAL:
            attrs["target_user"] = None
            return attrs

        target_user = User.objects.filter(id=target_user_id).first()
        if target_user is None:
            raise serializers.ValidationError({"target_user_id": "请选择有效的目标用户"})
        attrs["target_user"] = target_user
        return attrs

    def create(self, validated_data):
        return Announcement.objects.create(**validated_data)

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance
