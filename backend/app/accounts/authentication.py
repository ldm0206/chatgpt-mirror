from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.authentication import get_authorization_header
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError

from app.accounts.models import SessionAnchor
from app.accounts.sessions import touch
from app.security import ConfigurableCsrfViewMiddleware


AUTH_COOKIE_NAME = "mirror_api_session"


class _CsrfCheck(ConfigurableCsrfViewMiddleware):
    def _reject(self, request, reason):
        return reason


def renew_session(token):
    """Slide the session window once less than half its lifetime remains.

    Returns the renewal deadline capped by the installation's maximum session lifetime,
    or None when the session is already past that ceiling.
    """
    now = timezone.now()
    ttl = settings.API_TOKEN_TTL_SECONDS
    if not settings.API_TOKEN_SLIDING_RENEWAL:
        return None
    if token.created + timedelta(seconds=ttl / 2) > now:
        return None

    anchor, _ = SessionAnchor.objects.get_or_create(
        token_key=token.key, defaults={"started_at": token.created},
    )
    max_lifetime = settings.API_TOKEN_MAX_LIFETIME_SECONDS
    if max_lifetime and now >= anchor.started_at + timedelta(seconds=max_lifetime):
        return None

    type(token).objects.filter(pk=token.pk).update(created=now)
    token.created = now
    return now + timedelta(seconds=ttl)


class ExpiringCookieTokenAuthentication(TokenAuthentication):
    """Authenticate API clients by header or by a scoped HttpOnly cookie."""

    def authenticate(self, request):
        header = get_authorization_header(request)
        cookie_token = request.COOKIES.get(AUTH_COOKIE_NAME, "").strip()
        if header:
            result = super().authenticate(request)
        elif cookie_token:
            result = self.authenticate_credentials(cookie_token)
            self._enforce_csrf(request)
        else:
            return None

        if result is None:
            return None
        user, token = result
        expires_at = token.created + timedelta(seconds=settings.API_TOKEN_TTL_SECONDS)
        expired_account = user.expired_date and user.expired_date <= timezone.localdate()
        if timezone.now() >= expires_at or not user.is_active or expired_account:
            type(token).objects.filter(user=user).delete()
            raise AuthenticationFailed("登录已过期，请重新登录")
        if user.username == settings.FREE_ACCOUNT_USERNAME:
            from app.utils import get_request_subject
            request.user = user
            try:
                subject = get_request_subject(request)
            except ValidationError:
                raise AuthenticationFailed("免费访客会话已失效，请重新进入")
        else:
            # The shared visitor token is reissued per VisitorSession; only real members slide.
            renew_session(token)
            subject = user.username
        # Any authenticated call keeps this session's seat and queue entry alive.
        touch(subject)
        return user, token

    @staticmethod
    def _enforce_csrf(request):
        check = _CsrfCheck(lambda _request: None)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            raise PermissionDenied(f"CSRF 验证失败: {reason}")


def set_auth_cookie(response, token):
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token.key,
        max_age=settings.API_TOKEN_TTL_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="Strict",
        path="/0x/",
    )


def clear_auth_cookie(response):
    response.delete_cookie(AUTH_COOKIE_NAME, path="/0x/", samesite="Strict")
