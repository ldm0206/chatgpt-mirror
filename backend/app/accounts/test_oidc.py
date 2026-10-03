# -*- coding: utf-8 -*-
import json
from datetime import timedelta
from unittest.mock import Mock, patch
from urllib.parse import parse_qsl, urlsplit

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from app.accounts import oidc
from app.accounts.authentication import AUTH_COOKIE_NAME
from app.accounts.models import GatewayRevocation, OidcFlow, OidcIdentity, SiteSettings, User, VisitLog
from app.accounts.session_authority import GATEWAY_AUTH_COOKIE_NAME, authorization_is_active
from app.settings import ADMIN_USERNAME, FREE_ACCOUNT_USERNAME


ISSUER = "https://idp.example.com"
CLIENT_ID = "mirror-client"
CLIENT_SECRET = "mirror-secret"
DISCOVERY = {
    "issuer": ISSUER,
    "authorization_endpoint": ISSUER + "/authorize",
    "token_endpoint": ISSUER + "/token",
    "jwks_uri": ISSUER + "/jwks",
    "userinfo_endpoint": ISSUER + "/userinfo",
    "id_token_signing_alg_values_supported": ["RS256"],
    "token_endpoint_auth_methods_supported": ["client_secret_post"],
}


def json_response(payload, status=200):
    response = Mock()
    response.status_code = status
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def error_response(status=400):
    response = Mock()
    response.status_code = status
    response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        f"{status} error", response=response,
    )
    return response


class OidcTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        cls.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        cls.jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.nonce = ""
        self.claims = {"preferred_username": "alice", "email": "alice@example.com"}
        self.userinfo = {}
        self.jwks = {"keys": [self.jwk]}
        self.token_requests = []
        self.get_patcher = patch("app.accounts.oidc.requests.get", side_effect=self.fake_get)
        self.post_patcher = patch("app.accounts.oidc.requests.post", side_effect=self.fake_post)
        self.get_patcher.start()
        self.post_patcher.start()
        self.addCleanup(patch.stopall)

    # ---- provider doubles -------------------------------------------------

    def fake_get(self, url, **kwargs):
        if url.endswith("/.well-known/openid-configuration"):
            return json_response(DISCOVERY)
        if url.endswith("/jwks"):
            return json_response(self.jwks)
        if url.endswith("/userinfo"):
            return json_response(self.userinfo)
        raise AssertionError(f"unexpected GET {url}")

    def fake_post(self, url, data=None, headers=None, **kwargs):
        assert url.endswith("/token"), url
        self.token_requests.append({"data": data, "headers": headers})
        return json_response({"id_token": self.make_id_token(), "access_token": "access-token"})

    def make_id_token(self, **overrides):
        now = timezone.now()
        claims = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": "subject-1",
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "iat": int(now.timestamp()),
            "nonce": self.nonce,
            **self.claims,
        }
        claims.update(overrides)
        return jwt.encode(claims, self.private_pem, algorithm="RS256", headers={"kid": "test-key"})

    # ---- helpers ----------------------------------------------------------

    def enable_oidc(self, **overrides):
        values = {
            "oidc_issuer": ISSUER,
            "oidc_client_id": CLIENT_ID,
            "oidc_client_secret": CLIENT_SECRET,
        }
        values.update(overrides)
        SiteSettings.objects.update_or_create(pk=1, defaults=values)

    def start_flow(self):
        response = self.client.get("/0x/user/oidc/login")
        self.assertEqual(response.status_code, 200)
        params = dict(parse_qsl(urlsplit(response.data["authorize_url"]).query))
        # The nonce lives server-side now; read it back the same way the callback does.
        self.nonce = oidc.load_flow(params["state"])["nonce"]
        return {"state": params["state"], "redirect_uri": params["redirect_uri"]}, response

    def callback(self, flow, code="auth-code", state=None, user_agent=None):
        extra = {"HTTP_USER_AGENT": user_agent} if user_agent else {}
        return self.client.get(
            "/0x/user/oidc/callback",
            {"code": code, "state": state if state is not None else flow["state"]},
            **extra,
        )

    def login_through_provider(self):
        flow, _ = self.start_flow()
        return self.callback(flow)


