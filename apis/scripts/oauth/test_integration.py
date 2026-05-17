"""
Integration tests for sumo_oauth.py

These tests make REAL network calls to the Sumo Logic API.
All operations are READ-ONLY — no creates, deletes, or modifications.
Token refreshes are permitted (they are not destructive).

Run integration tests only:
    uv run pytest -v -m integration

Skip integration tests (normal unit-test run):
    uv run pytest -v -m "not integration"

Profiles used:
  default   — ClientCredentialsClient; tests CC token refresh + all Basic-auth GET commands
  stg-code  — AuthorizationCodeClient; tests token refresh via stored refresh_token grant
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

OAUTH_DIR = Path(__file__).parent
SCRIPT    = str(OAUTH_DIR / "sumo_oauth.py")


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------

def _run(*args, timeout: int = 45) -> tuple[int, str, str]:
    """Invoke the CLI and return (returncode, stdout, stderr).

    timeout: seconds before the subprocess is killed (default 45s).
    stdin is set to DEVNULL so the subprocess can never block waiting
    for terminal input (e.g. keychain UI dialogs, getpass prompts).
    """
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, *args],
            capture_output=True, text=True, cwd=str(OAUTH_DIR),
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"CLI command timed out after {timeout}s:\n"
            f"  {' '.join([sys.executable, SCRIPT, *args])}"
        )


def _profile_status(profile: str) -> dict:
    """Return the parsed JSON status dict for a profile, or {} if unavailable."""
    rc, out, _ = _run("status", "--profile", profile)
    if rc != 0:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# Profile readiness checks — evaluated once per session via module-level cache
# ---------------------------------------------------------------------------

_STATUS_CACHE: dict[str, dict] = {}


def _status(profile: str) -> dict:
    if profile not in _STATUS_CACHE:
        _STATUS_CACHE[profile] = _profile_status(profile)
    return _STATUS_CACHE[profile]


def _require_default_cc():
    """Skip if 'default' profile is not ready for CC token + Basic-auth API tests."""
    s = _status("default")
    if not s:
        pytest.skip("'default' profile not configured")
    if not s.get("client_secret_stored"):
        pytest.skip("'default' profile: client_secret not in keychain — run store-creds")
    if not s.get("access_key_stored"):
        pytest.skip("'default' profile: access_key not in keychain — run store-creds")


def _require_stg_code_ac():
    """Skip if 'stg-code' profile cannot produce a valid token right now.

    A stored refresh_token may be expired or revoked on the server side (HTTP 400
    invalid_grant) even though the keychain entry exists.  The only reliable check
    is to actually attempt a token fetch — if the server rejects it, the tests
    cannot run and the user must re-authenticate with 'auth-code-login'.
    """
    s = _status("stg-code")
    if not s:
        pytest.skip("'stg-code' profile not configured")
    if s.get("oauth_client_type") != "AuthorizationCodeClient":
        pytest.skip("'stg-code' profile is not an AuthorizationCodeClient — wrong profile type")
    # Probe: attempt a real token fetch (uses refresh_token grant if available)
    rc, _, _ = _run("token", "--raw", "--profile", "stg-code")
    if rc != 0:
        pytest.skip(
            "'stg-code' token cannot be refreshed (refresh_token may be expired or revoked). "
            "Re-authenticate with:  sumo-oauth auth-code-login --profile stg-code"
        )


# ===========================================================================
# CC token integration — 'default' profile (ClientCredentialsClient)
# ===========================================================================

@pytest.mark.integration
class TestCCTokenDefault:
    """Token lifecycle tests for the 'default' ClientCredentialsClient profile."""

    def setup_method(self):
        _require_default_cc()

    def test_login_succeeds(self):
        rc, out, err = _run("login", "--profile", "default")
        assert rc == 0, f"login exited {rc}:\n{err}"
        assert "Login successful" in out

    def test_login_shows_client_type(self):
        rc, out, _ = _run("login", "--profile", "default")
        assert rc == 0
        assert "ClientCredentialsClient" in out

    def test_login_shows_endpoint(self):
        rc, out, _ = _run("login", "--profile", "default")
        assert rc == 0
        assert "Endpoint" in out
        assert "sumologic.com" in out

    def test_token_raw_returns_bearer(self):
        rc, out, err = _run("token", "--raw", "--profile", "default")
        assert rc == 0, f"token --raw exited {rc}:\n{err}"
        token = out.strip()
        assert token.startswith("Bearer "), f"Expected 'Bearer …', got: {token!r}"
        assert len(token) > 30

    def test_token_shows_profile_info(self):
        rc, out, _ = _run("token", "--profile", "default")
        assert rc == 0
        assert "Profile" in out
        assert "Expires" in out

    def test_status_valid_after_login(self):
        _run("login", "--profile", "default")  # ensure token is fresh
        rc, out, _ = _run("status", "--profile", "default")
        assert rc == 0
        data = json.loads(out)
        assert data["status"] == "valid"
        assert data["oauth_client_type"] == "ClientCredentialsClient"
        assert data["client_secret_stored"] is True

    def test_export_env_outputs_all_vars(self):
        _run("login", "--profile", "default")  # ensure stored token is fresh
        rc, out, err = _run("export-env", "--profile", "default")
        assert rc == 0, f"export-env exited {rc}:\n{err}"
        for var in (
            "SUMOLOGIC_MCP_URL",
            "SUMOLOGIC_OAUTH_CLIENT_ID",
            "SUMOLOGIC_OAUTH_CLIENT_SECRET",
            "SUMOLOGIC_OAUTH_TOKEN_URL",
            "SUMOLOGIC_OAUTH_ACCESS_TOKEN",
        ):
            assert var in out, f"Missing variable in export-env output: {var}"

    def test_export_env_does_not_refresh_token(self):
        """export-env should output the stored token, not trigger a new token request."""
        # Get the token via 'token --raw', then check export-env returns the same value
        _run("login", "--profile", "default")
        rc1, raw, _ = _run("token", "--raw", "--profile", "default")
        assert rc1 == 0
        stored_token = raw.strip().removeprefix("Bearer ")

        rc2, env_out, _ = _run("export-env", "--profile", "default")
        assert rc2 == 0
        assert stored_token in env_out, "export-env returned a different token than the stored one"

    def test_export_env_fish_syntax(self):
        rc, out, _ = _run("export-env", "--profile", "default", "--shell", "fish")
        assert rc == 0
        lines = [l for l in out.splitlines() if l.strip()]
        assert all(l.startswith("set -x ") for l in lines), \
            f"Expected fish 'set -x' lines, got:\n{out}"


# ===========================================================================
# AC token integration — 'stg-code' profile (AuthorizationCodeClient)
# ===========================================================================

@pytest.mark.integration
class TestACTokenStgCode:
    """Token lifecycle tests for the 'stg-code' AuthorizationCodeClient profile."""

    def setup_method(self):
        _require_stg_code_ac()

    def test_token_raw_returns_bearer(self):
        """Expired AC token should refresh automatically via stored refresh_token."""
        rc, out, err = _run("token", "--raw", "--profile", "stg-code")
        assert rc == 0, f"token --raw exited {rc}:\n{err}"
        token = out.strip()
        assert token.startswith("Bearer "), f"Expected 'Bearer …', got: {token!r}"
        assert len(token) > 30

    def test_status_shows_ac_type(self):
        rc, out, _ = _run("status", "--profile", "stg-code")
        assert rc == 0
        data = json.loads(out)
        assert data["oauth_client_type"] == "AuthorizationCodeClient"

    def test_status_valid_after_token_refresh(self):
        _run("token", "--raw", "--profile", "stg-code")  # force refresh
        rc, out, _ = _run("status", "--profile", "stg-code")
        assert rc == 0
        data = json.loads(out)
        assert data["status"] == "valid"
        assert data["refresh_token_stored"] is True

    def test_export_env_outputs_key_vars(self):
        rc, out, err = _run("export-env", "--profile", "stg-code")
        assert rc == 0, f"export-env exited {rc}:\n{err}"
        assert "SUMOLOGIC_OAUTH_CLIENT_ID" in out
        assert "SUMOLOGIC_OAUTH_TOKEN_URL" in out
        assert "SUMOLOGIC_OAUTH_ACCESS_TOKEN" in out


# ===========================================================================
# Basic-auth API GET commands — 'default' profile (access_id + access_key)
# ===========================================================================

@pytest.mark.integration
class TestAPIGetDefault:
    """Live read-only API calls using Basic auth from the 'default' profile."""

    def setup_method(self):
        _require_default_cc()

    # -- users ---------------------------------------------------------------

    def test_users_table(self):
        rc, out, err = _run("users", "--profile", "default")
        assert rc == 0, f"users exited {rc}:\n{err}"
        assert out.strip()

    def test_users_json_is_list(self):
        rc, out, _ = _run("users", "--profile", "default", "--output", "json")
        assert rc == 0
        assert isinstance(json.loads(out), list)

    def test_users_json_has_expected_fields(self):
        rc, out, _ = _run("users", "--profile", "default", "--output", "json")
        assert rc == 0
        data = json.loads(out)
        if data:
            assert "id" in data[0]
            assert "email" in data[0]

    def test_users_filter_regex(self):
        rc, out, _ = _run("users", "--profile", "default",
                           "--filter", ".*", "--output", "json")
        assert rc == 0
        assert isinstance(json.loads(out), list)

    # -- service-accounts ----------------------------------------------------

    def test_service_accounts_table(self):
        rc, out, err = _run("service-accounts", "--profile", "default")
        assert rc == 0, f"service-accounts exited {rc}:\n{err}"
        assert out.strip()

    def test_service_accounts_json_is_list(self):
        rc, out, _ = _run("service-accounts", "--profile", "default", "--output", "json")
        assert rc == 0
        assert isinstance(json.loads(out), list)

    # -- oauth-clients -------------------------------------------------------

    def test_oauth_clients_table(self):
        rc, out, err = _run("oauth-clients", "--profile", "default")
        assert rc == 0, f"oauth-clients exited {rc}:\n{err}"
        assert out.strip()

    def test_oauth_clients_json_is_list(self):
        rc, out, _ = _run("oauth-clients", "--profile", "default", "--output", "json")
        assert rc == 0
        assert isinstance(json.loads(out), list)

    # -- oauth-scopes --------------------------------------------------------

    def test_oauth_scopes_table(self):
        rc, out, err = _run("oauth-scopes", "--profile", "default")
        assert rc == 0, f"oauth-scopes exited {rc}:\n{err}"
        assert out.strip()

    def test_oauth_scopes_json_is_list(self):
        rc, out, _ = _run("oauth-scopes", "--profile", "default", "--output", "json")
        assert rc == 0
        data = json.loads(out)
        assert isinstance(data, list)

    def test_oauth_scopes_json_has_id_field(self):
        rc, out, _ = _run("oauth-scopes", "--profile", "default", "--output", "json")
        assert rc == 0
        data = json.loads(out)
        if data:
            assert "id" in data[0]
            assert "label" in data[0]

    def test_oauth_scopes_filter(self):
        rc, out, _ = _run("oauth-scopes", "--profile", "default",
                           "--filter", "search", "--output", "json")
        assert rc == 0
        assert isinstance(json.loads(out), list)

    # -- access-keys ---------------------------------------------------------

    def test_access_keys_table(self):
        rc, out, err = _run("access-keys", "--profile", "default")
        assert rc == 0, f"access-keys exited {rc}:\n{err}"
        assert out.strip()

    def test_access_keys_json_is_list(self):
        rc, out, _ = _run("access-keys", "--profile", "default", "--output", "json")
        assert rc == 0
        assert isinstance(json.loads(out), list)

    # -- roles ---------------------------------------------------------------

    def test_roles_table(self):
        rc, out, err = _run("roles", "--profile", "default")
        assert rc == 0, f"roles exited {rc}:\n{err}"
        assert out.strip()

    def test_roles_json_is_list(self):
        rc, out, _ = _run("roles", "--profile", "default", "--output", "json")
        assert rc == 0
        data = json.loads(out)
        assert isinstance(data, list)

    def test_roles_json_has_expected_fields(self):
        rc, out, _ = _run("roles", "--profile", "default", "--output", "json")
        assert rc == 0
        data = json.loads(out)
        if data:
            assert "id" in data[0]
            assert "name" in data[0]

    def test_roles_filter(self):
        rc, out, _ = _run("roles", "--profile", "default",
                           "--filter", ".*", "--output", "json")
        assert rc == 0
        assert isinstance(json.loads(out), list)

    # -- oauth-consents ------------------------------------------------------

    def test_oauth_consents_table(self):
        rc, out, err = _run("oauth-consents", "--profile", "default")
        assert rc == 0, f"oauth-consents exited {rc}:\n{err}"
        assert out.strip()

    def test_oauth_consents_json_is_list(self):
        rc, out, _ = _run("oauth-consents", "--profile", "default", "--output", "json")
        assert rc == 0
        assert isinstance(json.loads(out), list)

    # -- list-profiles -------------------------------------------------------

    def test_list_profiles_includes_default(self):
        rc, out, _ = _run("list-profiles")
        assert rc == 0
        assert "default" in out

    def test_list_profiles_json_contains_default(self):
        rc, out, _ = _run("list-profiles", "--output", "json")
        assert rc == 0
        data = json.loads(out)
        assert isinstance(data, list)
        names = [p["profile"] for p in data]
        assert "default" in names
