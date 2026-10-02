import time
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from app.accounts.models import SessionSlot, SiteSettings, User
from app.accounts.sessions import (
    admit, occupancy, queue_position, release, release_expired_slots, slot_state, touch,
)
from app.chatgpt.models import ChatgptAccount, ChatgptCar


def make_account(username):
    return ChatgptAccount.objects.create(
        chatgpt_username=username,
        plan_type="plus",
        access_token="token-" + username,
        access_token_valid=True,
        session_token_valid=True,
        created_time=int(time.time()),
        updated_time=int(time.time()),
    )


def set_limits(**values):
    config, _ = SiteSettings.objects.get_or_create(pk=1)
    for key, value in values.items():
        setattr(config, key, value)
    config.save()
    return config


class SeatAdmissionTests(TestCase):
    def setUp(self):
        self.first = User.objects.create_user(username="first", password="Strong-password-123!")
        self.second = User.objects.create_user(username="second", password="Strong-password-123!")
        self.account = make_account("shared@example.com")
        self.other = make_account("other@example.com")

    def test_defaults_admit_everyone(self):
        first = admit("first", self.first, self.account)
        second = admit("second", self.second, self.account)

        self.assertEqual(first.state, SessionSlot.STATE_ACTIVE)
        self.assertEqual(second.state, SessionSlot.STATE_ACTIVE)

    def test_global_cap_queues_the_extra_session(self):
        set_limits(max_active_sessions=1)

        first = admit("first", self.first, self.account)
        second = admit("second", self.second, self.account)

        self.assertEqual(first.state, SessionSlot.STATE_ACTIVE)
        self.assertEqual(second.state, SessionSlot.STATE_WAITING)
        self.assertEqual(queue_position(second), 1)

    def test_per_account_cap_only_limits_that_account(self):
        set_limits(max_sessions_per_account=1)

        admit("first", self.first, self.account)
        same_account = admit("second", self.second, self.account)
        other_account = admit("second", self.second, self.other)

        self.assertEqual(same_account.state, SessionSlot.STATE_WAITING)
        self.assertEqual(other_account.state, SessionSlot.STATE_ACTIVE)

    def test_re_entering_does_not_consume_a_second_seat(self):
        set_limits(max_active_sessions=1)

        admit("first", self.first, self.account)
        again = admit("first", self.first, self.account)

        self.assertEqual(again.state, SessionSlot.STATE_ACTIVE)
        self.assertEqual(SessionSlot.objects.count(), 1)

    def test_switching_account_moves_the_seat(self):
        admit("first", self.first, self.account)
        moved = admit("first", self.first, self.other)

        self.assertEqual(moved.chatgpt_account, self.other)
        self.assertEqual(SessionSlot.objects.count(), 1)

    def test_waiting_order_is_first_in_first_out(self):
        set_limits(max_active_sessions=1)
        admit("first", self.first, self.account)
        second_slot = admit("second", self.second, self.account)
        third = User.objects.create_user(username="third", password="Strong-password-123!")
        third_slot = admit("third", third, self.account)

        self.assertEqual(queue_position(second_slot), 1)
        self.assertEqual(queue_position(third_slot), 2)
        self.assertEqual(slot_state("second")["queue_size"], 2)


