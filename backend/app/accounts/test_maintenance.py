from datetime import date, timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token

from app.accounts.maintenance import cleanup_expired_data
from app.accounts.models import (
    GatewayRevocation, PendingLogin, SessionAnchor, User, VisitorSession,
)


COMMAND = "app.accounts.management.commands.run_scheduled_tasks"


class CleanupExpiredDataTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.user = User.objects.create_user(username="cleanup-user", password="Strong-password-123!")

    def expired(self, delta=timedelta(minutes=1)):
        return self.now - delta

    def future(self, delta=timedelta(hours=1)):
        return self.now + delta

    def test_expired_sessions_tickets_and_revocations_are_removed(self):
        VisitorSession.objects.create(sid="a" * 32, user=self.user, expires_at=self.expired())
        PendingLogin.objects.create(
            digest="d" * 64, user=self.user, password_digest="p" * 64, csrf_digest="c" * 64,
            expires_at=self.expired(),
        )
        GatewayRevocation.objects.create(
            subject=self.user.username, version="v1", expires_at=self.expired(),
        )

        counts = cleanup_expired_data()

        self.assertEqual(VisitorSession.objects.count(), 0)
        self.assertEqual(PendingLogin.objects.count(), 0)
        self.assertEqual(GatewayRevocation.objects.count(), 0)
        self.assertEqual(counts["visitor_sessions"], 1)
        self.assertEqual(counts["pending_logins"], 1)
        self.assertEqual(counts["gateway_revocations"], 1)

    def test_live_rows_are_kept(self):
        VisitorSession.objects.create(sid="b" * 32, user=self.user, expires_at=self.future())
        PendingLogin.objects.create(
            digest="e" * 64, user=self.user, password_digest="p" * 64, csrf_digest="c" * 64,
            expires_at=self.future(),
        )
        GatewayRevocation.objects.create(
            subject=self.user.username, version="v2", expires_at=self.future(),
        )

        cleanup_expired_data()

        self.assertEqual(VisitorSession.objects.count(), 1)
        self.assertEqual(PendingLogin.objects.count(), 1)
        self.assertEqual(GatewayRevocation.objects.count(), 1)

    def test_session_anchors_without_a_token_are_removed(self):
        token = Token.objects.create(user=self.user)
        kept = SessionAnchor.objects.create(token_key=token.key, started_at=self.now)
        SessionAnchor.objects.create(token_key="0" * 40, started_at=self.now)

        counts = cleanup_expired_data()

        self.assertEqual(list(SessionAnchor.objects.values_list("token_key", flat=True)), [kept.token_key])
        self.assertEqual(counts["session_anchors"], 1)

    def test_every_anchor_is_removed_once_no_token_exists(self):
        SessionAnchor.objects.create(token_key="1" * 40, started_at=self.now)

        cleanup_expired_data()

        self.assertFalse(SessionAnchor.objects.exists())


class RunScheduledTasksTests(TestCase):
    def setUp(self):
        self.tokens = patch(f"{COMMAND}.check_access_token").start()
        self.update = patch(f"{COMMAND}.update_access_token").start()
        self.cleanup = patch(f"{COMMAND}.cleanup_expired_data", return_value={}).start()
        self.addCleanup(patch.stopall)

    def run_once(self, **kwargs):
        call_command("run_scheduled_tasks", "--once", **kwargs)

    def freeze_at(self, hour, day=date(2026, 10, 2)):
        clock = patch(f"{COMMAND}.timezone").start()
        clock.localtime.return_value = timezone.localtime().replace(hour=hour, minute=30)
        clock.localdate.return_value = day
        return clock

    def test_credentials_are_refreshed_on_start(self):
        self.freeze_at(1)

        self.run_once()

        self.tokens.assert_called_once()
        self.update.assert_called_once()

    def test_cleanup_runs_inside_the_nightly_window(self):
        self.freeze_at(3)

        self.run_once()

        self.cleanup.assert_called_once()

    def test_cleanup_waits_before_the_nightly_window(self):
        self.freeze_at(2)

        self.run_once()

        self.cleanup.assert_not_called()

    def test_cleanup_hour_is_configurable(self):
        self.freeze_at(5)

        self.run_once(**{"cleanup_hour": 5})

        self.cleanup.assert_called_once()

    def test_a_failing_refresh_does_not_stop_the_worker(self):
        self.freeze_at(1)
        self.tokens.side_effect = RuntimeError("gateway down")

        self.run_once()

        self.update.assert_called_once()

    def test_a_failing_cleanup_is_logged_not_raised(self):
        self.freeze_at(4)
        self.cleanup.side_effect = RuntimeError("database is locked")

        self.run_once()

        self.cleanup.assert_called_once()
