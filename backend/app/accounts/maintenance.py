"""Housekeeping for rows that nothing else removes."""
from django.utils import timezone
from rest_framework.authtoken.models import Token

from app.accounts.models import GatewayRevocation, PendingLogin, SessionAnchor, VisitorSession
from app.accounts.sessions import promote_waiting, release_expired_slots


def cleanup_expired_data():
    """Delete expired sessions, tickets, delivered revocations and orphaned anchors.

    Every delete is idempotent, so a repeated run (for example after a restart that
    lost the in-process schedule) is harmless.
    """
    now = timezone.now()
    session_slots = release_expired_slots(now)
    if session_slots:
        promote_waiting(now)
    visitor_sessions, _ = VisitorSession.objects.filter(expires_at__lte=now).delete()
    pending_logins, _ = PendingLogin.objects.filter(expires_at__lte=now).delete()
    # deliver() already drops these; a row survives only if its retry never ran.
    gateway_revocations, _ = GatewayRevocation.objects.filter(expires_at__lte=now).delete()
    session_anchors, _ = SessionAnchor.objects.exclude(
        token_key__in=Token.objects.values("key")
    ).delete()
    return {
        "session_slots": session_slots,
        "visitor_sessions": visitor_sessions,
        "pending_logins": pending_logins,
        "gateway_revocations": gateway_revocations,
        "session_anchors": session_anchors,
    }