class SeatReleaseTests(TestCase):
    def setUp(self):
        self.first = User.objects.create_user(username="first", password="Strong-password-123!")
        self.second = User.objects.create_user(username="second", password="Strong-password-123!")
        self.account = make_account("shared@example.com")

    def test_releasing_the_seat_promotes_the_oldest_waiter(self):
        set_limits(max_active_sessions=1)
        admit("first", self.first, self.account)
        admit("second", self.second, self.account)

        release("first")

        self.assertEqual(slot_state("second")["state"], SessionSlot.STATE_ACTIVE)

    def test_promotion_respects_the_per_account_cap(self):
        set_limits(max_sessions_per_account=1)
        account = make_account("only@example.com")
        admit("first", self.first, account)
        admit("second", self.second, account)

        release("first")

        self.assertEqual(slot_state("second")["state"], SessionSlot.STATE_ACTIVE)

    def test_idle_seats_are_reclaimed_and_the_queue_advances(self):
        set_limits(max_active_sessions=1, session_idle_seconds=600)
        admit("first", self.first, self.account)
        admit("second", self.second, self.account)
        SessionSlot.objects.filter(subject="first").update(
            last_seen_at=timezone.now() - timedelta(seconds=601)
        )

        admit("second", self.second, self.account)

        self.assertFalse(SessionSlot.objects.filter(subject="first").exists())
        self.assertEqual(slot_state("second")["state"], SessionSlot.STATE_ACTIVE)

    def test_expired_seats_are_only_reclaimed_when_idle_is_enabled(self):
        set_limits(session_idle_seconds=0)
        admit("first", self.first, self.account)
        SessionSlot.objects.update(last_seen_at=timezone.now() - timedelta(days=30))

        self.assertEqual(release_expired_slots(), 0)

    def test_touch_extends_the_seat(self):
        set_limits(max_active_sessions=1, session_idle_seconds=600)
        admit("first", self.first, self.account)
        stale = timezone.now() - timedelta(seconds=120)
        SessionSlot.objects.filter(subject="first").update(last_seen_at=stale)

        touch("first")

        self.assertGreater(SessionSlot.objects.get(subject="first").last_seen_at, stale)


class OccupancyTests(TestCase):
    def setUp(self):
        self.first = User.objects.create_user(username="first", password="Strong-password-123!")
        self.second = User.objects.create_user(username="second", password="Strong-password-123!")
        self.account = make_account("shared@example.com")

    def test_occupancy_reports_seats_queue_and_limits(self):
        set_limits(max_active_sessions=1, max_sessions_per_account=2, session_idle_seconds=900)
        admit("first", self.first, self.account)
        admit("second", self.second, self.account)

        snapshot = occupancy()

        self.assertEqual([row["username"] for row in snapshot["active"]], ["first"])
        self.assertEqual([row["username"] for row in snapshot["waiting"]], ["second"])
        self.assertEqual(snapshot["usage"], {"active": 1, "waiting": 1})
        self.assertEqual(snapshot["limits"]["max_active_sessions"], 1)
        self.assertEqual(snapshot["limits"]["max_sessions_per_account"], 2)


