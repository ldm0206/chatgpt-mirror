import time

from django.test import TestCase
from rest_framework.test import APIClient

from app.accounts.models import User
from app.chatgpt.models import ChatgptAccount


def make_account(username, proxy_node_id=None):
    return ChatgptAccount.objects.create(
        chatgpt_username=username,
        plan_type="plus",
        access_token="token-" + username,
        proxy_node_id=proxy_node_id,
        created_time=int(time.time()),
        updated_time=int(time.time()),
    )


class BatchProxyTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="proxy-admin", password="Strong-password-123!", is_staff=True,
        )
        self.member = User.objects.create_user(username="proxy-member", password="Strong-password-123!")
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.first = make_account("first@example.com", proxy_node_id=1)
        self.second = make_account("second@example.com", proxy_node_id=2)
        self.third = make_account("third@example.com")

    def post(self, payload):
        return self.client.post("/0x/chatgpt/batch-proxy", payload, format="json")

    def test_selected_accounts_move_to_the_requested_node(self):
        response = self.post({"account_ids": [self.first.id, self.third.id], "proxy_node_id": 7})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["updated"], 2)
        self.assertEqual(ChatgptAccount.objects.get(id=self.first.id).proxy_node_id, 7)
        self.assertEqual(ChatgptAccount.objects.get(id=self.third.id).proxy_node_id, 7)
        self.assertEqual(ChatgptAccount.objects.get(id=self.second.id).proxy_node_id, 2)

    def test_apply_to_all_covers_every_account(self):
        response = self.post({"apply_to_all": True, "proxy_node_id": 4})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["updated"], 3)
        self.assertEqual(
            list(ChatgptAccount.objects.values_list("proxy_node_id", flat=True)), [4, 4, 4]
        )

    def test_null_node_restores_direct_connection(self):
        response = self.post({"account_ids": [self.first.id, self.second.id], "proxy_node_id": None})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ChatgptAccount.objects.filter(proxy_node_id__isnull=True).count(), 3)

    def test_empty_selection_without_apply_to_all_is_rejected(self):
        response = self.post({"account_ids": [], "proxy_node_id": 1})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ChatgptAccount.objects.get(id=self.first.id).proxy_node_id, 1)

    def test_unknown_account_ids_change_nothing(self):
        response = self.post({"account_ids": [9999], "proxy_node_id": 5})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["updated"], 0)
        self.assertFalse(ChatgptAccount.objects.filter(proxy_node_id=5).exists())

    def test_requires_an_admin(self):
        self.client.force_authenticate(user=self.member)

        response = self.post({"apply_to_all": True, "proxy_node_id": 3})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ChatgptAccount.objects.filter(proxy_node_id=3).exists())


class ProxyUsageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="usage-admin", password="Strong-password-123!", is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_usage_counts_accounts_per_node_and_reports_direct_ones(self):
        make_account("a@example.com", proxy_node_id=2)
        make_account("b@example.com", proxy_node_id=2)
        make_account("c@example.com", proxy_node_id=9)
        make_account("d@example.com")

        response = self.client.get("/0x/chatgpt/proxy-usage")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["usage"], {"2": 2, "9": 1})
        self.assertEqual(response.data["unassigned"], 1)

    def test_usage_is_empty_without_accounts(self):
        response = self.client.get("/0x/chatgpt/proxy-usage")

        self.assertEqual(response.data["usage"], {})
        self.assertEqual(response.data["unassigned"], 0)
