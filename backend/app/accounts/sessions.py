"""Seat accounting for concurrent mirror sessions.

The mirror cannot observe activity inside the ChatGPT page the gateway serves, so a
seat is claimed when a member enters an upstream account and released by logout, an
admin disconnect, or an idle timeout. When the caps are reached the session waits in
a FIFO queue instead of being refused.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from app.accounts.models import SessionSlot, SiteSettings

UNLIMITED = 0


def slot_settings():
    config = SiteSettings.objects.filter(pk=1).first()
    if config is None:
        return {"max_active_sessions": 0, "max_sessions_per_account": 0, "session_idle_seconds": 1800}
    return {
        "max_active_sessions": config.max_active_sessions,
        "max_sessions_per_account": config.max_sessions_per_account,
        "session_idle_seconds": config.session_idle_seconds,
    }


def active_slots():
    return SessionSlot.objects.filter(state=SessionSlot.STATE_ACTIVE)


def has_capacity(account, limits, exclude_subject=None):
    """Whether one more seat fits, ignoring the seat the caller already holds."""
    occupied = active_slots()
    if exclude_subject:
        occupied = occupied.exclude(subject=exclude_subject)

    max_active = limits["max_active_sessions"]
    if max_active and occupied.count() >= max_active:
        return False

    max_per_account = limits["max_sessions_per_account"]
    if account is not None and max_per_account:
        if occupied.filter(chatgpt_account=account).count() >= max_per_account:
            return False
    return True


def release_expired_slots(now=None):
    """Drop seats that stopped showing any activity."""
    now = now or timezone.now()
    idle_seconds = slot_settings()["session_idle_seconds"]
    if idle_seconds <= 0:
        return 0
    released, _ = SessionSlot.objects.filter(
        last_seen_at__lte=now - timedelta(seconds=idle_seconds)
    ).delete()
    return released


def promote_waiting(now=None):
    """Admit queued sessions while capacity allows, oldest first."""
    now = now or timezone.now()
    limits = slot_settings()
    promoted = 0
    for slot in SessionSlot.objects.filter(state=SessionSlot.STATE_WAITING).select_related("chatgpt_account"):
        if not has_capacity(slot.chatgpt_account, limits, exclude_subject=slot.subject):
            continue
        slot.state = SessionSlot.STATE_ACTIVE
        slot.acquired_at = now
        slot.last_seen_at = now
        slot.save(update_fields=["state", "acquired_at", "last_seen_at"])
        promoted += 1
    return promoted


@transaction.atomic
def admit(subject, user, account, now=None):
    """Claim a seat for this session, or queue it behind the sessions already waiting."""
    now = now or timezone.now()
    release_expired_slots(now)
    promote_waiting(now)
    limits = slot_settings()

    slot = SessionSlot.objects.select_for_update().filter(subject=subject).first()
    already_waiting = slot is not None and slot.state == SessionSlot.STATE_WAITING
    if slot is None:
        slot = SessionSlot(subject=subject, user=user, queued_at=now)

    admitted = has_capacity(account, limits, exclude_subject=subject)
    slot.user = user
    slot.chatgpt_account = account
    slot.last_seen_at = now
    if admitted:
        slot.state = SessionSlot.STATE_ACTIVE
        slot.acquired_at = now
        slot.queued_at = now
    else:
        slot.state = SessionSlot.STATE_WAITING
        slot.acquired_at = None
        if not already_waiting:
            slot.queued_at = now
    slot.save()
    return slot


def release(subject):
    """Free the seat held by this session and let the queue move up."""
    deleted, _ = SessionSlot.objects.filter(subject=subject).delete()
    if deleted:
        promote_waiting()
    return deleted


def touch(subject, now=None):
    """Mark the session as still around, at most once per heartbeat window."""
    now = now or timezone.now()
    SessionSlot.objects.filter(subject=subject).filter(
        Q(last_seen_at__lte=now - timedelta(seconds=30))
    ).update(last_seen_at=now)


def queue_position(slot):
    if slot.state != SessionSlot.STATE_WAITING:
        return 0
    return SessionSlot.objects.filter(state=SessionSlot.STATE_WAITING).filter(
        Q(queued_at__lt=slot.queued_at) | Q(queued_at=slot.queued_at, id__lt=slot.id)
    ).count() + 1


def slot_state(subject):
    slot = SessionSlot.objects.filter(subject=subject).select_related("chatgpt_account").first()
    if slot is None:
        return {"state": "none", "position": 0, "queue_size": 0}
    return {
        "state": slot.state,
        "position": queue_position(slot),
        "queue_size": SessionSlot.objects.filter(state=SessionSlot.STATE_WAITING).count(),
        "chatgpt_username": slot.chatgpt_account.chatgpt_username if slot.chatgpt_account else "",
        "acquired_at": slot.acquired_at.isoformat() if slot.acquired_at else None,
    }


def occupancy():
    """Everything the console needs to show who is inside and who is waiting."""
    limits = slot_settings()
    active = [
        {
            "subject": slot.subject,
            "user_id": slot.user_id,
            "username": slot.user.username,
            "chatgpt_username": slot.chatgpt_account.chatgpt_username if slot.chatgpt_account else "",
            "acquired_at": slot.acquired_at.isoformat() if slot.acquired_at else None,
            "last_seen_at": slot.last_seen_at.isoformat(),
        }
        for slot in active_slots().select_related("user", "chatgpt_account").order_by("acquired_at")
    ]
    waiting = [
        {
            "subject": slot.subject,
            "user_id": slot.user_id,
            "username": slot.user.username,
            "chatgpt_username": slot.chatgpt_account.chatgpt_username if slot.chatgpt_account else "",
            "position": index,
            "queued_at": slot.queued_at.isoformat(),
        }
        for index, slot in enumerate(
            SessionSlot.objects.filter(state=SessionSlot.STATE_WAITING)
            .select_related("user", "chatgpt_account"), start=1,
        )
    ]
    revision = SiteSettings.objects.filter(pk=1).values_list("revision", flat=True).first() or 0
    return {
        "active": active,
        "waiting": waiting,
        "limits": {**limits, "revision": revision},
        "usage": {"active": len(active), "waiting": len(waiting)},
    }