class SlotApiTests(TestCase):
    def setUp(self):
        member = User.objects.create_user(username="member", password="Strong-password-123!")
        other = User.objects.create_user(username="other", password="Strong-password-123!")
        admin = User.objects.create_user(username="slot-admin", password="Strong-password-123!", is_staff=True)
        self.account = make_account("shared@example.com")
        car = ChatgptCar.objects.create(
            car_name="slot-pool", gpt_account_list=[self.account.id],
            created_time=int(time.time()), updated_time=int(time.time()),
        )
        for user in (member, other, admin):
            user.gptcar_list = [car.id]
            user.save(update_fields=["gptcar_list"])
        self.member, self.other, self.admin = member, other, admin
        self.client = APIClient()
        self.client.force_authenticate(user=self.member)

    def test_slot_state_is_none_before_entering_an_account(self):
        response = self.client.get("/0x/chatgpt/slot")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["state"], "none")

    def test_leave_releases_the_seat(self):
        admit("member", self.member, self.account)

        response = self.client.post("/0x/chatgpt/slot", {"action": "leave"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SessionSlot.objects.filter(subject="member").exists())

    def test_unknown_action_is_rejected(self):
        response = self.client.post("/0x/chatgpt/slot", {"action": "jump"}, format="json")
        self.assertEqual(response.status_code, 400)

    @patch("app.chatgpt.views.chatgpt.req_gateway", return_value={"login_url": "https://example.com/chat"})
    def test_login_returns_queued_instead_of_a_url_when_full(self, _gateway):
        set_limits(max_active_sessions=1)
        admit("other", self.other, self.account)

        response = self.client.post(
            "/0x/chatgpt/login", {"chatgpt_id": self.account.id, "login_mode": "api"}, format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["queued"])
        self.assertEqual(response.data["position"], 1)
        self.assertNotIn("login_url", response.data)
        _gateway.assert_not_called()

    @patch("app.chatgpt.views.chatgpt.req_gateway", return_value={"login_url": "https://example.com/chat"})
    def test_login_proceeds_when_a_seat_is_free(self, _gateway):
        response = self.client.post(
            "/0x/chatgpt/login", {"chatgpt_id": self.account.id, "login_mode": "api"}, format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("queued", response.data)
        self.assertEqual(response.data["login_url"], "https://example.com/chat")
        self.assertEqual(slot_state("member")["state"], SessionSlot.STATE_ACTIVE)

    @patch("app.chatgpt.views.chatgpt.req_gateway", return_value={"login_url": "https://example.com/chat"})
    def test_admins_are_not_queued(self, _gateway):
        set_limits(max_active_sessions=1)
        admit("other", self.other, self.account)
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/0x/chatgpt/login", {"chatgpt_id": self.account.id, "login_mode": "api"}, format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("queued", response.data)
        self.assertFalse(SessionSlot.objects.filter(subject="slot-admin").exists())

    def test_occupancy_requires_an_admin(self):
        self.assertEqual(self.client.get("/0x/user/sessions").status_code, 403)

    def test_admin_can_disconnect_a_seat(self):
        admit("member", self.member, self.account)
        self.client.force_authenticate(user=self.admin)

        response = self.client.post("/0x/user/sessions/release", {"subject": "member"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SessionSlot.objects.filter(subject="member").exists())

    def test_disconnecting_an_unknown_seat_is_rejected(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post("/0x/user/sessions/release", {"subject": "ghost"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_limits_require_a_superuser(self):
        self.client.force_authenticate(user=self.admin)
        config = SiteSettings.objects.get_or_create(pk=1)[0]

        response = self.client.put("/0x/user/sessions/limits", {
            "revision": config.revision, "max_active_sessions": 5,
            "max_sessions_per_account": 2, "session_idle_seconds": 600,
        }, format="json")

        self.assertEqual(response.status_code, 403)

    def test_superuser_can_raise_the_cap_and_the_queue_moves(self):
        root = User.objects.create_superuser(username="root", password="Strong-password-123!")
        set_limits(max_active_sessions=1)
        admit("member", self.member, self.account)
        admit("other", self.other, self.account)
        self.client.force_authenticate(user=root)
        config = SiteSettings.objects.get(pk=1)

        response = self.client.put("/0x/user/sessions/limits", {
            "revision": config.revision, "max_active_sessions": 5,
            "max_sessions_per_account": 0, "session_idle_seconds": 900,
        }, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(slot_state("other")["state"], SessionSlot.STATE_ACTIVE)

    def test_stale_revision_is_rejected(self):
        root = User.objects.create_superuser(username="root", password="Strong-password-123!")
        set_limits(max_active_sessions=1)
        self.client.force_authenticate(user=root)

        response = self.client.put("/0x/user/sessions/limits", {
            "revision": 99, "max_active_sessions": 5,
            "max_sessions_per_account": 0, "session_idle_seconds": 900,
        }, format="json")

        self.assertEqual(response.status_code, 400)


class SlotRevocationTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="member", password="Strong-password-123!")
        self.account = make_account("shared@example.com")
        Token.objects.create(user=self.member)

    def test_revoking_a_user_releases_their_seat(self):
        from app.accounts.views import revoke_user_sessions

        admit("member", self.member, self.account)

        revoke_user_sessions(self.member)

        self.assertFalse(SessionSlot.objects.filter(subject="member").exists())
