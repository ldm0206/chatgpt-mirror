from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from app.accounts.authentication import AUTH_COOKIE_NAME
from app.accounts.models import SiteSettings, User, VisitLog
from app.accounts.turnstile import turnstile_settings
from app.settings import ADMIN_USERNAME, FREE_ACCOUNT_USERNAME


STRONG_PASSWORD = "Strong-password-123!"


@override_settings(ALLOWED_HOSTS=["testserver"], CSRF_TRUSTED_ORIGINS=["https://testserver"])
class AdminSetupTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.turnstile = patch(
            "app.accounts.views.login.turnstile_settings",
            new=lambda: {"enabled": False, "site_key": "", "secret_key": "", "source": ""},
        )
        self.turnstile.start()
        self.addCleanup(self.turnstile.stop)

    def csrf(self):
        return self.client.get("/0x/user/version-cfg").data["csrf_token"]

    def setup_post(self, data, csrf=None):
        return self.client.post(
            "/0x/user/setup", data, format="json", HTTP_X_CSRFTOKEN=csrf if csrf is not None else self.csrf(),
        )

    def test_status_reports_needed_until_an_active_superuser_exists(self):
        self.assertTrue(self.client.get("/0x/user/setup-status").data["needed"])
        User.objects.create_superuser(username="root", password=STRONG_PASSWORD)
        self.assertFalse(self.client.get("/0x/user/setup-status").data["needed"])

    def test_inactive_superuser_does_not_count_as_initialized(self):
        User.objects.create_superuser(username="root", password=STRONG_PASSWORD, is_active=False)
        self.assertTrue(self.client.get("/0x/user/setup-status").data["needed"])

    def test_setup_creates_admin_with_configured_username_and_signs_in(self):
        response = self.setup_post({"password": STRONG_PASSWORD, "confirm_password": STRONG_PASSWORD})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["authenticated"])
        self.assertTrue(response.data["is_admin"])
        self.assertEqual(response.data["username"], ADMIN_USERNAME)
        self.assertIn(AUTH_COOKIE_NAME, response.cookies)

        user = User.objects.get(username=ADMIN_USERNAME)
        self.assertTrue(user.is_superuser and user.is_staff and user.is_active)
        self.assertTrue(user.check_password(STRONG_PASSWORD))
        self.assertTrue(Token.objects.filter(user=user).exists())
        self.assertTrue(VisitLog.objects.filter(username=ADMIN_USERNAME, log_type="login").exists())

    def test_setup_is_refused_once_an_admin_exists(self):
        User.objects.create_superuser(username="root", password=STRONG_PASSWORD)

        response = self.setup_post({"password": STRONG_PASSWORD, "confirm_password": STRONG_PASSWORD})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username=ADMIN_USERNAME).exists())

    def test_setup_requires_csrf(self):
        response = self.client.post(
            "/0x/user/setup",
            {"password": STRONG_PASSWORD, "confirm_password": STRONG_PASSWORD},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username=ADMIN_USERNAME).exists())

    def test_setup_rejects_mismatched_confirmation(self):
        response = self.setup_post({"password": STRONG_PASSWORD, "confirm_password": "Other-password-123!"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("confirm_password", response.data)
        self.assertFalse(User.objects.exists())

    def test_setup_rejects_weak_password(self):
        response = self.setup_post({"password": "123456", "confirm_password": "123456"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)
        self.assertFalse(User.objects.exists())

    def test_setup_refuses_when_the_admin_name_is_already_taken(self):
        User.objects.create_user(username=ADMIN_USERNAME, password=STRONG_PASSWORD)

        response = self.setup_post({"password": STRONG_PASSWORD, "confirm_password": STRONG_PASSWORD})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.get(username=ADMIN_USERNAME).is_superuser)

    def test_setup_verifies_turnstile_before_creating_the_admin(self):
        with patch(
            "app.accounts.views.login.turnstile_settings",
            new=lambda: {"enabled": True, "site_key": "site", "secret_key": "secret", "source": "panel"},
        ):
            response = self.setup_post({"password": STRONG_PASSWORD, "confirm_password": STRONG_PASSWORD})

        self.assertEqual(response.status_code, 400)
        self.assertIn("人机验证", str(response.data))
        self.assertFalse(User.objects.exists())


@override_settings(ALLOWED_HOSTS=["testserver"], CSRF_TRUSTED_ORIGINS=["https://testserver"])
class TurnstileSettingsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser(username="root", password=STRONG_PASSWORD)
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def env_enabled(self, enabled=True):
        return patch.multiple(
            "app.accounts.turnstile",
            TURNSTILE_ENABLED=enabled,
            TURNSTILE_SITE_KEY="env-site" if enabled else "",
            TURNSTILE_SECRET_KEY="env-secret" if enabled else "",
        )

    def save(self, payload):
        config = SiteSettings.objects.get_or_create(pk=1)[0]
        return self.client.put(
            "/0x/user/turnstile-config",
            {"revision": config.revision, **payload},
            format="json",
        )

    def test_environment_pair_is_used_when_the_panel_is_empty(self):
        with self.env_enabled():
            config = turnstile_settings()
        self.assertEqual((config["enabled"], config["site_key"], config["source"]), (True, "env-site", "env"))

    def test_panel_pair_overrides_the_environment(self):
        with self.env_enabled():
            response = self.save({"turnstile_site_key": "panel-site", "turnstile_secret_key": "panel-secret"})
            self.assertEqual(response.status_code, 200, response.data)
            config = turnstile_settings()
        self.assertEqual((config["enabled"], config["site_key"], config["secret_key"]), (True, "panel-site", "panel-secret"))
        self.assertEqual(config["source"], "panel")

    def test_clearing_the_site_key_hands_the_pair_back_to_the_environment(self):
        self.save({"turnstile_site_key": "panel-site", "turnstile_secret_key": "panel-secret"})

        with self.env_enabled():
            response = self.save({"turnstile_site_key": ""})
            config = turnstile_settings()

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(config["site_key"], "env-site")
        self.assertEqual(config["source"], "env")
        self.assertEqual(SiteSettings.objects.get(pk=1).turnstile_secret_key, "")

    def test_panel_pair_enables_verification_without_environment_configuration(self):
        with self.env_enabled(False):
            self.save({"turnstile_site_key": "panel-site", "turnstile_secret_key": "panel-secret"})
            config = turnstile_settings()
        self.assertTrue(config["enabled"])

    def test_site_key_without_a_secret_is_rejected(self):
        response = self.save({"turnstile_site_key": "panel-site"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("turnstile_secret_key", response.data)

    def test_existing_secret_is_retained_when_only_the_site_key_changes(self):
        self.save({"turnstile_site_key": "panel-site", "turnstile_secret_key": "panel-secret"})

        response = self.save({"turnstile_site_key": "panel-site-2"})

        self.assertEqual(response.status_code, 200, response.data)
        config = turnstile_settings()
        self.assertEqual((config["site_key"], config["secret_key"]), ("panel-site-2", "panel-secret"))

    def test_stored_secret_is_never_returned(self):
        self.save({"turnstile_site_key": "panel-site", "turnstile_secret_key": "panel-secret"})

        response = self.client.get("/0x/user/turnstile-config")

        self.assertNotIn("panel-secret", str(response.data))
        self.assertTrue(response.data["secret_configured"])
        self.assertEqual(SiteSettings.objects.get(pk=1).turnstile_secret_key, "panel-secret")

    def test_stale_revision_is_rejected(self):
        self.save({"turnstile_site_key": "panel-site", "turnstile_secret_key": "panel-secret"})

        response = self.client.put(
            "/0x/user/turnstile-config",
            {"revision": 0, "turnstile_site_key": "other-site"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(turnstile_settings()["site_key"], "panel-site")

    def test_non_superuser_cannot_read_or_write(self):
        member = User.objects.create_user(username="member", password=STRONG_PASSWORD)
        self.client.force_authenticate(user=member)

        self.assertEqual(self.client.get("/0x/user/turnstile-config").status_code, 403)
        config = SiteSettings.objects.get_or_create(pk=1)[0]
        self.assertEqual(
            self.client.put("/0x/user/turnstile-config", {"revision": config.revision}, format="json").status_code,
            403,
        )

    def test_version_config_exposes_the_panel_site_key(self):
        self.save({"turnstile_site_key": "panel-site", "turnstile_secret_key": "panel-secret"})

        response = APIClient().get("/0x/user/version-cfg")

        self.assertTrue(response.data["turnstile_enabled"])
        self.assertEqual(response.data["turnstile_site_key"], "panel-site")
        self.assertNotIn("panel-secret", str(response.data))

    def test_free_account_username_is_reserved(self):
        self.assertNotEqual(ADMIN_USERNAME, FREE_ACCOUNT_USERNAME)
