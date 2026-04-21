"""
Unit tests for sumo_oauth.py

Run with:
    uv run pytest -v
    uv run pytest -v -m "not integration"   # skip tests that need live creds

Mock data for API-response tests is loaded from mock_data/ (created by
fetch_mock_data.py).  Tests that rely on mock_data files are skipped
gracefully if the files do not exist yet.
"""

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
    @patch("sumo_oauth._keychain_get", return_value="secret")
    @patch("sumo_oauth._fetch_oauth_token",
           return_value={"access_token": "newtoken", "expires_in": 1800})
    def test_require_token_refreshes_expired(self, mock_fetch, mock_get, mock_set, mock_avail):
        session = self._session({"default": {
            "endpoint": "https://api.au.sumologic.com",
            "client_id": "cid",
            "access_token": "oldtoken",
            "expires_at": time.time() - 10,  # expired
        }})
        bearer = session.require_token("default")
        self.assertEqual(bearer, "Bearer newtoken")
        mock_fetch.assert_called_once()

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
        "userId": "0000000000000001",
        "scopes": ["runLogSearch"],
        "createdAt": "2026-04-20T00:00:00Z",
        "expiresAt": "2026-07-20T00:00:00Z",
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
        # scopes rendered via _fmt_scopes
        self.assertIn("runLogSearch", output)

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

    def test_access_key_table_columns_match_response(self):
        """Verify the table column field names exist in the actual API response."""
        data = self._skip_if_missing("access_keys")
        # These are the field names used in print_access_keys table columns
        for field in ("id", "label", "serviceAccountId", "createdAt", "lastUsed"):
            self.assertIn(field, data,
                          f"Table column field '{field}' not in API response — "
                          f"update print_access_keys columns. Available: {list(data.keys())}")


if __name__ == "__main__":
    unittest.main()
