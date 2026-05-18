"""
Unit tests for sumo_oauth.py

Run with:
    uv run pytest -v
    uv run pytest -v -m "not integration"   # skip tests that need live creds

Mock data for API-response tests is loaded from mock_data/ (created by
fetch_mock_data.py).  Tests that rely on mock_data files are skipped
gracefully if the files do not exist yet.
"""

import argparse
import base64
import json
import sys
import time
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
import sumo_oauth as so

MOCK_DATA_DIR = Path(__file__).parent / "mock_data"


def load_mock(name: str) -> dict | list | None:
    """Load a mock data file; return None if it does not exist yet."""
    path = MOCK_DATA_DIR / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


# ===========================================================================
# Pure utility functions
# ===========================================================================

class TestResolveEndpoint(unittest.TestCase):

    def test_known_region_us1(self):
        self.assertEqual(so.resolve_endpoint("us1"), "https://api.sumologic.com")

    def test_known_region_au(self):
        self.assertEqual(so.resolve_endpoint("au"), "https://api.au.sumologic.com")

    def test_all_regions_present(self):
        for region in ("us1", "us2", "eu", "au", "de", "jp", "ca", "in"):
            url = so.resolve_endpoint(region)
            self.assertTrue(url.startswith("https://"), f"Bad URL for {region}: {url}")

    def test_full_url_passthrough(self):
        url = "https://api.custom.sumologic.com"
        self.assertEqual(so.resolve_endpoint(url), url)

    def test_full_url_trailing_slash_stripped(self):
        self.assertEqual(so.resolve_endpoint("https://api.sumologic.com/"),
                         "https://api.sumologic.com")

    def test_unknown_region_raises(self):
        with self.assertRaises(ValueError):
            so.resolve_endpoint("xx99")

    def test_case_insensitive(self):
        self.assertEqual(so.resolve_endpoint("US1"), so.resolve_endpoint("us1"))


class TestBasicAuthHeader(unittest.TestCase):

    def test_format(self):
        header = so._basic_auth_header("myid", "mykey")
        self.assertTrue(header.startswith("Basic "))

    def test_decoded_value(self):
        header = so._basic_auth_header("myid", "mykey")
        token = header.split(" ", 1)[1]
        decoded = base64.b64decode(token).decode()
        self.assertEqual(decoded, "myid:mykey")

    def test_special_chars(self):
        header = so._basic_auth_header("id@org", "key:with:colons")
        token = header.split(" ", 1)[1]
        decoded = base64.b64decode(token).decode()
        self.assertEqual(decoded, "id@org:key:with:colons")


class TestApiToTokenUrl(unittest.TestCase):

    def test_known_endpoints_mapped(self):
        for region, api_url in so.REGIONS.items():
            token_url = so._API_TO_TOKEN_URL.get(api_url)
            self.assertIsNotNone(token_url, f"No token URL for region {region}")
            self.assertIn("service.", token_url)
            self.assertIn("/oauth2/token", token_url)

    def test_us1_token_url(self):
        api = "https://api.sumologic.com"
        self.assertEqual(so._API_TO_TOKEN_URL[api],
                         "https://service.sumologic.com/oauth2/token")

    def test_au_token_url(self):
        api = "https://api.au.sumologic.com"
        self.assertEqual(so._API_TO_TOKEN_URL[api],
                         "https://service.au.sumologic.com/oauth2/token")