class OidcLoginViewTests(OidcTestCase):
    def test_login_requires_enabled_config(self):
        response = self.client.get("/0x/user/oidc/login")
        self.assertEqual(response.status_code, 400)

    def test_login_registers_the_flow_and_returns_authorize_url(self):
        self.enable_oidc()
        flow, response = self.start_flow()

        authorize_url = response.data["authorize_url"]
        self.assertTrue(authorize_url.startswith(DISCOVERY["authorization_endpoint"] + "?"))
        for fragment in (
            "response_type=code",
            "client_id=" + CLIENT_ID,
            "code_challenge_method=S256",
            "state=",
            "nonce=",
        ):
            self.assertIn(fragment, authorize_url)

        # The flow is stored server-side: no cookie travels through the provider redirect.
        self.assertEqual(OidcFlow.objects.count(), 1)
        self.assertEqual(response.cookies, {})
        self.assertIn("state=" + flow["state"], authorize_url)
        self.assertEqual(flow["redirect_uri"], "http://testserver/0x/user/oidc/callback")

    def test_login_reports_provider_outage(self):
        self.enable_oidc()
        self.get_patcher.stop()
        with patch("app.accounts.oidc.requests.get", side_effect=requests.ConnectionError("down")):
            response = self.client.get("/0x/user/oidc/login")
        self.assertEqual(response.status_code, 400)
        self.assertIn("身份提供方", response.data["message"])


