import time
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from app.accounts.management.commands.install_egress_guard import GUARD_MARKER, GUARD_NAME
from app.accounts.models import User, VisitLog
from app.accounts.views.cfg import EgressReportView


def gateway_config(with_guard=False):
    scripts = [
        {"id": 3, "enabled": True, "name": "隐藏横幅", "language": "css",
         "position": "body_end", "content": "#banner{display:none}"},
    ]
    if with_guard:
        scripts.insert(0, {
            "id": 7, "enabled": False, "name": "旧版防护", "language": "javascript",
            "position": "head_end", "content": "(function(){ window." + GUARD_MARKER + " = 1; })();",
        })
    return {
        "scripts": scripts,
        "trusted_cdn_sources": ["https://cdn.example.com/*"],
    }


class InstallEgressGuardTests(TestCase):
    def run_command(self, *args, with_guard=False, **kwargs):
        output = StringIO()
        calls = []

        def fake_req_gateway(method, uri, *call_args, **call_kwargs):
            calls.append((method, uri, call_kwargs.get("json")))
            return gateway_config(with_guard=with_guard)

        patch_target = "app.accounts.management.commands.install_egress_guard.req_gateway"
        with patch(patch_target, side_effect=fake_req_gateway):
            call_command("install_egress_guard", *args, stdout=output, **kwargs)
        return output.getvalue(), calls

    def posted_scripts(self, calls):
        posted = calls[-1][2]
        return posted["scripts"], posted

    def guard_in(self, scripts):
        return next(script for script in scripts if GUARD_MARKER in script["content"])

    def test_install_appends_guard_and_preserves_other_scripts(self):
        output, calls = self.run_command()

        self.assertEqual([call[:2] for call in calls], [
            ("get", "/api/custom-scripts"),
            ("post", "/api/custom-scripts"),
        ])
        scripts, posted = self.posted_scripts(calls)
        guard = self.guard_in(scripts)

        self.assertEqual(guard["name"], GUARD_NAME)
        self.assertEqual(guard["language"], "javascript")
        self.assertEqual(guard["position"], "head_start")
        self.assertTrue(guard["enabled"])
        self.assertEqual(guard["id"], 4)  # 已有最大 id 3，取 +1
        self.assertIn('"cdn.example.com"', guard["content"])
        self.assertIn(GUARD_MARKER, guard["content"])
        # 其他脚本与可信 CDN 源原样保留
        self.assertIn("#banner{display:none}", [script["content"] for script in scripts])
        self.assertEqual(posted["trusted_cdn_sources"], ["https://cdn.example.com/*"])
        self.assertIn("已安装", output)

    def test_reinstall_replaces_existing_guard_in_place(self):
        output, calls = self.run_command(with_guard=True)

        scripts, _ = self.posted_scripts(calls)
        guard = self.guard_in(scripts)

        self.assertEqual(len(scripts), 2)
        self.assertEqual(guard["id"], 7)  # 复用原有 id，不新增
        self.assertEqual(guard["position"], "head_start")
        self.assertNotIn("旧版防护", [script["name"] for script in scripts])
        self.assertIn("已更新", output)

    def test_remove_deletes_only_guard(self):
        output, calls = self.run_command("--remove", with_guard=True)

        scripts, posted = self.posted_scripts(calls)
        self.assertEqual(len(scripts), 1)
        self.assertNotIn(GUARD_MARKER, "".join(script["content"] for script in scripts))
        self.assertEqual(posted["trusted_cdn_sources"], ["https://cdn.example.com/*"])
        self.assertIn("已移除", output)

    def test_remove_without_guard_is_noop(self):
        output, calls = self.run_command("--remove")

        self.assertEqual(len(calls), 1)  # 只有读取，没有写回
        self.assertIn("没有已安装", output)

    def test_dry_run_does_not_write_back(self):
        output, calls = self.run_command("--dry-run")

        self.assertEqual(len(calls), 1)
        self.assertIn("dry-run", output)

    def test_allow_host_joins_builtin_whitelist(self):
        _, calls = self.run_command("--allow-host", "stats.example.org")

        scripts, _ = self.posted_scripts(calls)
        guard = self.guard_in(scripts)
        self.assertIn('"stats.example.org"', guard["content"])
        self.assertIn('"cdn.example.com"', guard["content"])


class EgressReportViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="member", password="Strong-password-123!")
        self.factory = APIRequestFactory()

    def post_events(self, events, authenticate=True):
        request = self.factory.post(
            "/0x/user/egress-report", {"events": events}, format="json",
        )
        if authenticate:
            force_authenticate(request, user=self.user)
        return EgressReportView.as_view()(request)

    def test_records_blocked_targets(self):
        response = self.post_events([
            {"url": "https://cdn.oaistatic.com/assets/app.js", "count": 3},
            {"url": "https://statsig.anthropic-telemetry.example/v1/e", "count": 1},
        ])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["recorded"], 2)
        rows = VisitLog.objects.filter(log_type="egress-blocked").order_by("id")
        self.assertEqual([row.chatgpt_username for row in rows], [
            "cdn.oaistatic.com", "statsig.anthropic-telemetry.example",
        ])
        self.assertTrue(all(row.username == "member" for row in rows))

    def test_dedupes_repeated_targets_within_window(self):
        self.post_events([{"url": "https://cdn.oaistatic.com/a.js", "count": 1}])
        response = self.post_events([
            {"url": "https://cdn.oaistatic.com/b.js", "count": 2},   # 同域名不再记录
            {"url": "https://ab.chatgpt.com/x", "count": 1},         # 新域名正常记录
        ])

        self.assertEqual(response.data["recorded"], 1)
        self.assertEqual(VisitLog.objects.filter(log_type="egress-blocked").count(), 2)

    def test_rejects_bad_payload(self):
        response = self.post_events({"url": "https://cdn.oaistatic.com/a.js"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(VisitLog.objects.filter(log_type="egress-blocked").count(), 0)

    def test_requires_authentication(self):
        response = self.post_events([{"url": "https://cdn.oaistatic.com/a.js"}], authenticate=False)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(VisitLog.objects.filter(log_type="egress-blocked").count(), 0)

    def test_caps_records_per_request(self):
        events = [{"url": f"https://host{i}.example.com/a.js", "count": 1} for i in range(30)]
        response = self.post_events(events)

        self.assertEqual(response.data["recorded"], 10)
        self.assertEqual(VisitLog.objects.filter(log_type="egress-blocked").count(), 10)