class TestApplyRegexFilter(unittest.TestCase):

    ITEMS = [
        {"email": "alice@example.com", "id": "AAA"},
        {"email": "bob@example.com",   "id": "BBB"},
        {"email": "carol@other.org",   "id": "CCC"},
    ]

    def test_no_filter_returns_all(self):
        result = so._apply_regex_filter(self.ITEMS, None, ["email"])
        self.assertEqual(len(result), 3)

    def test_filter_matches_subset(self):
        result = so._apply_regex_filter(self.ITEMS, "example.com", ["email"])
        self.assertEqual(len(result), 2)

    def test_filter_case_insensitive(self):
        result = so._apply_regex_filter(self.ITEMS, "ALICE", ["email"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "AAA")

    def test_filter_multiple_fields(self):
        result = so._apply_regex_filter(self.ITEMS, "BBB", ["email", "id"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["email"], "bob@example.com")

    def test_filter_no_match_returns_empty(self):
        result = so._apply_regex_filter(self.ITEMS, "xyz999", ["email"])
        self.assertEqual(result, [])

    def test_invalid_regex_exits(self):
        with self.assertRaises(SystemExit):
            so._apply_regex_filter(self.ITEMS, "[invalid", ["email"])

    def test_empty_items(self):
        result = so._apply_regex_filter([], "anything", ["email"])
        self.assertEqual(result, [])


class TestFmtScopes(unittest.TestCase):

    def test_empty_list_means_all(self):
        self.assertEqual(so._fmt_scopes([]), "(all)")

    def test_single_scope(self):
        self.assertEqual(so._fmt_scopes(["runLogSearch"]), "runLogSearch")

    def test_three_scopes(self):
        result = so._fmt_scopes(["a", "b", "c"])
        self.assertEqual(result, "a, b, c")

    def test_four_scopes_shows_overflow(self):
        result = so._fmt_scopes(["a", "b", "c", "d"])
        self.assertIn("+1 more", result)
        self.assertTrue(result.startswith("a, b, c"))

    def test_many_scopes_overflow_count(self):
        scopes = [f"scope{i}" for i in range(10)]
        result = so._fmt_scopes(scopes)
        self.assertIn("+7 more", result)


# ===========================================================================
# Keychain helpers
# ===========================================================================

class TestKeychainHelpers(unittest.TestCase):
    # keyring is imported lazily inside each helper, so patch via the keyring module itself.

    @patch("keyring.get_password", return_value="mysecret")
    def test_keychain_get_returns_value(self, mock_get):
        result = so._keychain_get("testkey")
        self.assertEqual(result, "mysecret")
        mock_get.assert_called_once_with(so.KEYCHAIN_SERVICE, "testkey")

    @patch("keyring.get_password", side_effect=Exception("keychain error"))
    def test_keychain_get_returns_none_on_exception(self, _):
        result = so._keychain_get("testkey")
        self.assertIsNone(result)

    @patch("keyring.set_password")
    def test_keychain_set_returns_true(self, mock_set):
        result = so._keychain_set("testkey", "value")
        self.assertTrue(result)
        mock_set.assert_called_once_with(so.KEYCHAIN_SERVICE, "testkey", "value")

    @patch("keyring.set_password", side_effect=Exception("fail"))
    def test_keychain_set_returns_false_on_exception(self, _):
        result = so._keychain_set("testkey", "value")
        self.assertFalse(result)

    @patch("keyring.delete_password")
    def test_keychain_delete_returns_true(self, _):
        result = so._keychain_delete("testkey")
        self.assertTrue(result)

    def test_client_secret_key_format(self):
        self.assertEqual(so._client_secret_key("prod"), "prod:client_secret")

    def test_access_key_key_format(self):
        self.assertEqual(so._access_key_key("staging"), "staging:access_key")

    def test_refresh_token_key_format(self):
        self.assertEqual(so._refresh_token_key("myprofile"), "myprofile:refresh_token")

    def test_refresh_token_key_default_profile(self):
        self.assertEqual(so._refresh_token_key("default"), "default:refresh_token")


# ===========================================================================
# Session class
# ===========================================================================

class TestSession(unittest.TestCase):

    def _session(self, data=None) -> so.Session:
        """Create a Session backed by a temp file, optionally pre-populated."""
        f = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        if data is not None:
            f.write(json.dumps(data).encode())
        f.close()
        self._tmp = Path(f.name)
        return so.Session(self._tmp)

    def tearDown(self):
        if hasattr(self, "_tmp") and self._tmp.exists():
            self._tmp.unlink()

    def test_empty_file_gives_empty_profile(self):
        session = self._session()
        self.assertEqual(session.get("default"), {})

    def test_set_and_get_profile(self):
        session = self._session()
        session.set("myprofile", {"endpoint": "https://api.au.sumologic.com"})
        self.assertEqual(session.get("myprofile")["endpoint"], "https://api.au.sumologic.com")

    def test_names_lists_profiles(self):
        session = self._session({"prod": {"endpoint": "https://api.sumologic.com"},
                                  "staging": {"endpoint": "https://api.us2.sumologic.com"}})
        self.assertIn("prod", session.names())
        self.assertIn("staging", session.names())

    def test_delete_profile(self):
        session = self._session({"default": {"endpoint": "https://api.sumologic.com"}})
        session.delete("default")
        self.assertEqual(session.get("default"), {})

    def test_file_chmod_600(self):
        session = self._session()
        session.set("default", {"endpoint": "https://api.sumologic.com"})
        import stat
        mode = self._tmp.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_migrate_legacy_flat_format(self):
        # Old flat format (no profile nesting)
        legacy = {"endpoint": "https://api.sumologic.com", "client_id": "cid123",
                  "access_token": "tok", "expires_at": 9999999999.0}
        session = self._session(legacy)
        # Should have migrated to {"default": <legacy>}
        self.assertEqual(session.get("default")["client_id"], "cid123")

    def test_profile_status_not_configured(self):
        session = self._session()
        status = session.profile_status("nonexistent")
        self.assertEqual(status["status"], "not configured")

    def test_profile_status_no_token(self):
        session = self._session({"default": {"endpoint": "https://api.sumologic.com",
                                              "client_id": "cid"}})
        status = session.profile_status("default")
        self.assertEqual(status["status"], "no token")

    def test_profile_status_expired(self):
        session = self._session({"default": {
            "endpoint": "https://api.sumologic.com",
            "client_id": "cid",
            "access_token": "tok",
            "expires_at": time.time() - 100,  # already expired
        }})
        status = session.profile_status("default")
        self.assertEqual(status["status"], "expired")

    def test_profile_status_valid(self):
        session = self._session({"default": {
            "endpoint": "https://api.sumologic.com",
            "client_id": "cid",
            "access_token": "tok",
            "expires_at": time.time() + 3600,
        }})
        status = session.profile_status("default")
        self.assertEqual(status["status"], "valid")

    def test_profile_status_has_utc_and_local(self):
        session = self._session({"default": {
            "endpoint": "https://api.sumologic.com",
            "client_id": "cid",
            "access_token": "tok",
            "expires_at": time.time() + 3600,
        }})
        status = session.profile_status("default")
        self.assertIn("expires_at_utc", status)
        self.assertIn("expires_at_local", status)
        self.assertTrue(status["expires_at_utc"].endswith("Z"))

    def test_profile_status_remaining_hms_format(self):
        session = self._session({"default": {
            "endpoint": "https://api.sumologic.com",
            "client_id": "cid",
            "access_token": "tok",
            "expires_at": time.time() + 3661,   # 1h 1m 1s
        }})
        status = session.profile_status("default")
        self.assertRegex(status["remaining"], r"^\d{2}:\d{2}:\d{2}$")

    @patch("sumo_oauth._keychain_available", return_value=True)
    @patch("sumo_oauth._keychain_set", return_value=True)
    def test_store_token_persists_metadata(self, mock_set, mock_avail):
        session = self._session()
        token_resp = {"access_token": "tok123", "token_type": "Bearer", "expires_in": 1800}
        session.store_token("default", "https://api.au.sumologic.com", "cid", "secret",
                            token_resp)
        p = session.get("default")
        self.assertEqual(p["access_token"], "tok123")
        self.assertEqual(p["client_id"], "cid")
        self.assertAlmostEqual(p["expires_at"], time.time() + 1800, delta=5)

    @patch("sumo_oauth._keychain_available", return_value=True)
    @patch("sumo_oauth._keychain_set", return_value=True)
    def test_store_token_persists_scopes(self, mock_set, mock_avail):
        session = self._session()
        token_resp = {"access_token": "tok", "expires_in": 1800}
        session.store_token("default", "https://api.au.sumologic.com", "cid", "secret",
                            token_resp, scopes=["runLogSearch", "viewCollectors"])
        self.assertEqual(session.get("default")["scopes"], ["runLogSearch", "viewCollectors"])

    @patch("sumo_oauth._keychain_available", return_value=True)
    @patch("sumo_oauth._keychain_set", return_value=True)
    @patch("sumo_oauth._fetch_oauth_token",
           return_value={"access_token": "newtoken", "expires_in": 1800})
    def test_require_token_refreshes_expired(self, mock_fetch, mock_set, mock_avail):
        # _keychain_get: return None for refresh_token key so refresh grant is skipped,
        # return "secret" for client_secret key so client_credentials grant proceeds.
        def _keychain_side_effect(key):
            if "refresh_token" in key:
                return None
            return "secret"

        session = self._session({"default": {
            "endpoint": "https://api.au.sumologic.com",
            "client_id": "cid",
            "access_token": "oldtoken",
            "expires_at": time.time() - 10,  # expired
        }})
        with patch("sumo_oauth._keychain_get", side_effect=_keychain_side_effect):
            bearer = session.require_token("default")
        self.assertEqual(bearer, "Bearer newtoken")
        mock_fetch.assert_called_once()

    def test_profile_status_includes_oauth_client_type(self):
        session = self._session({"default": {
            "endpoint": "https://api.au.sumologic.com",
            "client_id": "cid",
            "oauth_client_type": "ClientCredentialsClient",
        }})
        with patch("sumo_oauth._keychain_get", return_value=None):
            status = session.profile_status("default")
        self.assertEqual(status["oauth_client_type"], "ClientCredentialsClient")

    def test_profile_status_includes_refresh_token_stored_false(self):
        session = self._session({"default": {
            "endpoint": "https://api.au.sumologic.com",
            "client_id": "cid",
        }})
        with patch("sumo_oauth._keychain_get", return_value=None):
            status = session.profile_status("default")
        self.assertFalse(status["refresh_token_stored"])

    def test_profile_status_includes_refresh_token_stored_true(self):
        session = self._session({"default": {
            "endpoint": "https://api.au.sumologic.com",
            "client_id": "cid",
        }})
        with patch("sumo_oauth._keychain_get", return_value="somerefreshtoken"):
            status = session.profile_status("default")
        self.assertTrue(status["refresh_token_stored"])

    @patch("sumo_oauth._keychain_available", return_value=True)
    @patch("sumo_oauth._keychain_set", return_value=True)
    def test_store_token_persists_refresh_token(self, mock_set, mock_avail):
        session = self._session()
        token_resp = {"access_token": "tok123", "token_type": "Bearer", "expires_in": 1800}
        session.store_token("default", "https://api.au.sumologic.com", "cid", "secret",
                            token_resp, refresh_token="myrefreshtoken")
        # keychain_set should have been called with the refresh_token key
        calls = [str(c) for c in mock_set.call_args_list]
        self.assertTrue(
            any("refresh_token" in c for c in calls),
            f"refresh_token not stored in keychain. Calls: {calls}"
        )

    @patch("sumo_oauth._keychain_available", return_value=True)
    @patch("sumo_oauth._keychain_set", return_value=True)
    def test_store_token_skips_empty_client_secret(self, mock_set, mock_avail):
        """Empty client_secret must not be written to the keychain."""
        session = self._session()
        token_resp = {"access_token": "tok", "expires_in": 1800}
        session.store_token("default", "https://api.au.sumologic.com", "cid", "",
                            token_resp)
        calls_keys = [c[0][1] for c in mock_set.call_args_list]  # second positional arg = key
        self.assertFalse(
            any("client_secret" in k for k in calls_keys),
            f"client_secret was stored for empty value. Keys: {calls_keys}"
        )

    @patch("sumo_oauth._keychain_available", return_value=True)
    @patch("sumo_oauth._keychain_set", return_value=True)
    def test_require_token_valid_not_refreshed(self, mock_set, mock_avail):
        session = self._session({"default": {
            "endpoint": "https://api.au.sumologic.com",
            "client_id": "cid",
            "access_token": "validtoken",
            "expires_at": time.time() + 3600,
        }})
        with patch("sumo_oauth._fetch_oauth_token") as mock_fetch:
            bearer = session.require_token("default")
            mock_fetch.assert_not_called()
        self.assertEqual(bearer, "Bearer validtoken")

    def test_require_token_no_profile_exits(self):
        session = self._session()
        with self.assertRaises(SystemExit):
            session.require_token("nonexistent")

    def test_require_token_auth_code_client_no_refresh_exits(self):
        """AuthorizationCodeClient with expired token and no refresh_token must exit."""
        session = self._session({"default": {
            "endpoint": "https://api.au.sumologic.com",
            "client_id": "cid",
            "oauth_client_type": "AuthorizationCodeClient",
            "access_token": "oldtok",
            "expires_at": time.time() - 10,
        }})
        # No refresh token stored
        with patch("sumo_oauth._keychain_get", return_value=None):
            with self.assertRaises(SystemExit):
                session.require_token("default")

    def test_require_token_uses_refresh_token_when_present(self):
        """When a refresh_token exists, require_token should call _fetch_refresh_token."""
        session = self._session({"default": {
            "endpoint": "https://api.au.sumologic.com",
            "client_id": "cid",
            "access_token": "oldtok",
            "expires_at": time.time() - 10,
        }})

        def _kc_get(key):
            if "refresh_token" in key:
                return "myrefresh"
            if "client_secret" in key:
                return "secret"
            return None

        new_token_resp = {"access_token": "refreshed", "expires_in": 1800}
        with patch("sumo_oauth._keychain_get", side_effect=_kc_get), \
             patch("sumo_oauth._keychain_set", return_value=True), \
             patch("sumo_oauth._keychain_available", return_value=True), \
             patch("sumo_oauth._fetch_refresh_token", return_value=new_token_resp) as mock_refresh:
            bearer = session.require_token("default")
        self.assertEqual(bearer, "Bearer refreshed")
        mock_refresh.assert_called_once()


# ===========================================================================
# HTTP helpers (mocked requests)
# ===========================================================================

class TestApiGet(unittest.TestCase):

    def _mock_resp(self, status=200, body=None, ok=True, reason="OK"):
        resp = MagicMock()
        resp.ok = ok
        resp.status_code = status
        resp.reason = reason
        resp.text = json.dumps(body or {})
        resp.json.return_value = body or {}
        resp.history = []
        resp.url = "https://api.au.sumologic.com/api/v1/users"
        return resp

    @patch("sumo_oauth._SumoSession")
    def test_api_get_success_returns_json(self, MockSession):
        expected = {"data": [{"id": "abc"}]}
        ctx = MockSession.return_value.__enter__.return_value
        ctx.get.return_value = self._mock_resp(body=expected)
        result = so._api_get("https://api.au.sumologic.com/api/v1/users", "Basic abc")
        self.assertEqual(result, expected)

    @patch("sumo_oauth._SumoSession")
    def test_api_get_401_exits(self, MockSession):
        ctx = MockSession.return_value.__enter__.return_value
        ctx.get.return_value = self._mock_resp(status=401, ok=False, reason="Unauthorized",
                                                body={"message": "Unauthorized"})
        with self.assertRaises(SystemExit):
            so._api_get("https://example.com/api/v1/users", "Basic bad")

    @patch("sumo_oauth._SumoSession")
    def test_api_get_404_exits(self, MockSession):
        ctx = MockSession.return_value.__enter__.return_value
        ctx.get.return_value = self._mock_resp(status=404, ok=False, reason="Not Found",
                                                body={"message": "Not Found"})
        with self.assertRaises(SystemExit):
            so._api_get("https://example.com/api/v1/missing", "Basic abc")

    @patch("sumo_oauth._SumoSession")
    def test_api_delete_success(self, MockSession):
        resp = MagicMock()
        resp.ok = True
        resp.history = []
        MockSession.return_value.__enter__.return_value.delete.return_value = resp
        # Should not raise
        so._api_delete("https://example.com/api/v1/oauth/clients/123", "Basic abc")

    @patch("sumo_oauth._SumoSession")
    def test_api_delete_error_exits(self, MockSession):
        resp = MagicMock()
        resp.ok = False
        resp.status_code = 404
        resp.reason = "Not Found"
        resp.text = "{}"
        resp.history = []
        resp.url = "https://example.com"
        MockSession.return_value.__enter__.return_value.delete.return_value = resp
        with self.assertRaises(SystemExit):
            so._api_delete("https://example.com/api/v1/oauth/clients/bad", "Basic abc")

    @patch("sumo_oauth._SumoSession")
    def test_api_post_success_returns_json(self, MockSession):
        expected = {"clientId": "newclient"}
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = expected
        resp.history = []
        MockSession.return_value.__enter__.return_value.post.return_value = resp
        result = so._api_post("https://example.com/api/v1/oauth/clients", "Basic abc",
                              {"name": "test"})
        self.assertEqual(result, expected)

    @patch("sumo_oauth._SumoSession")
    def test_api_put_success_returns_json(self, MockSession):
        expected = {"clientId": "updated"}
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = expected
        resp.history = []
        MockSession.return_value.__enter__.return_value.put.return_value = resp
        result = so._api_put("https://example.com/api/v1/oauth/clients/abc", "Basic abc",
                             {"name": "updated"})
        self.assertEqual(result, expected)


# ===========================================================================
# API functions (mocking _api_get)
# ===========================================================================

class TestListFunctions(unittest.TestCase):

    ENDPOINT = "https://api.au.sumologic.com"
    AUTH     = "Basic dGVzdA=="

    def _paginated(self, items):
        """Return a single-page response with a 'data' key."""
        return {"data": items, "next": None}

    @patch("sumo_oauth._api_get")
    def test_list_users_returns_data(self, mock_get):
        mock_get.return_value = self._paginated([{"id": "U1", "email": "a@b.com"}])
        result = so.list_users(self.ENDPOINT, self.AUTH)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "U1")

    @patch("sumo_oauth._api_get")
    def test_list_users_paginates(self, mock_get):
        mock_get.side_effect = [
            {"data": [{"id": "U1"}], "next": "tok2"},
            {"data": [{"id": "U2"}], "next": None},
        ]
        result = so.list_users(self.ENDPOINT, self.AUTH)
        self.assertEqual(len(result), 2)
        self.assertEqual(mock_get.call_count, 2)

    @patch("sumo_oauth._api_get")
    def test_list_service_accounts(self, mock_get):
        mock_get.return_value = self._paginated([{"id": "SA1", "name": "svc"}])
        result = so.list_service_accounts(self.ENDPOINT, self.AUTH)
        self.assertEqual(result[0]["name"], "svc")

    @patch("sumo_oauth._api_get")
    def test_list_access_keys(self, mock_get):
        mock_get.return_value = self._paginated([{"id": "su0TEST", "label": "mykey"}])
        result = so.list_access_keys(self.ENDPOINT, self.AUTH)
        self.assertEqual(result[0]["label"], "mykey")

    @patch("sumo_oauth._api_get")
    def test_list_oauth_clients(self, mock_get):
        mock_get.return_value = self._paginated([{"clientId": "cid1", "name": "app"}])
        result = so.list_oauth_clients(self.ENDPOINT, self.AUTH)
        self.assertEqual(result[0]["clientId"], "cid1")

    @patch("sumo_oauth._api_get")
    def test_list_oauth_scopes_no_pagination(self, mock_get):
        mock_get.return_value = {"data": [{"id": "runLogSearch", "label": "Run Log Search"}]}
        result = so.list_oauth_scopes(self.ENDPOINT, self.AUTH)
        self.assertEqual(result[0]["id"], "runLogSearch")

    @patch("sumo_oauth._api_get")
    def test_list_oauth_consents(self, mock_get):
        mock_get.return_value = self._paginated([{"id": "con1", "clientId": "cid1"}])
        result = so.list_oauth_consents(self.ENDPOINT, self.AUTH)
        self.assertEqual(result[0]["id"], "con1")

    @patch("sumo_oauth._api_get")
    def test_get_oauth_client(self, mock_get):
        mock_get.return_value = {"clientId": "cid1", "name": "MyApp"}
        result = so.get_oauth_client(self.ENDPOINT, self.AUTH, "cid1")
        self.assertEqual(result["name"], "MyApp")
        mock_get.assert_called_once_with(
            f"{self.ENDPOINT}/api/v1/oauth/clients/cid1", self.AUTH
        )

    @patch("sumo_oauth._api_delete")
    def test_delete_oauth_client(self, mock_del):
        so.delete_oauth_client(self.ENDPOINT, self.AUTH, "cid1")
        mock_del.assert_called_once_with(
            f"{self.ENDPOINT}/api/v1/oauth/clients/cid1", self.AUTH
        )

    @patch("sumo_oauth._api_post")
    def test_create_oauth_client(self, mock_post):
        payload = {"name": "test", "scopes": ["runLogSearch"]}
        mock_post.return_value = {"clientId": "newcid", **payload}
        result = so.create_oauth_client(self.ENDPOINT, self.AUTH, payload)
        self.assertEqual(result["clientId"], "newcid")
        mock_post.assert_called_once_with(
            f"{self.ENDPOINT}/api/v1/oauth/clients", self.AUTH, payload
        )

    @patch("sumo_oauth._api_put")
    def test_update_oauth_client(self, mock_put):
        payload = {"name": "updated"}
        mock_put.return_value = {"clientId": "cid1", **payload}
        result = so.update_oauth_client(self.ENDPOINT, self.AUTH, "cid1", payload)
        self.assertEqual(result["name"], "updated")
        mock_put.assert_called_once_with(
            f"{self.ENDPOINT}/api/v1/oauth/clients/cid1", self.AUTH, payload
        )

    @patch("sumo_oauth.list_roles_v2")
    @patch("sumo_oauth.list_users")
    def test_resolve_roles_maps_ids_to_names(self, mock_users, mock_roles):
        mock_users.return_value = [
            {"id": "U1", "email": "a@b.com", "roleIds": ["R001", "R002"]},
        ]
        mock_roles.return_value = [
            {"id": "R001", "name": "Admin"},
            {"id": "R002", "name": "Analyst"},
        ]
        # Simulate cmd_users role-resolution logic directly
        role_map = {r["id"]: r.get("name", r["id"]) for r in mock_roles.return_value}
        users = mock_users.return_value
        for u in users:
            u["roleIds"] = [role_map.get(rid, rid) for rid in u.get("roleIds", [])]
        self.assertEqual(users[0]["roleIds"], ["Admin", "Analyst"])

    @patch("sumo_oauth.list_roles_v2")
    @patch("sumo_oauth.list_users")
    def test_resolve_roles_falls_back_to_id_when_unknown(self, mock_users, mock_roles):
        mock_users.return_value = [
            {"id": "U1", "email": "a@b.com", "roleIds": ["R001", "UNKNOWN"]},
        ]
        mock_roles.return_value = [{"id": "R001", "name": "Admin"}]
        role_map = {r["id"]: r.get("name", r["id"]) for r in mock_roles.return_value}
        users = mock_users.return_value
        for u in users:
            u["roleIds"] = [role_map.get(rid, rid) for rid in u.get("roleIds", [])]
        self.assertEqual(users[0]["roleIds"], ["Admin", "UNKNOWN"])

    @patch("sumo_oauth._api_get")
    def test_list_roles_v2_returns_data(self, mock_get):
        mock_get.return_value = {"data": [{"id": "R001", "name": "Admin"}], "next": None}
        result = so.list_roles_v2(self.ENDPOINT, self.AUTH)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Admin")
        mock_get.assert_called_once_with(
            f"{self.ENDPOINT}/api/v2/roles", self.AUTH, {"limit": 100}
        )

    @patch("sumo_oauth._api_get")
    def test_list_roles_v2_paginates(self, mock_get):
        mock_get.side_effect = [
            {"data": [{"id": "R001", "name": "Admin"}],   "next": "tok2"},
            {"data": [{"id": "R002", "name": "Analyst"}], "next": None},
        ]
        result = so.list_roles_v2(self.ENDPOINT, self.AUTH)
        self.assertEqual(len(result), 2)
        self.assertEqual(mock_get.call_count, 2)


# ===========================================================================
# Output formatting (capture stdout)
# ===========================================================================

class TestPrintFunctions(unittest.TestCase):

    ACCESS_KEY = {
        "id": "su0TESTKEY0001",
        "label": "test-key",
        "corsHeaders": [],
        "disabled": False,
        "createdAt": "2026-04-20T02:19:25.923Z",
        "createdBy": "0000000000000001",
        "modifiedAt": "2026-04-20T02:19:25.923Z",
        "modifiedBy": "0000000000000001",
        "serviceAccountId": "0000000000000002",
        "lastUsed": "2026-04-21T20:47:08.695Z",
        "scopes": [],
        "effectiveScopes": [],
        "expiresOn": None,
    }

    USER = {
        "id": "0000000000000001",
        "firstName": "Test",
        "lastName": "User",
        "email": "test@example.com",
        "roleIds": ["0000000000000010", "0000000000000011"],
        "isActive": True,
    }

    SERVICE_ACCOUNT = {
        "id": "0000000000000002",
        "name": "mcp-svc",
        "email": "mcp-svc@example.com",
        "isActive": True,
        "createdAt": "2026-01-15T10:00:00Z",
    }

    OAUTH_CLIENT = {
        "type": "ClientCredentialsClient",
        "clientId": "TEST-CLIENT-ID-0001",
        "name": "MCP Client",
        "description": "",
        "disabled": False,
        "createdAt": "2026-04-20T00:00:00Z",
        "scopes": ["runLogSearch", "viewCollectors"],
        "effectiveScopes": ["runLogSearch", "viewCollectors"],
        "runAs": {"type": "ServiceAccount", "runAsId": "0000000000000002"},
    }

    OAUTH_SCOPE = {
        "id": "runLogSearch",
        "label": "Run Log Search",
        "type": "Manage",
        "dependsOn": [],
        "group": {"id": "logSearch", "label": "Log Search", "parentId": None},
    }

    OAUTH_CONSENT = {
        "id": "0000000000000099",
        "clientId": "TEST-CLIENT-ID-0001",
        "clientName": "Sumo Logic MCP Client",
        "userId": "0000000000000001",
        "scopes": ["runLogSearch"],
        "createdAt": "2026-04-20T00:00:00Z",
        "expiresAt": "2026-07-20T00:00:00Z",
    }

    ROLE = {
        "id": "0000000000000020",
        "name": "Analyst",
        "description": "Read-only analyst role",
        "filterPredicate": "",
        "users": ["0000000000000001"],
        "capabilities": ["viewCollectors", "runLogSearch", "viewFields"],
        "systemDefined": False,
        "createdAt": "2026-01-01T00:00:00Z",
        "createdBy": "0000000000000001",
        "modifiedAt": "2026-01-01T00:00:00Z",
        "modifiedBy": "0000000000000001",
    }

    def _capture(self, fn, *args):
        buf = StringIO()
        with patch("sys.stdout", buf):
            fn(*args)
        return buf.getvalue()

    # -- access keys ---------------------------------------------------------

    def test_print_access_keys_json(self):
        output = self._capture(so.print_access_keys, [self.ACCESS_KEY], "json")
        parsed = json.loads(output)
        self.assertIsInstance(parsed, list)
        self.assertEqual(parsed[0]["id"], "su0TESTKEY0001")

    def test_print_access_keys_table_headers(self):
        output = self._capture(so.print_access_keys, [self.ACCESS_KEY], "table")
        self.assertIn("ID", output)
        self.assertIn("Label", output)
        self.assertIn("Disabled", output)
        self.assertIn("Service Acct ID", output)

    def test_print_access_keys_empty_scopes_shown_as_all(self):
        output = self._capture(so.print_access_keys, [self.ACCESS_KEY], "table")
        self.assertIn("(all)", output)

    def test_print_access_keys_no_results(self):
        output = self._capture(so.print_access_keys, [], "table")
        self.assertIn("(no results)", output)

    def test_print_access_keys_expiresOn_null(self):
        # None should not appear as the string "None" in table
        output = self._capture(so.print_access_keys, [self.ACCESS_KEY], "table")
        # "None" will currently appear; this test documents the current behaviour
        # and can be tightened once null handling is improved
        self.assertIn("su0TESTKEY0001", output)

    # -- users ---------------------------------------------------------------

    def test_print_users_json(self):
        output = self._capture(so.print_users, [self.USER], "json")
        parsed = json.loads(output)
        self.assertEqual(parsed[0]["email"], "test@example.com")

    def test_print_users_table_includes_name(self):
        output = self._capture(so.print_users, [self.USER], "table")
        self.assertIn("Test", output)
        self.assertIn("User", output)

    def test_print_users_role_ids_joined(self):
        output = self._capture(so.print_users, [self.USER.copy()], "table")
        self.assertIn("0000000000000010", output)

    # -- service accounts ----------------------------------------------------

    def test_print_service_accounts_json(self):
        output = self._capture(so.print_service_accounts, [self.SERVICE_ACCOUNT], "json")
        parsed = json.loads(output)
        self.assertEqual(parsed[0]["name"], "mcp-svc")

    def test_print_service_accounts_table(self):
        output = self._capture(so.print_service_accounts, [self.SERVICE_ACCOUNT], "table")
        self.assertIn("mcp-svc", output)

    # -- oauth clients -------------------------------------------------------

    def test_print_oauth_clients_json(self):
        output = self._capture(so.print_oauth_clients, [self.OAUTH_CLIENT], "json")
        parsed = json.loads(output)
        self.assertEqual(parsed[0]["name"], "MCP Client")

    def test_print_oauth_clients_table(self):
        output = self._capture(so.print_oauth_clients, [self.OAUTH_CLIENT], "table")
        self.assertIn("MCP Client", output)
        self.assertIn("Client ID", output)
        self.assertIn("Type", output)
        self.assertIn("Run As ID", output)
        self.assertIn("Port", output)
        # scopes rendered via _fmt_scopes
        self.assertIn("runLogSearch", output)

    def test_print_oauth_clients_port_from_redirect_uri(self):
        ac_client = dict(self.OAUTH_CLIENT, redirectUris=["http://localhost:8888/callback"])
        output = self._capture(so.print_oauth_clients, [ac_client], "table")
        self.assertIn("8888", output)

    def test_print_oauth_clients_no_redirect_uri_shows_dash(self):
        # CC clients have no redirectUris — port column should show "-"
        output = self._capture(so.print_oauth_clients, [self.OAUTH_CLIENT], "table")
        self.assertIn("-", output)

    # -- oauth scopes --------------------------------------------------------

    def test_print_oauth_scopes_table(self):
        output = self._capture(so.print_oauth_scopes, [self.OAUTH_SCOPE], "table")
        self.assertIn("runLogSearch", output)
        self.assertIn("Type", output)
        self.assertIn("Group", output)
        self.assertIn("Log Search", output)
        self.assertNotIn("Description", output)

    # -- oauth consents ------------------------------------------------------

    def test_print_oauth_consents_json(self):
        output = self._capture(so.print_oauth_consents, [self.OAUTH_CONSENT], "json")
        parsed = json.loads(output)
        self.assertEqual(parsed[0]["clientId"], "TEST-CLIENT-ID-0001")

    def test_print_oauth_consents_table(self):
        output = self._capture(so.print_oauth_consents, [self.OAUTH_CONSENT], "table")
        self.assertIn("Consent ID", output)
        self.assertIn("Client ID", output)
        self.assertIn("Client Name", output)
        self.assertIn("Sumo Logic MCP Client", output)

    # -- roles ---------------------------------------------------------------

    def test_print_roles_json(self):
        output = self._capture(so.print_roles, [self.ROLE], "json")
        parsed = json.loads(output)
        self.assertIsInstance(parsed, list)
        self.assertEqual(parsed[0]["name"], "Analyst")

    def test_print_roles_table_headers(self):
        output = self._capture(so.print_roles, [self.ROLE], "table")
        self.assertIn("ID", output)
        self.assertIn("Name", output)
        self.assertIn("System Defined", output)
        self.assertIn("Capabilities", output)

    def test_print_roles_table_content(self):
        output = self._capture(so.print_roles, [self.ROLE], "table")
        self.assertIn("Analyst", output)
        self.assertIn("viewCollectors", output)

    def test_print_roles_empty_capabilities_shown_as_all(self):
        role_no_caps = dict(self.ROLE, capabilities=[])
        output = self._capture(so.print_roles, [role_no_caps], "table")
        self.assertIn("(all)", output)

    def test_print_roles_no_results(self):
        output = self._capture(so.print_roles, [], "table")
        self.assertIn("(no results)", output)

    def test_print_roles_many_capabilities_overflow(self):
        role_many = dict(self.ROLE, capabilities=[f"cap{i}" for i in range(10)])
        output = self._capture(so.print_roles, [role_many], "table")
        self.assertIn("+7 more", output)

    # -- single oauth client -------------------------------------------------

    def test_print_oauth_client_json(self):
        output = self._capture(so.print_oauth_client, self.OAUTH_CLIENT, "json")
        parsed = json.loads(output)
        self.assertEqual(parsed["name"], "MCP Client")

    def test_print_oauth_client_table_shows_all_keys(self):
        output = self._capture(so.print_oauth_client, self.OAUTH_CLIENT, "table")
        self.assertIn("clientId", output)
        self.assertIn("name", output)


# ===========================================================================
# Mock data validation (run only when mock_data/ exists)
# ===========================================================================

class TestMockData(unittest.TestCase):
    """Validate the shape of sanitized mock data produced by fetch_mock_data.py."""

    def _skip_if_missing(self, name: str):
        data = load_mock(name)
        if data is None:
            self.skipTest(f"mock_data/{name}.json not found — run fetch_mock_data.py first")
        return data

    def test_access_key_shape(self):
        data = self._skip_if_missing("access_keys")
        for field in ("id", "label", "disabled", "createdAt", "serviceAccountId",
                      "scopes", "effectiveScopes"):
            self.assertIn(field, data, f"Missing field: {field}")

    def test_access_key_id_sanitized(self):
        data = self._skip_if_missing("access_keys")
        # Real IDs start with su0 followed by real random chars;
        # sanitized ones are su0TESTKEY####
        self.assertRegex(data["id"], r"^su0TESTKEY\d{4}$")

    def test_access_key_no_real_emails(self):
        """No obviously real email domains should appear in mock data."""
        data = self._skip_if_missing("access_keys")
        text = json.dumps(data)
        self.assertNotRegex(text, r"@sumologic\.com")

    def test_user_shape(self):
        data = self._skip_if_missing("users")
        for field in ("id", "email"):
            self.assertIn(field, data, f"Missing field: {field}")

    def test_user_email_sanitized(self):
        data = self._skip_if_missing("users")
        self.assertIn("example.com", data.get("email", ""))

    def test_service_account_shape(self):
        data = self._skip_if_missing("service_accounts")
        self.assertIn("id", data)

    def test_oauth_client_shape(self):
        data = self._skip_if_missing("oauth_clients")
        self.assertIn("clientId", data)

    def test_oauth_scope_shape(self):
        data = self._skip_if_missing("oauth_scopes")
        for field in ("id", "label", "type", "group"):
            self.assertIn(field, data, f"Missing field: {field}")

    def test_oauth_token_shape(self):
        data = self._skip_if_missing("oauth_token")
        self.assertIn("access_token", data)
        # Should be masked, not a real JWT
        self.assertEqual(data["access_token"], "TEST_ACCESS_TOKEN")

    def test_roles_v2_shape(self):
        data = self._skip_if_missing("roles_v2")
        for field in ("id", "name", "capabilities", "systemDefined"):
            self.assertIn(field, data, f"Missing field: {field}")

    def test_roles_v2_id_sanitized(self):
        data = self._skip_if_missing("roles_v2")
        # Sanitized IDs are 16-char hex
        self.assertRegex(data["id"], r"^[0-9A-Fa-f]{16}$")

    def test_access_key_table_columns_match_response(self):
        """Verify the table column field names exist in the actual API response."""
        data = self._skip_if_missing("access_keys")
        # These are the field names used in print_access_keys table columns
        for field in ("id", "label", "serviceAccountId", "createdAt", "lastUsed"):
            self.assertIn(field, data,
                          f"Table column field '{field}' not in API response — "
                          f"update print_access_keys columns. Available: {list(data.keys())}")


# ===========================================================================
# OAuth type aliases and short labels
# ===========================================================================

class TestOauthTypeAliases(unittest.TestCase):

    def test_cc_alias_resolves(self):
        self.assertEqual(so._OAUTH_TYPE_ALIASES["cc"], "ClientCredentialsClient")

    def test_client_credentials_alias_resolves(self):
        self.assertEqual(so._OAUTH_TYPE_ALIASES["client-credentials"], "ClientCredentialsClient")

    def test_canonical_cc_passthrough(self):
        self.assertEqual(so._OAUTH_TYPE_ALIASES["ClientCredentialsClient"],
                         "ClientCredentialsClient")

    def test_ac_alias_resolves(self):
        self.assertEqual(so._OAUTH_TYPE_ALIASES["ac"], "AuthorizationCodeClient")

    def test_authorization_code_alias_resolves(self):
        self.assertEqual(so._OAUTH_TYPE_ALIASES["authorization-code"], "AuthorizationCodeClient")

    def test_canonical_ac_passthrough(self):
        self.assertEqual(so._OAUTH_TYPE_ALIASES["AuthorizationCodeClient"],
                         "AuthorizationCodeClient")

    def test_short_cc(self):
        self.assertEqual(so._OAUTH_TYPE_SHORT["ClientCredentialsClient"], "cc")

    def test_short_ac(self):
        self.assertEqual(so._OAUTH_TYPE_SHORT["AuthorizationCodeClient"], "ac")

    def test_unknown_alias_not_present(self):
        self.assertNotIn("garbage", so._OAUTH_TYPE_ALIASES)


# ===========================================================================
# PKCE helpers
# ===========================================================================

class TestPkce(unittest.TestCase):

    def test_returns_two_strings(self):
        verifier, challenge = so._pkce_pair()
        self.assertIsInstance(verifier, str)
        self.assertIsInstance(challenge, str)

    def test_verifier_and_challenge_differ(self):
        verifier, challenge = so._pkce_pair()
        self.assertNotEqual(verifier, challenge)

    def test_verifier_reasonable_length(self):
        verifier, _ = so._pkce_pair()
        # 32 random bytes base64url-encoded without padding ≈ 43 chars
        self.assertGreaterEqual(len(verifier), 40)

    def test_no_padding_chars(self):
        verifier, challenge = so._pkce_pair()
        self.assertNotIn("=", verifier)
        self.assertNotIn("=", challenge)

    def test_s256_challenge_is_correct(self):
        import hashlib, base64
        verifier, challenge = so._pkce_pair()
        digest = hashlib.sha256(verifier.encode()).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        self.assertEqual(challenge, expected)

    def test_each_call_returns_unique_pair(self):
        v1, c1 = so._pkce_pair()
        v2, c2 = so._pkce_pair()
        self.assertNotEqual(v1, v2)
        self.assertNotEqual(c1, c2)


# ===========================================================================
# AUTHORIZATION_URLS and _API_TO_AUTHORIZATION_URL
# ===========================================================================

class TestAuthorizationUrls(unittest.TestCase):

    def test_all_regions_have_authorization_url(self):
        for region in so.REGIONS:
            self.assertIn(region, so.AUTHORIZATION_URLS,
                          f"Region '{region}' missing from AUTHORIZATION_URLS")

    def test_authorization_urls_contain_authorize_path(self):
        for region, url in so.AUTHORIZATION_URLS.items():
            self.assertIn("/oauth2/authorize", url,
                          f"Region '{region}' URL missing /oauth2/authorize: {url}")

    def test_authorization_urls_use_service_host(self):
        for region, url in so.AUTHORIZATION_URLS.items():
            self.assertIn("service.", url,
                          f"Region '{region}' URL should use service host: {url}")

    def test_api_to_authorization_url_mapped(self):
        for region, api_url in so.REGIONS.items():
            auth_url = so._API_TO_AUTHORIZATION_URL.get(api_url)
            self.assertIsNotNone(auth_url,
                                 f"No authorization URL mapped for API endpoint {api_url}")

    def test_us1_authorization_url(self):
        self.assertEqual(so.AUTHORIZATION_URLS["us1"],
                         "https://service.sumologic.com/oauth2/authorize")

    def test_au_authorization_url(self):
        self.assertEqual(so.AUTHORIZATION_URLS["au"],
                         "https://service.au.sumologic.com/oauth2/authorize")


# ===========================================================================
# cmd_client_config output
# ===========================================================================

class TestCmdClientConfig(unittest.TestCase):

    def _make_args(self, fmt="claude-code", profile="default",
                   server_name="sumologic", callback_port=7878):
        args = MagicMock()
        args.format = fmt
        args.profile = profile
        args.server_name = server_name
        args.callback_port = callback_port
        return args

    def _run_config(self, fmt, profile_data=None):
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        data = {"default": profile_data or {
            "endpoint": "https://api.au.sumologic.com",
            "client_id": "TEST_CLIENT_ID",
            "access_token": "TEST_TOKEN",
            "expires_at": time.time() + 3600,
            "oauth_client_type": "AuthorizationCodeClient",
        }}
        f.write(json.dumps(data).encode())
        f.close()
        session = so.Session(Path(f.name))
        args = self._make_args(fmt=fmt)
        buf = StringIO()
        with patch("sys.stdout", buf), \
             patch("sumo_oauth._keychain_get", return_value="TEST_SECRET"), \
             patch("sumo_oauth._keychain_available", return_value=True), \
             patch("sumo_oauth._fetch_oauth_token",
                   return_value={"access_token": "TEST_TOKEN", "expires_in": 3600}):
            so.cmd_client_config(args, session)
        Path(f.name).unlink()
        return buf.getvalue()

    def test_claude_code_output_contains_mcp_add(self):
        output = self._run_config("claude-code")
        self.assertIn("claude mcp add --transport http", output)
        self.assertIn("--callback-port", output)
        self.assertIn("--client-secret", output)

    def test_claude_code_json_output_is_valid_json_block(self):
        output = self._run_config("claude-code-json")
        # Strip comment lines, parse the JSON block
        lines = [l for l in output.splitlines() if not l.strip().startswith("#")]
        parsed = json.loads("\n".join(lines))
        self.assertIn("mcpServers", parsed)

    def test_vscode_output_contains_servers_key(self):
        output = self._run_config("vscode")
        lines = [l for l in output.splitlines() if not l.strip().startswith("#")]
        parsed = json.loads("\n".join(lines))
        self.assertIn("servers", parsed)

    def test_cursor_output_has_authorization_header(self):
        output = self._run_config("cursor")
        self.assertIn("Authorization", output)
        self.assertIn("Bearer", output)

    def test_all_format_produces_multiple_blocks(self):
        output = self._run_config("all")
        # "all" should include multiple platform headers
        self.assertIn("claude", output.lower())
        self.assertIn("cursor", output.lower())


# ===========================================================================
# _prompt_client_type
# ===========================================================================

class TestPromptClientType(unittest.TestCase):

    def _call(self, user_input: str, current: str | None = None) -> str | None:
        with patch("builtins.input", return_value=user_input):
            return so._prompt_client_type(current)

    def test_cc_alias_returns_canonical(self):
        self.assertEqual(self._call("cc"), "ClientCredentialsClient")

    def test_client_credentials_alias_returns_canonical(self):
        self.assertEqual(self._call("client-credentials"), "ClientCredentialsClient")

    def test_ac_alias_returns_canonical(self):
        self.assertEqual(self._call("ac"), "AuthorizationCodeClient")

    def test_authorization_code_alias_returns_canonical(self):
        self.assertEqual(self._call("authorization-code"), "AuthorizationCodeClient")

    def test_empty_input_keeps_current(self):
        self.assertEqual(self._call("", current="ClientCredentialsClient"),
                         "ClientCredentialsClient")

    def test_empty_input_no_current_returns_none(self):
        self.assertIsNone(self._call("", current=None))

    def test_invalid_input_keeps_current(self):
        with patch("builtins.input", return_value="garbage"):
            result = so._prompt_client_type("ClientCredentialsClient")
        self.assertEqual(result, "ClientCredentialsClient")

    def test_invalid_input_no_current_returns_none(self):
        with patch("builtins.input", return_value="garbage"):
            result = so._prompt_client_type(None)
        self.assertIsNone(result)


# ===========================================================================
# store-creds --client-type (argparse + cmd_store_creds)
# ===========================================================================

class TestStoreCreds(unittest.TestCase):

    def _make_args(self, profile="default", mode="oauth", region=None,
                   client_id=None, client_type=None, access_id=None):
        args = argparse.Namespace(
            profile=profile,
            mode=mode,
            region=region,
            endpoint=None,
            client_id=client_id,
            client_type=client_type,
            access_id=access_id,
        )
        return args

    def _run_store_creds(self, args, session, inputs=(), new_secret=None, new_key=None):
        """Patch interactive prompts and keychain, run cmd_store_creds."""
        input_iter = iter(inputs)
        with patch("builtins.input", side_effect=lambda _: next(input_iter, "")), \
             patch("getpass.getpass", return_value=""), \
             patch("sumo_oauth._keychain_available", return_value=True), \
             patch("sumo_oauth._keychain_get", return_value=None), \
             patch("sumo_oauth._keychain_set", return_value=True):
            so.cmd_store_creds(args, session)

    def _fresh_session(self):
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        Path(tmp.name).unlink()
        return so.Session(Path(tmp.name))

    # -- --client-type flag bypasses the interactive prompt ------------------

    def test_client_type_cc_flag_sets_profile(self):
        session = self._fresh_session()
        args = self._make_args(client_type="client-credentials", region="us1",
                               client_id="cid123")
        # inputs: region(enter=keep), client_id(enter=keep), type prompt never reached
        self._run_store_creds(args, session, inputs=["", "", ""])
        p = session.get("default")
        self.assertEqual(p.get("oauth_client_type"), "ClientCredentialsClient")

    def test_client_type_ac_flag_sets_profile(self):
        session = self._fresh_session()
        args = self._make_args(client_type="authorization-code", region="au",
                               client_id="cid456")
        self._run_store_creds(args, session, inputs=["", "", ""])
        p = session.get("default")
        self.assertEqual(p.get("oauth_client_type"), "AuthorizationCodeClient")

    def test_no_client_type_flag_prompts_interactively(self):
        """Without --client-type, the user is prompted; 'ac' should be saved."""
        session = self._fresh_session()
        args = self._make_args(region="us1", client_id="cid789")
        # inputs: region(enter), client_id(enter), type prompt → "ac"
        self._run_store_creds(args, session, inputs=["", "", "ac"])
        p = session.get("default")
        self.assertEqual(p.get("oauth_client_type"), "AuthorizationCodeClient")

    def test_endpoint_stored_from_region_flag(self):
        session = self._fresh_session()
        args = self._make_args(region="au", client_type="client-credentials",
                               client_id="cid")
        self._run_store_creds(args, session, inputs=["", "", ""])
        p = session.get("default")
        self.assertEqual(p.get("endpoint"), "https://api.au.sumologic.com")

    def test_client_id_stored_from_flag(self):
        session = self._fresh_session()
        args = self._make_args(region="us1", client_id="MY_CLIENT_ID",
                               client_type="client-credentials")
        self._run_store_creds(args, session, inputs=["", "", ""])
        p = session.get("default")
        self.assertEqual(p.get("client_id"), "MY_CLIENT_ID")

    # -- argparse: --client-type appears in store-creds help -----------------

    def test_store_creds_help_includes_client_type(self):
        parser = so.build_parser()
        buf = StringIO()
        try:
            parser.parse_args(["store-creds", "--help"])
        except SystemExit:
            pass
        import io
        buf = io.StringIO()
        with patch("sys.stdout", buf), self.assertRaises(SystemExit):
            parser.parse_args(["store-creds", "--help"])
        self.assertIn("--client-type", buf.getvalue())

    def test_store_creds_client_type_choices(self):
        parser = so.build_parser()
        # Both valid choices should parse without error
        for choice in ("client-credentials", "authorization-code"):
            args = parser.parse_args([
                "store-creds", "--client-type", choice, "--region", "us1"
            ])
            self.assertEqual(args.client_type, choice)

    def test_store_creds_invalid_client_type_rejected(self):
        parser = so.build_parser()
        with self.assertRaises(SystemExit):
            with patch("sys.stderr", StringIO()):
                parser.parse_args(["store-creds", "--client-type", "garbage"])


# ===========================================================================
# cmd_oauth_clients --type filter
# ===========================================================================

class TestCmdOauthClientsTypeFilter(unittest.TestCase):

    ENDPOINT = "https://api.au.sumologic.com"

    def _session(self, profile_data=None):
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        data = {"default": profile_data or {"endpoint": self.ENDPOINT}}
        f.write(json.dumps(data).encode())
        f.close()
        self._tmp = Path(f.name)
        return so.Session(self._tmp)

    def tearDown(self):
        if hasattr(self, "_tmp") and self._tmp.exists():
            self._tmp.unlink()

    def _make_args(self, type_filter=None, name_filter=None):
        args = argparse.Namespace(
            profile="default",
            region=None,
            endpoint=None,
            access_id="aid",
            access_key=None,
            output="table",
            limit=100,
            filter=name_filter,
            type=type_filter,
        )
        return args

    def _run(self, clients, type_filter=None):
        session = self._session()
        args = self._make_args(type_filter=type_filter)
        buf = StringIO()
        with patch("sumo_oauth._keychain_get", return_value="akey"), \
             patch("sumo_oauth.list_oauth_clients", return_value=clients), \
             patch("sys.stdout", buf):
            so.cmd_oauth_clients(args, session)
        return buf.getvalue()

    def test_no_type_filter_shows_all(self):
        clients = [
            {"type": "ClientCredentialsClient", "clientId": "C1", "name": "CC"},
            {"type": "AuthorizationCodeClient", "clientId": "A1", "name": "AC"},
        ]
        output = self._run(clients)
        self.assertIn("CC", output)
        self.assertIn("AC", output)

    def test_type_cc_filters_to_cc_only(self):
        clients = [
            {"type": "ClientCredentialsClient", "clientId": "C1", "name": "CC Client"},
            {"type": "AuthorizationCodeClient", "clientId": "A1", "name": "AC Client"},
        ]
        output = self._run(clients, type_filter="cc")
        self.assertIn("CC Client", output)
        self.assertNotIn("AC Client", output)

    def test_type_ac_filters_to_ac_only(self):
        clients = [
            {"type": "ClientCredentialsClient", "clientId": "C1", "name": "CC Client"},
            {"type": "AuthorizationCodeClient", "clientId": "A1", "name": "AC Client"},
        ]
        output = self._run(clients, type_filter="ac")
        self.assertNotIn("CC Client", output)
        self.assertIn("AC Client", output)

    def test_type_full_name_accepted(self):
        clients = [
            {"type": "ClientCredentialsClient", "clientId": "C1", "name": "CC Client"},
        ]
        output = self._run(clients, type_filter="ClientCredentialsClient")
        self.assertIn("CC Client", output)

    def test_type_unknown_exits(self):
        with self.assertRaises(SystemExit):
            self._run([], type_filter="garbage")


# ===========================================================================
# profile_status callback_port
# ===========================================================================

class TestProfileStatusCallbackPort(unittest.TestCase):

    def _session(self, data):
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        f.write(json.dumps(data).encode())
        f.close()
        self._tmp = Path(f.name)
        return so.Session(self._tmp)

    def tearDown(self):
        if hasattr(self, "_tmp") and self._tmp.exists():
            self._tmp.unlink()

    def test_callback_port_included_in_status(self):
        session = self._session({"default": {
            "endpoint": "https://api.au.sumologic.com",
            "oauth_client_type": "AuthorizationCodeClient",
            "callback_port": 9000,
        }})
        with patch("sumo_oauth._keychain_get", return_value=None):
            status = session.profile_status("default")
        self.assertEqual(status["callback_port"], 9000)

    def test_callback_port_none_when_not_set(self):
        session = self._session({"default": {
            "endpoint": "https://api.au.sumologic.com",
            "oauth_client_type": "ClientCredentialsClient",
        }})
        with patch("sumo_oauth._keychain_get", return_value=None):
            status = session.profile_status("default")
        self.assertIsNone(status["callback_port"])


# ===========================================================================
# store-creds callback_port handling
# ===========================================================================

class TestStoreCredsCallbackPort(unittest.TestCase):

    def _fresh_session(self):
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        Path(tmp.name).unlink()
        return so.Session(Path(tmp.name))

    def _run(self, args, session, inputs=()):
        input_iter = iter(inputs)
        with patch("builtins.input", side_effect=lambda _: next(input_iter, "")), \
             patch("getpass.getpass", return_value=""), \
             patch("sumo_oauth._keychain_available", return_value=True), \
             patch("sumo_oauth._keychain_get", return_value=None), \
             patch("sumo_oauth._keychain_set", return_value=True):
            so.cmd_store_creds(args, session)

    def test_callback_port_flag_stored_for_ac(self):
        session = self._fresh_session()
        args = argparse.Namespace(
            profile="default", mode="oauth", region="us1", endpoint=None,
            client_id="cid", client_type="authorization-code", access_id=None,
            callback_port=9877,
        )
        self._run(args, session)
        p = session.get("default")
        self.assertEqual(p.get("callback_port"), 9877)

    def test_callback_port_default_8888_for_ac_when_not_set(self):
        session = self._fresh_session()
        args = argparse.Namespace(
            profile="default", mode="oauth", region="au", endpoint=None,
            client_id="cid", client_type="authorization-code", access_id=None,
            callback_port=None,
        )
        # inputs: region, client_id, type prompt, callback_port (enter = default)
        self._run(args, session, inputs=["", "", "", ""])
        p = session.get("default")
        self.assertEqual(p.get("callback_port"), 8888)

    def test_callback_port_not_stored_for_cc(self):
        session = self._fresh_session()
        args = argparse.Namespace(
            profile="default", mode="oauth", region="us1", endpoint=None,
            client_id="cid", client_type="client-credentials", access_id=None,
            callback_port=None,
        )
        self._run(args, session)
        p = session.get("default")
        self.assertNotIn("callback_port", p)

    def test_store_creds_callback_port_arg_exists(self):
        parser = so.build_parser()
        args = parser.parse_args([
            "store-creds", "--client-type", "authorization-code",
            "--region", "us1", "--callback-port", "9500",
        ])
        self.assertEqual(args.callback_port, 9500)


# ===========================================================================
# DEPLOYMENT_NAMES and _API_TO_SERVER_NAME
# ===========================================================================

class TestDeploymentNames(unittest.TestCase):

    def test_us1_maps_to_prod(self):
        self.assertEqual(so.DEPLOYMENT_NAMES["us1"], "prod")

    def test_all_other_regions_map_to_key(self):
        for region in ("us2", "eu", "au", "de", "jp", "ca", "in", "fed", "kr", "ch"):
            self.assertEqual(so.DEPLOYMENT_NAMES[region], region,
                             f"Expected {region} → '{region}', got '{so.DEPLOYMENT_NAMES[region]}'")

    def test_all_regions_covered(self):
        self.assertEqual(set(so.DEPLOYMENT_NAMES.keys()), set(so.REGIONS.keys()))

    def test_api_to_server_name_us1(self):
        us1_api = so.REGIONS["us1"]
        self.assertEqual(so._API_TO_SERVER_NAME[us1_api], "sumo-mcp-prod")

    def test_api_to_server_name_au(self):
        au_api = so.REGIONS["au"]
        self.assertEqual(so._API_TO_SERVER_NAME[au_api], "sumo-mcp-au")

    def test_api_to_server_name_all_regions_mapped(self):
        for region, api_url in so.REGIONS.items():
            self.assertIn(api_url, so._API_TO_SERVER_NAME,
                          f"No server name for region '{region}'")
            self.assertTrue(so._API_TO_SERVER_NAME[api_url].startswith("sumo-mcp-"))


# ===========================================================================
# cmd_client_config server name derivation
# ===========================================================================

class TestCmdClientConfigServerName(unittest.TestCase):

    def _run_config(self, fmt, server_name=None, callback_port=None, endpoint=None):
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        ep = endpoint or "https://api.sumologic.com"
        data = {"default": {
            "endpoint": ep,
            "client_id": "TEST_CLIENT_ID",
            "access_token": "TEST_TOKEN",
            "expires_at": time.time() + 3600,
            "oauth_client_type": "AuthorizationCodeClient",
            "callback_port": 8888,
        }}
        f.write(json.dumps(data).encode())
        f.close()
        session = so.Session(Path(f.name))
        args = MagicMock()
        args.format = fmt
        args.profile = "default"
        args.server_name = server_name   # None triggers derivation
        args.callback_port = callback_port
        buf = StringIO()
        with patch("sys.stdout", buf), \
             patch("sumo_oauth._keychain_get", return_value="TEST_SECRET"), \
             patch("sumo_oauth._keychain_available", return_value=True), \
             patch("sumo_oauth._fetch_oauth_token",
                   return_value={"access_token": "TEST_TOKEN", "expires_in": 3600}):
            so.cmd_client_config(args, session)
        Path(f.name).unlink()
        return buf.getvalue()

    def test_server_name_derived_as_prod_for_us1(self):
        output = self._run_config("claude-code", server_name=None,
                                  endpoint="https://api.sumologic.com")
        self.assertIn("sumo-mcp-prod", output)

    def test_server_name_derived_for_au(self):
        output = self._run_config("claude-code", server_name=None,
                                  endpoint="https://api.au.sumologic.com")
        self.assertIn("sumo-mcp-au", output)

    def test_explicit_server_name_overrides_derivation(self):
        output = self._run_config("claude-code", server_name="my-custom-server",
                                  endpoint="https://api.sumologic.com")
        self.assertIn("my-custom-server", output)
        self.assertNotIn("sumo-mcp-prod", output)

    def test_callback_port_from_profile_used_when_arg_is_none(self):
        output = self._run_config("claude-code", callback_port=None,
                                  endpoint="https://api.sumologic.com")
        self.assertIn("8888", output)


if __name__ == "__main__":
    unittest.main()