class OidcCallbackStateTests(OidcTestCase):
    def setUp(self):
        super().setUp()
        self.enable_oidc()
        User.objects.create_user(username="alice", password="test-password")

    def test_callback_without_a_state_is_refused(self):
        self.start_flow()
        response = self.client.get("/0x/user/oidc/callback", {"code": "auth-code"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("oidc_error=state", response["Location"])
        self.assertFalse(Token.objects.exists())

    def test_callback_with_unknown_state_is_refused(self):
        self.start_flow()
        response = self.client.get(
            "/0x/user/oidc/callback", {"code": "auth-code", "state": "different"},
        )
        self.assertIn("oidc_error=state", response["Location"])
        self.assertFalse(OidcIdentity.objects.exists())

    def test_callback_with_expired_flow_is_refused(self):
        flow, _ = self.start_flow()
        OidcFlow.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.callback(flow)
        self.assertIn("oidc_error=state", response["Location"])
        self.assertFalse(OidcFlow.objects.exists())

    def test_callback_from_another_browser_is_refused(self):
        flow, _ = self.start_flow()
        response = self.callback(flow, user_agent="OtherBrowser/1.0")
        self.assertIn("oidc_error=state", response["Location"])
        self.assertFalse(OidcIdentity.objects.exists())

    def test_flow_is_single_use(self):
        flow, _ = self.start_flow()
        self.callback(flow, code="bad-code")
        self.assertFalse(OidcFlow.objects.exists())
        response = self.callback(flow)
        self.assertIn("oidc_error=state", response["Location"])

    def test_provider_error_parameter_is_reported(self):
        response = self.client.get("/0x/user/oidc/callback", {"error": "access_denied"})
        self.assertIn("oidc_error=provider", response["Location"])


class OidcIdTokenTests(OidcTestCase):
    def setUp(self):
        super().setUp()
        self.enable_oidc()
        self.config = oidc.oidc_settings()
        self.nonce = "expected-nonce"

    def test_accepts_valid_token(self):
        claims = oidc.verify_id_token(self.config, DISCOVERY, self.make_id_token(), self.nonce)
        self.assertEqual(claims["sub"], "subject-1")

    def test_rejects_wrong_nonce(self):
        with self.assertRaises(oidc.OidcError) as caught:
            oidc.verify_id_token(self.config, DISCOVERY, self.make_id_token(nonce="other"), self.nonce)
        self.assertEqual(caught.exception.code, "token")

    def test_rejects_wrong_audience(self):
        with self.assertRaises(oidc.OidcError):
            oidc.verify_id_token(self.config, DISCOVERY, self.make_id_token(aud="other-client"), self.nonce)

    def test_rejects_expired_token(self):
        expired = int((timezone.now() - timedelta(minutes=10)).timestamp())
        with self.assertRaises(oidc.OidcError):
            oidc.verify_id_token(self.config, DISCOVERY, self.make_id_token(exp=expired), self.nonce)

    def test_trailing_slash_issuer_still_verifies(self):
        # The issuer is compared byte for byte against the token, so the configured value
        # is normalised instead.
        self.enable_oidc(oidc_issuer=ISSUER + "/")
        config = oidc.oidc_settings()
        self.assertEqual(config["issuer"], ISSUER)
        claims = oidc.verify_id_token(config, DISCOVERY, self.make_id_token(), self.nonce)
        self.assertEqual(claims["sub"], "subject-1")

    def test_rejects_algorithm_confusion(self):
        # HS256 is absent from the advertised algorithms, so the header alone disqualifies it.
        forged = jwt.encode({"sub": "subject-1", "nonce": self.nonce}, "secret", algorithm="HS256")
        with self.assertRaises(oidc.OidcError):
            oidc.verify_id_token(self.config, DISCOVERY, forged, self.nonce)

    def test_unknown_kid_refreshes_jwks_once(self):
        self.jwks = {"keys": [dict(self.jwk, kid="stale-key")]}
        calls = {"count": 0}

        def rotating_get(url, **kwargs):
            if url.endswith("/jwks"):
                calls["count"] += 1
                if calls["count"] > 1:
                    return json_response({"keys": [self.jwk]})
                return json_response(self.jwks)
            return self.fake_get(url, **kwargs)

        self.get_patcher.stop()
        with patch("app.accounts.oidc.requests.get", side_effect=rotating_get):
            claims = oidc.verify_id_token(self.config, DISCOVERY, self.make_id_token(), self.nonce)
        self.assertEqual(claims["sub"], "subject-1")
        self.assertEqual(calls["count"], 2)


class OidcUserResolutionTests(OidcTestCase):
    def setUp(self):
        super().setUp()
        self.enable_oidc()

    def test_links_existing_user_by_username_and_issues_session(self):
        user = User.objects.create_user(username="alice", password="test-password")
        self.claims = {"preferred_username": "alice"}

        response = self.login_through_provider()

        self.assertEqual(response["Location"], "/admin/#/login-chatgpt")
        identity = OidcIdentity.objects.get()
        self.assertEqual((identity.issuer, identity.subject), (ISSUER, "subject-1"))
        self.assertEqual(identity.user, user)
        token = Token.objects.get(user=user)
        self.assertEqual(response.cookies[AUTH_COOKIE_NAME].value, token.key)
        gateway_cookie = response.cookies[GATEWAY_AUTH_COOKIE_NAME].value
        self.assertTrue(authorization_is_active(gateway_cookie, "alice"))
        self.assertTrue(VisitLog.objects.filter(username="alice", log_type="login").exists())

        self.client.cookies[AUTH_COOKIE_NAME] = token.key
        me = self.client.get("/0x/user/me")
        self.assertEqual(me.status_code, 200)
        self.assertTrue(me.data["authenticated"])

    def test_token_endpoint_receives_pkce_verifier(self):
        User.objects.create_user(username="alice", password="test-password")
        self.claims = {"preferred_username": "alice"}
        self.login_through_provider()
        self.assertEqual(self.token_requests[0]["data"]["code_verifier"] and True, True)
        self.assertEqual(self.token_requests[0]["data"]["redirect_uri"],
                         "http://testserver/0x/user/oidc/callback")

    def test_privileged_account_is_not_linked_by_default(self):
        User.objects.create_user(
            username=ADMIN_USERNAME, password="test-password", is_staff=True, is_superuser=True,
        )
        self.claims = {"preferred_username": ADMIN_USERNAME}

        response = self.login_through_provider()

        self.assertIn("oidc_error=conflict", response["Location"])
        self.assertFalse(OidcIdentity.objects.exists())
        self.assertFalse(Token.objects.exists())

    def test_privileged_account_links_when_admins_opt_in(self):
        self.enable_oidc(oidc_link_admins=True)
        admin = User.objects.create_user(
            username=ADMIN_USERNAME, password="test-password", is_staff=True, is_superuser=True,
        )
        self.claims = {"preferred_username": ADMIN_USERNAME}

        response = self.login_through_provider()

        self.assertEqual(response["Location"], "/admin/#/account/user")
        self.assertEqual(OidcIdentity.objects.get().user, admin)

    def test_shared_free_account_is_never_linked(self):
        User.objects.create_user(username=FREE_ACCOUNT_USERNAME, password="test-password")
        self.claims = {"preferred_username": FREE_ACCOUNT_USERNAME}

        response = self.login_through_provider()

        self.assertIn("oidc_error=conflict", response["Location"])
        self.assertFalse(OidcIdentity.objects.exists())

    def test_auto_provisions_new_user(self):
        self.claims = {"preferred_username": "newbie", "email": "newbie@example.com"}

        response = self.login_through_provider()

        self.assertEqual(response["Location"], "/admin/#/login-chatgpt")
        user = User.objects.get(username="newbie")
        self.assertTrue(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.gptcar_list, [])
        self.assertEqual(user.remark, "OIDC 自动创建")
        self.assertEqual(OidcIdentity.objects.get().user, user)
        self.assertTrue(Token.objects.filter(user=user).exists())

    def test_provisioned_username_never_lands_on_protected_names(self):
        self.enable_oidc(oidc_auto_link_by_username=False)
        self.claims = {"preferred_username": ADMIN_USERNAME}

        self.login_through_provider()

        user = OidcIdentity.objects.get().user
        self.assertNotEqual(user.username, ADMIN_USERNAME)
        self.assertEqual(user.username, f"{ADMIN_USERNAME}-2")

    def test_auto_provision_disabled_reports_no_account(self):
        self.enable_oidc(oidc_auto_provision=False)
        self.claims = {"preferred_username": "stranger"}

        response = self.login_through_provider()

        self.assertIn("oidc_error=no_account", response["Location"])
        self.assertFalse(User.objects.filter(username="stranger").exists())

    def test_auto_link_disabled_provisions_separate_account(self):
        existing = User.objects.create_user(username="alice", password="test-password")
        self.enable_oidc(oidc_auto_link_by_username=False)
        self.claims = {"preferred_username": "alice"}

        self.login_through_provider()

        identity = OidcIdentity.objects.get()
        self.assertNotEqual(identity.user, existing)
        self.assertEqual(identity.user.username, "alice-2")

    def test_inactive_and_expired_accounts_are_refused_after_linking(self):
        user = User.objects.create_user(username="alice", password="test-password", is_active=False)
        self.claims = {"preferred_username": "alice"}
        response = self.login_through_provider()
        self.assertIn("oidc_error=inactive", response["Location"])
        self.assertTrue(OidcIdentity.objects.filter(user=user).exists())
        self.assertFalse(Token.objects.exists())

        user.is_active = True
        user.expired_date = timezone.localdate() - timedelta(days=1)
        user.save()
        flow, _ = self.start_flow()
        response = self.callback(flow)
        self.assertIn("oidc_error=expired", response["Location"])

    def test_second_login_rotates_the_old_token(self):
        user = User.objects.create_user(username="alice", password="test-password")
        self.claims = {"preferred_username": "alice"}
        self.login_through_provider()
        first_token = Token.objects.get(user=user)

        flow, _ = self.start_flow()
        response = self.callback(flow)

        self.assertNotEqual(response.cookies[AUTH_COOKIE_NAME].value, first_token.key)
        self.assertEqual(Token.objects.filter(user=user).count(), 1)
        self.assertTrue(GatewayRevocation.objects.filter(subject="alice").exists())

    def test_userinfo_fills_missing_profile_claims(self):
        self.claims = {}
        self.userinfo = {"preferred_username": "alice"}

        self.login_through_provider()

        self.assertEqual(OidcIdentity.objects.get().user.username, "alice")

    def test_userinfo_cannot_override_the_signed_subject(self):
        self.claims = {}
        self.userinfo = {"sub": "attacker-subject", "preferred_username": "alice"}

        self.login_through_provider()

        identity = OidcIdentity.objects.get()
        self.assertEqual(identity.subject, "subject-1")
        self.assertEqual(identity.user.username, "alice")

    def test_userinfo_failure_falls_back_to_subject_username(self):
        self.claims = {}
        self.userinfo = {}
        self.get_patcher.stop()

        def failing_get(url, **kwargs):
            if url.endswith("/userinfo"):
                return error_response(500)
            return self.fake_get(url, **kwargs)

        with patch("app.accounts.oidc.requests.get", side_effect=failing_get):
            self.login_through_provider()

        user = OidcIdentity.objects.get().user
        self.assertTrue(user.username.startswith("oidc-"))


class OidcSettingsViewTests(OidcTestCase):
    def setUp(self):
        super().setUp()
        self.superuser = User.objects.create_superuser(username=ADMIN_USERNAME, password="test-password")
        self.member = User.objects.create_user(username="member", password="test-password")

    def authenticate(self, user):
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_requires_superuser(self):
        self.authenticate(self.member)
        self.assertEqual(self.client.get("/0x/user/oidc-config").status_code, 403)

    def test_get_hides_secret_and_reports_source(self):
        self.enable_oidc()
        self.authenticate(self.superuser)
        data = self.client.get("/0x/user/oidc-config").data
        self.assertNotIn("oidc_client_secret", data)
        self.assertTrue(data["secret_configured"])
        self.assertEqual(data["active_source"], "panel")
        self.assertTrue(data["active_enabled"])
        self.assertTrue(data["redirect_uri_suggested"].endswith("/0x/user/oidc/callback"))

    def test_put_saves_and_rejects_stale_revision(self):
        self.enable_oidc()
        self.authenticate(self.superuser)
        current = self.client.get("/0x/user/oidc-config").data["revision"]

        payload = {
            "revision": current,
            "oidc_issuer": ISSUER,
            "oidc_client_id": CLIENT_ID,
            "oidc_display_name": "企业登录",
            "oidc_auto_provision": False,
        }
        saved = self.client.put("/0x/user/oidc-config", payload, format="json")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.data["oidc_display_name"], "企业登录")
        self.assertFalse(SiteSettings.objects.get(pk=1).oidc_auto_provision)
        # The stored secret survives a blank submission.
        self.assertEqual(SiteSettings.objects.get(pk=1).oidc_client_secret, CLIENT_SECRET)

        stale = self.client.put("/0x/user/oidc-config", payload, format="json")
        self.assertEqual(stale.status_code, 400)

    def test_clearing_issuer_hands_provider_back_to_env(self):
        self.enable_oidc()
        self.authenticate(self.superuser)
        current = self.client.get("/0x/user/oidc-config").data["revision"]
        response = self.client.put(
            "/0x/user/oidc-config", {"revision": current, "oidc_issuer": ""}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        settings_row = SiteSettings.objects.get(pk=1)
        self.assertEqual((settings_row.oidc_issuer, settings_row.oidc_client_id), ("", ""))
        self.assertEqual(settings_row.oidc_client_secret, "")
        self.assertFalse(oidc.oidc_settings()["enabled"])

    def test_version_cfg_exposes_public_flags(self):
        data = self.client.get("/0x/user/version-cfg").data
        self.assertFalse(data["oidc_enabled"])
        self.enable_oidc(oidc_display_name="Keycloak")
        data = self.client.get("/0x/user/version-cfg").data
        self.assertTrue(data["oidc_enabled"])
        self.assertEqual(data["oidc_display_name"], "Keycloak")


class OidcHelperTests(TestCase):
    def test_derive_username_prefers_configured_claim(self):
        config = {"username_claim": "upn"}
        self.assertEqual(oidc.derive_username(config, {"upn": "bob.smith"}), "bob.smith")

    def test_derive_username_falls_back_to_email_and_subject(self):
        config = {"username_claim": "preferred_username"}
        self.assertEqual(oidc.derive_username(config, {"email": "carol@example.com"}), "carol")
        fallback = oidc.derive_username(config, {"sub": "opaque-subject"})
        self.assertTrue(fallback.startswith("oidc-"))
        self.assertEqual(len(fallback), 13)

    def test_derive_username_cleans_illegal_characters(self):
        config = {"username_claim": "preferred_username"}
        self.assertEqual(oidc.derive_username(config, {"preferred_username": "bob smi*th"}), "bobsmith")

    def test_unique_username_avoids_existing_and_protected_names(self):
        User.objects.create_user(username="taken", password="test-password")
        self.assertEqual(oidc._unique_username("taken"), "taken-2")
        self.assertEqual(oidc._unique_username(ADMIN_USERNAME), f"{ADMIN_USERNAME}-2")
        self.assertEqual(oidc._unique_username(FREE_ACCOUNT_USERNAME), f"{FREE_ACCOUNT_USERNAME}-2")
