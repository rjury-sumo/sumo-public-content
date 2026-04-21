#!/usr/bin/env python3
"""
Sumo Logic OAuth CLI Utility

Supports multiple named profiles so different Sumo Logic instances (regions,
accounts) can be managed from one tool.

Authentication model
--------------------
OAuth client credentials (--client-id / --client-secret):
  Used ONLY for obtaining/refreshing an access token:
    login   – exchange client_id/secret for a Bearer token, persist session
    token   – show or refresh the current token

Basic auth (--access-id / --access-key):
  Used for all admin API operations:
    users             – GET /api/v1/users
    service-accounts  – GET /api/v1/serviceAccounts
    oauth-clients     – GET /api/v1/oauth/clients

Credential resolution order (most to least preferred):
  1. CLI flag           --client-secret, --access-key, etc.
  2. Active profile     non-sensitive values from session file;
                        secrets from OS keychain
  3. Environment var    SUMO_CLIENT_SECRET, SUMO_ACCESS_KEY, etc.
  4. Error

Profile storage
---------------
Session file  (~/.sumo_oauth_session.json, chmod 600):
  Non-sensitive per-profile data: endpoint, client_id, access_id,
  access_token, expires_at.  Secrets are NEVER written here.

OS keychain   (service: "sumo-oauth"):
  {profile}:client_secret
  {profile}:access_key

Usage
-----
  # One-time profile setup – prompts securely for secrets
  sumo-oauth store-creds --profile prod --region us1 --client-id CID --access-id AID

  # OAuth token commands
  sumo-oauth login  [--profile prod]
  sumo-oauth token  [--profile prod]
  sumo-oauth token  [--profile prod] --raw
  sumo-oauth logout [--profile prod]

  # Admin API commands (Basic auth, all resolved from profile)
  sumo-oauth users            [--profile prod]
  sumo-oauth service-accounts [--profile prod]
  sumo-oauth oauth-clients    [--profile prod]

  # Profile management
  sumo-oauth list-profiles
  sumo-oauth delete-profile --profile prod
  sumo-oauth clear-creds    --profile prod
  sumo-oauth status         [--profile prod]

Environment variables (loaded from .env if python-dotenv is installed):
  SUMO_PROFILE         Default profile name (overrides built-in default of 'default')
  SUMO_REGION          Region override
  SUMO_CLIENT_ID       OAuth client ID override
  SUMO_CLIENT_SECRET   OAuth client secret override  ← prefer keychain
  SUMO_ACCESS_ID       Basic auth access ID override
  SUMO_ACCESS_KEY      Basic auth access key override ← prefer keychain
"""

import argparse
import base64
import getpass
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests as _requests

# Optional: load .env from the current directory if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGIONS = {
    "us1": "https://api.sumologic.com",
    "us2": "https://api.us2.sumologic.com",
    "eu":  "https://api.eu.sumologic.com",
    "au":  "https://api.au.sumologic.com",
    "de":  "https://api.de.sumologic.com",
    "jp":  "https://api.jp.sumologic.com",
    "ca":  "https://api.ca.sumologic.com",
    "in":  "https://api.in.sumologic.com",
}

# OAuth2 token endpoints (service.* host, /oauth2/token path — different from the API host)
TOKEN_URLS = {
    "us1": "https://service.sumologic.com/oauth2/token",
    "us2": "https://service.us2.sumologic.com/oauth2/token",
    "eu":  "https://service.eu.sumologic.com/oauth2/token",
    "au":  "https://service.au.sumologic.com/oauth2/token",
    "de":  "https://service.de.sumologic.com/oauth2/token",
    "jp":  "https://service.jp.sumologic.com/oauth2/token",
    "ca":  "https://service.ca.sumologic.com/oauth2/token",
    "in":  "https://service.in.sumologic.com/oauth2/token",
}

# Reverse map: api endpoint → token URL (for auto-derivation)
_API_TO_TOKEN_URL = {v: TOKEN_URLS[k] for k, v in REGIONS.items()}

DEFAULT_SESSION_FILE = Path.home() / ".sumo_oauth_session.json"
DEFAULT_PROFILE      = "default"
TOKEN_REFRESH_BUFFER_SECS = 60
KEYCHAIN_SERVICE     = "sumo-oauth"


# ---------------------------------------------------------------------------
# Keychain helpers
# ---------------------------------------------------------------------------

def _keychain_available() -> bool:
    try:
        import keyring
        import keyring.backends.fail
        return not isinstance(keyring.get_keyring(), keyring.backends.fail.Keyring)
    except Exception:
        return False


def _keychain_get(username: str) -> str | None:
    try:
        import keyring
        return keyring.get_password(KEYCHAIN_SERVICE, username)
    except Exception as exc:
        logger.debug("Keychain get failed for '%s': %s", username, exc)
        return None


def _keychain_set(username: str, secret: str) -> bool:
    try:
        import keyring
        keyring.set_password(KEYCHAIN_SERVICE, username, secret)
        return True
    except Exception as exc:
        logger.warning("Keychain store failed for '%s': %s", username, exc)
        return False


def _keychain_delete(username: str) -> bool:
    try:
        import keyring
        keyring.delete_password(KEYCHAIN_SERVICE, username)
        return True
    except Exception as exc:
        logger.debug("Keychain delete for '%s': %s", username, exc)
        return False


def _client_secret_key(profile: str) -> str:
    return f"{profile}:client_secret"


def _access_key_key(profile: str) -> str:
    return f"{profile}:access_key"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(level: str = "INFO") -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s",
                                           datefmt="%H:%M:%S"))
    logger.setLevel(numeric)
    logger.addHandler(handler)
    logger.propagate = False


# ---------------------------------------------------------------------------
# Endpoint resolution
# ---------------------------------------------------------------------------

def resolve_endpoint(region_or_url: str) -> str:
    key = region_or_url.lower()
    if key in REGIONS:
        return REGIONS[key]
    if region_or_url.startswith("http"):
        return region_or_url.rstrip("/")
    raise ValueError(
        f"Unknown region '{region_or_url}'. Valid regions: {', '.join(REGIONS)}"
    )


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _basic_auth_header(access_id: str, access_key: str) -> str:
    creds = base64.b64encode(f"{access_id}:{access_key}".encode()).decode()
    return f"Basic {creds}"


class _SumoSession(_requests.Session):
    """
    requests.Session that preserves the Authorization header across redirects.

    Sumo Logic returns HTTP 301 when a request hits the wrong regional endpoint
    (e.g. api.sumologic.com redirects to api.us2.sumologic.com).  The default
    requests behaviour strips Authorization on cross-host redirects, causing the
    redirected request to fail.  Overriding rebuild_auth() prevents that.
    """
    def rebuild_auth(self, prepared_request, response):
        pass  # keep Authorization header on all redirects


def _api_get(url: str, auth_header: str, params: dict | None = None) -> dict:
    logger.debug("GET %s  params=%s", url, params)
    logger.debug("Authorization header type: %s", auth_header.split()[0] if auth_header else "none")
    with _SumoSession() as session:
        resp = session.get(
            url,
            headers={"Authorization": auth_header, "Accept": "application/json"},
            params=params,
        )
    if resp.history:
        for r in resp.history:
            logger.debug("Redirect: %s %s → %s", r.status_code, r.url, r.headers.get("Location"))
        logger.debug("Final URL after redirects: %s", resp.url)
    if not resp.ok:
        logger.error("HTTP %s %s", resp.status_code, resp.reason)
        logger.error("URL: %s", resp.url)
        logger.error("Response: %s", resp.text[:500])
        if resp.status_code == 401:
            logger.error(
                "401 Unauthorized – common causes:\n"
                "  • access_id and access_key are from different sources (check INFO lines above)\n"
                "  • SUMO_ACCESS_ID or SUMO_ACCESS_KEY env vars override profile credentials\n"
                "  • Stored access_key is incorrect – run 'store-creds' to update it"
            )
        sys.exit(1)
    return resp.json()


def _api_post(url: str, auth_header: str, payload: dict) -> dict:
    logger.debug("POST %s  body=%s", url, payload)
    with _SumoSession() as session:
        resp = session.post(
            url,
            json=payload,
            headers={"Authorization": auth_header,
                     "Content-Type": "application/json",
                     "Accept": "application/json"},
        )
    if resp.history:
        for r in resp.history:
            logger.debug("Redirect: %s %s → %s", r.status_code, r.url, r.headers.get("Location"))
        logger.debug("Final URL after redirects: %s", resp.url)
    if not resp.ok:
        logger.error("HTTP %s %s", resp.status_code, resp.reason)
        logger.error("URL: %s", resp.url)
        logger.error("Response: %s", resp.text[:500])
        sys.exit(1)
    return resp.json()


def _api_put(url: str, auth_header: str, payload: dict) -> dict:
    logger.debug("PUT %s  body=%s", url, payload)
    with _SumoSession() as session:
        resp = session.put(
            url,
            json=payload,
            headers={"Authorization": auth_header,
                     "Content-Type": "application/json",
                     "Accept": "application/json"},
        )
    if resp.history:
        for r in resp.history:
            logger.debug("Redirect: %s %s → %s", r.status_code, r.url, r.headers.get("Location"))
        logger.debug("Final URL after redirects: %s", resp.url)
    if not resp.ok:
        logger.error("HTTP %s %s", resp.status_code, resp.reason)
        logger.error("URL: %s", resp.url)
        logger.error("Response: %s", resp.text[:500])
        sys.exit(1)
    return resp.json()


def _api_delete(url: str, auth_header: str) -> None:
    logger.debug("DELETE %s", url)
    with _SumoSession() as session:
        resp = session.delete(
            url,
            headers={"Authorization": auth_header, "Accept": "application/json"},
        )
    if resp.history:
        for r in resp.history:
            logger.debug("Redirect: %s %s → %s", r.status_code, r.url, r.headers.get("Location"))
        logger.debug("Final URL after redirects: %s", resp.url)
    if not resp.ok:
        logger.error("HTTP %s %s", resp.status_code, resp.reason)
        logger.error("URL: %s", resp.url)
        logger.error("Response: %s", resp.text[:500])
        sys.exit(1)


def _fetch_oauth_token(endpoint: str, client_id: str, client_secret: str,
                       scopes: list[str] | None = None,
                       token_url: str | None = None) -> dict:
    """POST to the token endpoint with client_credentials grant.

    Credentials are sent via HTTP Basic auth (Authorization header) as per
    RFC 6749 §2.3.1, matching the curl -u <id>:<secret> pattern.
    The default token URL is {endpoint}/oauth/v2/token; pass token_url to override.
    """
    url = token_url or _API_TO_TOKEN_URL.get(endpoint.rstrip("/")) or f"{endpoint}/oauth/v2/token"
    logger.debug("Token request: POST %s  scopes=%s", url, scopes)
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data: dict = {"grant_type": "client_credentials"}
    if scopes:
        data["scope"] = " ".join(scopes)
    with _SumoSession() as session:
        resp = session.post(
            url,
            data=data,
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type":  "application/x-www-form-urlencoded",
                "Accept":        "application/json",
            },
        )
    if not resp.ok:
        logger.error("Token request failed – HTTP %s: %s", resp.status_code, resp.text[:500])
        sys.exit(1)
    return resp.json()


# ---------------------------------------------------------------------------
# Session / profile management
#
# Session file structure:
# {
#   "default": {
#     "endpoint":     "https://api.sumologic.com",
#     "client_id":    "...",
#     "access_id":    "...",
#     "access_token": "...",   ← short-lived, low risk
#     "token_type":   "Bearer",
#     "expires_at":   1234567890.0,
#     "expires_in":   1800
#   },
#   "prod": { ... }
# }
#
# Secrets (client_secret, access_key) are NEVER written here.
# They live in the OS keychain keyed as:
#   "{profile}:client_secret"
#   "{profile}:access_key"
# ---------------------------------------------------------------------------

class Session:
    """Multi-profile session store. Secrets never written to disk."""

    def __init__(self, path: Path):
        self.path = path
        self._profiles: dict[str, dict] = {}
        self._load()

    # -- persistence ---------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return

        # Migrate old flat single-session format → {"default": <data>}
        if raw and not any(isinstance(v, dict) for v in raw.values()):
            logger.debug("Migrating legacy session file to profile format")
            self._profiles = {DEFAULT_PROFILE: raw}
            self._save()
        else:
            self._profiles = raw

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._profiles, indent=2))
        self.path.chmod(0o600)

    # -- profile access ------------------------------------------------------

    def get(self, profile: str) -> dict:
        return self._profiles.get(profile, {})

    def set(self, profile: str, data: dict) -> None:
        self._profiles[profile] = data
        self._save()

    def delete(self, profile: str) -> None:
        self._profiles.pop(profile, None)
        self._save()

    def names(self) -> list[str]:
        return list(self._profiles.keys())

    # -- token helpers -------------------------------------------------------

    def _is_valid(self, profile: str) -> bool:
        p = self.get(profile)
        return bool(
            p.get("access_token")
            and time.time() < float(p.get("expires_at", 0)) - TOKEN_REFRESH_BUFFER_SECS
        )

    def store_token(self, profile: str, endpoint: str, client_id: str,
                    client_secret: str, token_response: dict,
                    scopes: list[str] | None = None,
                    token_url: str | None = None) -> None:
        """
        Persist token metadata to the session file.
        Stores client_secret in keychain – never in the file.
        """
        if _keychain_available():
            if _keychain_set(_client_secret_key(profile), client_secret):
                logger.debug("client_secret stored in keychain for profile '%s'", profile)
        else:
            logger.warning(
                "No keychain backend available. client_secret will not be persisted "
                "beyond this session. Set SUMO_CLIENT_SECRET for automatic refresh."
            )

        expires_in = int(token_response.get("expires_in", 1800))
        p = self.get(profile)
        p.update({
            "endpoint":     endpoint,
            "client_id":    client_id,
            "access_token": token_response["access_token"],
            "token_type":   token_response.get("token_type", "Bearer"),
            "expires_at":   time.time() + expires_in,
            "expires_in":   expires_in,
        })
        if scopes:
            p["scopes"] = scopes
        if token_url:
            p["token_url"] = token_url
        self.set(profile, p)
        logger.info("Profile '%s' saved to %s (expires in %ds)", profile, self.path, expires_in)

    def require_token(self, profile: str) -> str:
        """Return a valid 'Bearer <token>', refreshing via keychain if needed."""
        p = self.get(profile)
        if not p or not p.get("client_id"):
            logger.error(
                "Profile '%s' has no OAuth configuration. "
                "Run 'store-creds --profile %s --client-id CID' then 'login --profile %s'.",
                profile, profile, profile,
            )
            sys.exit(1)

        if not self._is_valid(profile):
            logger.info("Token for profile '%s' expired or expiring – refreshing…", profile)
            client_secret = (
                _keychain_get(_client_secret_key(profile))
                or os.environ.get("SUMO_CLIENT_SECRET")
            )
            if not client_secret:
                logger.error(
                    "Cannot refresh token for profile '%s': client_secret not found.\n"
                    "Run 'store-creds --profile %s --client-id %s' or set SUMO_CLIENT_SECRET.",
                    profile, profile, p["client_id"],
                )
                sys.exit(1)
            token_resp = _fetch_oauth_token(
                p["endpoint"], p["client_id"], client_secret,
                scopes=p.get("scopes"), token_url=p.get("token_url"),
            )
            self.store_token(profile, p["endpoint"], p["client_id"], client_secret, token_resp,
                             scopes=p.get("scopes"), token_url=p.get("token_url"))
            p = self.get(profile)

        return f"Bearer {p['access_token']}"

    def profile_status(self, profile: str) -> dict:
        p = self.get(profile)
        if not p:
            return {"profile": profile, "status": "not configured"}
        expires_at = float(p.get("expires_at", 0))
        remaining  = max(0, expires_at - time.time())
        remaining_i = int(remaining)
        remaining_hms = "{:02d}:{:02d}:{:02d}".format(
            remaining_i // 3600, (remaining_i % 3600) // 60, remaining_i % 60
        )
        return {
            "profile":              profile,
            "status":               "valid" if self._is_valid(profile) else
                                    ("expired" if p.get("access_token") else "no token"),
            "endpoint":             p.get("endpoint"),
            "client_id":            p.get("client_id"),
            "access_id":            p.get("access_id"),
            "expires_at_utc":       time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                  time.gmtime(expires_at)) if expires_at else None,
            "expires_at_local":     time.strftime("%Y-%m-%dT%H:%M:%S %Z",
                                                  time.localtime(expires_at)) if expires_at else None,
            "remaining":            remaining_hms,
            "client_secret_stored": bool(_keychain_get(_client_secret_key(profile))),
            "access_key_stored":    bool(_keychain_get(_access_key_key(profile))),
            "keychain_available":   _keychain_available(),
        }


# ---------------------------------------------------------------------------
# API calls (all use Basic auth)
# ---------------------------------------------------------------------------

def list_access_keys(endpoint: str, auth_header: str, limit: int = 100) -> list[dict]:
    """GET /api/v1/accessKeys – paginated list of access keys for the org."""
    keys: list[dict] = []
    token = None
    while True:
        params: dict = {"limit": limit}
        if token:
            params["token"] = token
        resp = _api_get(f"{endpoint}/api/v1/accessKeys", auth_header, params)
        keys.extend(resp.get("data", []))
        token = resp.get("next")
        if not token:
            break
    return keys


def list_users(endpoint: str, auth_header: str, limit: int = 100) -> list[dict]:
    users: list[dict] = []
    token = None
    while True:
        params: dict = {"limit": limit}
        if token:
            params["token"] = token
        resp = _api_get(f"{endpoint}/api/v1/users", auth_header, params)
        users.extend(resp.get("data", []))
        token = resp.get("next")
        if not token:
            break
    return users


def list_service_accounts(endpoint: str, auth_header: str, limit: int = 100) -> list[dict]:
    accounts: list[dict] = []
    token = None
    while True:
        params: dict = {"limit": limit}
        if token:
            params["token"] = token
        resp = _api_get(f"{endpoint}/api/v1/serviceAccounts", auth_header, params)
        accounts.extend(resp.get("data", []))
        token = resp.get("next")
        if not token:
            break
    return accounts


def get_oauth_client(endpoint: str, auth_header: str, client_id: str) -> dict:
    """GET /api/v1/oauth/clients/{clientId}"""
    return _api_get(f"{endpoint}/api/v1/oauth/clients/{client_id}", auth_header)


def create_oauth_client(endpoint: str, auth_header: str, payload: dict) -> dict:
    """POST /api/v1/oauth/clients"""
    return _api_post(f"{endpoint}/api/v1/oauth/clients", auth_header, payload)


def update_oauth_client(endpoint: str, auth_header: str, client_id: str, payload: dict) -> dict:
    """PUT /api/v1/oauth/clients/{clientId}"""
    return _api_put(f"{endpoint}/api/v1/oauth/clients/{client_id}", auth_header, payload)


def delete_oauth_client(endpoint: str, auth_header: str, client_id: str) -> None:
    """DELETE /api/v1/oauth/clients/{clientId}"""
    _api_delete(f"{endpoint}/api/v1/oauth/clients/{client_id}", auth_header)


def list_oauth_consents(endpoint: str, auth_header: str, limit: int = 100) -> list[dict]:
    """GET /api/v1/oauth/consents – paginated list of OAuth consents."""
    consents: list[dict] = []
    token = None
    while True:
        params: dict = {"limit": limit}
        if token:
            params["token"] = token
        resp = _api_get(f"{endpoint}/api/v1/oauth/consents", auth_header, params)
        consents.extend(resp.get("data", []))
        token = resp.get("next")
        if not token:
            break
    return consents


def list_oauth_scopes(endpoint: str, auth_header: str) -> list[dict]:
    """GET /api/v1/oauth/scopes – returns all available OAuth scopes (no pagination)."""
    resp = _api_get(f"{endpoint}/api/v1/oauth/scopes", auth_header)
    return resp.get("data", resp) if isinstance(resp, dict) else resp


def list_oauth_clients(endpoint: str, auth_header: str, limit: int = 100) -> list[dict]:
    clients: list[dict] = []
    token = None
    while True:
        params: dict = {"limit": limit}
        if token:
            params["token"] = token
        resp = _api_get(f"{endpoint}/api/v1/oauth/clients", auth_header, params)
        clients.extend(resp.get("data", []))
        token = resp.get("next")
        if not token:
            break
    return clients


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _print_table(rows: list[dict], columns: list[tuple[str, str]]) -> None:
    if not rows:
        print("(no results)")
        return
    widths = [len(label) for label, _ in columns]
    def _cell(row, key):
        v = row.get(key)
        return "-" if v is None else str(v)

    for row in rows:
        for i, (_, key) in enumerate(columns):
            widths[i] = max(widths[i], len(_cell(row, key)))
    sep = "-+-".join("-" * w for w in widths)
    print(" | ".join(f"{label:<{widths[i]}}" for i, (label, _) in enumerate(columns)))
    print(sep)
    for row in rows:
        print(" | ".join(
            f"{_cell(row, key):<{widths[i]}}"
            for i, (_, key) in enumerate(columns)
        ))


def _fmt_scopes(val: list) -> str:
    """Format a scopes array: [] means all scopes; otherwise show count + first few."""
    if not val:
        return "(all)"
    preview = ", ".join(val[:3])
    return f"{preview}, +{len(val) - 3} more" if len(val) > 3 else preview


def print_access_keys(keys: list[dict], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(keys, indent=2))
        return
    # Flatten scopes for table display before passing to _print_table
    rows = []
    for k in keys:
        row = dict(k)
        row["_scopes"]          = _fmt_scopes(k.get("scopes", []))
        row["_effectiveScopes"] = _fmt_scopes(k.get("effectiveScopes", []))
        row["_disabled"]        = str(k.get("disabled", ""))
        row["_corsHeaders"]     = ", ".join(k.get("corsHeaders", [])) or "(none)"
        rows.append(row)
    _print_table(rows, [
        ("ID",               "id"),
        ("Label",            "label"),
        ("Disabled",         "_disabled"),
        ("Service Acct ID",  "serviceAccountId"),
        ("Created At",       "createdAt"),
        ("Last Used",        "lastUsed"),
        ("Expires On",       "expiresOn"),
        ("Scopes",           "_scopes"),
        ("Effective Scopes", "_effectiveScopes"),
    ])
    print(f"\nTotal: {len(keys)}")


def print_users(users: list[dict], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(users, indent=2))
        return
    for u in users:
        u["roleIds"] = ",".join(u.get("roleIds", []))
    _print_table(users, [
        ("ID",       "id"),
        ("First",    "firstName"),
        ("Last",     "lastName"),
        ("Email",    "email"),
        ("Active",   "isActive"),
        ("Role IDs", "roleIds"),
    ])
    print(f"\nTotal: {len(users)}")


def print_service_accounts(accounts: list[dict], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(accounts, indent=2))
        return
    _print_table(accounts, [
        ("ID",      "id"),
        ("Name",    "name"),
        ("Email",   "email"),
        ("Active",  "isActive"),
        ("Created", "createdAt"),
    ])
    print(f"\nTotal: {len(accounts)}")


def print_oauth_consents(consents: list[dict], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(consents, indent=2))
        return
    _print_table(consents, [
        ("Consent ID",  "id"),
        ("Client ID",   "clientId"),
        ("User ID",     "userId"),
        ("Scopes",      "scopes"),
        ("Created",     "createdAt"),
        ("Expires",     "expiresAt"),
    ])
    print(f"\nTotal: {len(consents)}")


def print_oauth_scopes(scopes: list[dict], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(scopes, indent=2))
        return
    rows = []
    for s in scopes:
        row = dict(s)
        row["_group"] = (s.get("group") or {}).get("label", "-")
        rows.append(row)
    _print_table(rows, [
        ("ID",    "id"),
        ("Label", "label"),
        ("Type",  "type"),
        ("Group", "_group"),
    ])
    print(f"\nTotal: {len(scopes)}")


def print_oauth_client(client: dict, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(client, indent=2))
        return
    for key, val in client.items():
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val)
        print(f"  {key:<24}: {val}")


def print_oauth_clients(clients: list[dict], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(clients, indent=2))
        return
    rows = []
    for c in clients:
        row = dict(c)
        row["_scopes"]          = _fmt_scopes(c.get("scopes", []))
        row["_effectiveScopes"] = _fmt_scopes(c.get("effectiveScopes", []))
        row["_runAsId"]         = (c.get("runAs") or {}).get("runAsId", "-")
        rows.append(row)
    _print_table(rows, [
        ("Client ID",        "clientId"),
        ("Name",             "name"),
        ("Type",             "type"),
        ("Disabled",         "disabled"),
        ("Run As ID",        "_runAsId"),
        ("Scopes",           "_scopes"),
        ("Created",          "createdAt"),
    ])
    print(f"\nTotal: {len(clients)}")


# ---------------------------------------------------------------------------
# Credential resolution helpers (CLI flag > profile > env var > error)
# ---------------------------------------------------------------------------

def _resolve_endpoint(args: argparse.Namespace, profile_data: dict) -> str:
    endpoint_arg = getattr(args, "endpoint", None)
    cli_region   = getattr(args, "region",   None)
    if endpoint_arg:
        return resolve_endpoint(endpoint_arg)
    if cli_region:
        return resolve_endpoint(cli_region)
    if profile_data.get("endpoint"):
        logger.debug("Using endpoint from profile: %s", profile_data["endpoint"])
        return profile_data["endpoint"]
    if os.environ.get("SUMO_REGION"):
        logger.debug("Using endpoint from SUMO_REGION env var: %s", os.environ["SUMO_REGION"])
        return resolve_endpoint(os.environ["SUMO_REGION"])
    logger.error(
        "No endpoint configured. Use --region / --endpoint, set SUMO_REGION, "
        "or run 'store-creds --profile %s --region REGION'.",
        args.profile,
    )
    sys.exit(1)


def _require_basic_auth(args: argparse.Namespace, profile: str,
                        profile_data: dict) -> tuple[str, str]:
    """Resolve access_id + access_key: CLI flag > profile > env var > error."""
    # access_id
    if getattr(args, "access_id", None):
        aid = args.access_id
        aid_src, aid_cat = "CLI flag", "cli"
    elif profile_data.get("access_id"):
        aid = profile_data["access_id"]
        aid_src, aid_cat = f"profile '{profile}'", "profile"
    elif os.environ.get("SUMO_ACCESS_ID"):
        aid = os.environ["SUMO_ACCESS_ID"]
        aid_src, aid_cat = "SUMO_ACCESS_ID env var", "env"
    else:
        aid = None
        aid_src, aid_cat = "not found", "none"

    # access_key (never logged)
    if getattr(args, "access_key", None):
        akey = args.access_key
        akey_src, akey_cat = "CLI flag", "cli"
    else:
        akey = _keychain_get(_access_key_key(profile))
        if akey:
            akey_src, akey_cat = f"keychain (profile='{profile}')", "profile"
        elif os.environ.get("SUMO_ACCESS_KEY"):
            akey = os.environ["SUMO_ACCESS_KEY"]
            akey_src, akey_cat = "SUMO_ACCESS_KEY env var", "env"
        else:
            akey_src, akey_cat = "not found", "none"

    logger.debug("access_id  : %s  (source: %s)", aid, aid_src)
    logger.debug("access_key : %s  (source: %s)", "***set***" if akey else "MISSING", akey_src)

    # Warn only when id and key come from categorically different sources
    # (e.g. one from env var, one from profile) — same category is fine.
    if aid and akey and aid_cat != akey_cat:
        logger.warning(
            "access_id and access_key are from different sources (%s vs %s) — "
            "if they belong to different accounts this will cause a 401.",
            aid_src, akey_src,
        )

    if not aid or not akey:
        missing = []
        if not aid:
            missing.append("access_id (--access-id, profile 'store-creds', or SUMO_ACCESS_ID)")
        if not akey:
            missing.append(f"access_key (profile 'store-creds --profile {profile}', or SUMO_ACCESS_KEY)")
        logger.error("Missing Basic auth credentials:\n  %s", "\n  ".join(missing))
        sys.exit(1)
    return aid, akey


def _require_oauth_creds(args: argparse.Namespace, profile: str,
                         profile_data: dict) -> tuple[str, str]:
    """Resolve client_id + client_secret: CLI flag > profile > env var > error."""
    # client_id
    if getattr(args, "client_id", None):
        cid = args.client_id
        cid_src = "CLI flag"
    elif profile_data.get("client_id"):
        cid = profile_data["client_id"]
        cid_src = f"profile '{profile}'"
    elif os.environ.get("SUMO_CLIENT_ID"):
        cid = os.environ["SUMO_CLIENT_ID"]
        cid_src = "SUMO_CLIENT_ID env var"
    else:
        cid = None
        cid_src = "not found"

    # client_secret (never logged)
    if getattr(args, "client_secret", None):
        csec = args.client_secret
        csec_src = "CLI flag"
    else:
        csec = _keychain_get(_client_secret_key(profile))
        if csec:
            csec_src = f"keychain (profile='{profile}')"
        elif os.environ.get("SUMO_CLIENT_SECRET"):
            csec = os.environ["SUMO_CLIENT_SECRET"]
            csec_src = "SUMO_CLIENT_SECRET env var"
        else:
            csec_src = "not found"

    logger.debug("client_id     : %s  (source: %s)", cid, cid_src)
    logger.debug("client_secret : %s  (source: %s)", "***set***" if csec else "MISSING", csec_src)

    if not cid or not csec:
        missing = []
        if not cid:
            missing.append("client_id (--client-id, profile 'store-creds', or SUMO_CLIENT_ID)")
        if not csec:
            missing.append(f"client_secret (profile 'store-creds --profile {profile}', or SUMO_CLIENT_SECRET)")
        logger.error("Missing OAuth credentials:\n  %s", "\n  ".join(missing))
        sys.exit(1)
    return cid, csec


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _prompt_value(label: str, current: str | None) -> str | None:
    """Prompt for a non-sensitive value. Shows current; empty input keeps it."""
    hint = f"current: {current}" if current else "not set"
    raw = input(f"  {label} [{hint}]: ").strip()
    return raw if raw else current


def _prompt_secret(label: str, has_existing: bool) -> str | None:
    """Prompt for a secret via getpass. Empty input keeps the existing value."""
    hint = "enter to keep existing" if has_existing else "enter value"
    val = getpass.getpass(f"  {label} [{hint}]: ").strip()
    return val if val else None


def cmd_store_creds(args: argparse.Namespace, session: Session) -> None:
    """Configure a profile interactively; store secrets in the OS keychain."""
    profile = args.profile

    if not _keychain_available():
        logger.error(
            "No keychain backend available.\n"
            "macOS/Windows: system keychain should work automatically.\n"
            "Linux: install secretstorage – pip install secretstorage"
        )
        sys.exit(1)

    # Seed from CLI flags / env vars, then fill from existing profile
    p = session.get(profile).copy()

    # Apply any CLI overrides as starting values before prompting
    cli_region   = getattr(args, "region",    None) or os.environ.get("SUMO_REGION")
    cli_endpoint = getattr(args, "endpoint",  None)
    cli_client   = getattr(args, "client_id", None) or os.environ.get("SUMO_CLIENT_ID")
    cli_access   = getattr(args, "access_id", None) or os.environ.get("SUMO_ACCESS_ID")

    if cli_endpoint:
        p["endpoint"] = resolve_endpoint(cli_endpoint)
    elif cli_region:
        p["endpoint"] = resolve_endpoint(cli_region)
    if cli_client:
        p["client_id"] = cli_client
    if cli_access:
        p["access_id"] = cli_access

    print(f"Configuring profile '{profile}' – press Enter to keep the current value.\n")

    # --- region / endpoint --------------------------------------------------
    current_endpoint = p.get("endpoint")
    raw = input(f"  region or endpoint URL [current: {current_endpoint or 'not set'}]: ").strip()
    if raw:
        try:
            p["endpoint"] = resolve_endpoint(raw)
        except ValueError as exc:
            logger.error("%s", exc)
            sys.exit(1)

    # --- OAuth client credentials -------------------------------------------
    p["client_id"] = _prompt_value("client_id    ", p.get("client_id"))

    has_secret = bool(_keychain_get(_client_secret_key(profile)))
    new_secret = _prompt_secret("client_secret", has_secret)

    # --- Basic auth credentials ---------------------------------------------
    p["access_id"] = _prompt_value("access_id    ", p.get("access_id"))

    has_key = bool(_keychain_get(_access_key_key(profile)))
    new_key = _prompt_secret("access_key   ", has_key)

    # --- Persist ------------------------------------------------------------
    stored: list[str] = []

    if new_secret:
        if _keychain_set(_client_secret_key(profile), new_secret):
            stored.append(f"  client_secret  → keychain  (profile={profile})")
    elif not has_secret and p.get("client_id"):
        logger.warning("No client_secret stored – you will need one to run 'login'.")

    if new_key:
        if _keychain_set(_access_key_key(profile), new_key):
            stored.append(f"  access_key     → keychain  (profile={profile})")
    elif not has_key and p.get("access_id"):
        logger.warning("No access_key stored – you will need one for API commands.")

    # Persist non-sensitive profile config
    session.set(profile, p)

    print(f"Profile '{profile}' configured.")
    if p.get("endpoint"):
        print(f"  endpoint  : {p['endpoint']}")
    if p.get("client_id"):
        print(f"  client_id : {p['client_id']}")
    if p.get("access_id"):
        print(f"  access_id : {p['access_id']}")
    if stored:
        print("Secrets stored in OS keychain:")
        for s in stored:
            print(s)


def cmd_clear_creds(args: argparse.Namespace, session: Session) -> None:
    """Remove keychain secrets for a profile."""
    profile = args.profile
    removed: list[str] = []

    for key, label in [
        (_client_secret_key(profile), "client_secret"),
        (_access_key_key(profile),    "access_key"),
    ]:
        if _keychain_delete(key):
            removed.append(f"  {label}  (profile={profile})")
        else:
            print(f"  {label} for profile '{profile}' – not found or already removed")

    if removed:
        print("Removed from OS keychain:")
        for r in removed:
            print(r)
    print("Note: session file entry for this profile is unchanged. "
          "Use 'delete-profile' to remove it entirely.")


def cmd_list_profiles(args: argparse.Namespace, session: Session) -> None:
    """List all configured profiles with status summary."""
    names = session.names()
    if not names:
        print("No profiles configured. Run 'store-creds' to create one.")
        return

    if getattr(args, "output", "table") == "json":
        print(json.dumps([session.profile_status(n) for n in names], indent=2))
        return

    # Table output
    col_w = max(len(n) for n in names)
    header = (
        f"{'Profile':<{col_w}} | {'Status':<9} | {'Endpoint':<36} | "
        f"{'client_id':<20} | {'access_id':<20} | {'secret':<6} | {'key':<6}"
    )
    sep = "-" * len(header)
    print(header)
    print(sep)
    for name in names:
        s = session.profile_status(name)
        print(
            f"{name:<{col_w}} | {s['status']:<9} | {(s['endpoint'] or ''):<36} | "
            f"{(s['client_id'] or ''):<20} | {(s['access_id'] or ''):<20} | "
            f"{'yes' if s['client_secret_stored'] else 'no':<6} | "
            f"{'yes' if s['access_key_stored'] else 'no':<6}"
        )


def cmd_delete_profile(args: argparse.Namespace, session: Session) -> None:
    """Remove a profile from the session file and clear its keychain entries."""
    profile = args.profile
    if not session.get(profile):
        print(f"Profile '{profile}' does not exist.")
        return
    _keychain_delete(_client_secret_key(profile))
    _keychain_delete(_access_key_key(profile))
    session.delete(profile)
    print(f"Profile '{profile}' deleted (session + keychain entries removed).")


def cmd_login(args: argparse.Namespace, session: Session) -> None:
    profile      = args.profile
    profile_data = session.get(profile)
    endpoint     = _resolve_endpoint(args, profile_data)
    client_id, client_secret = _require_oauth_creds(args, profile, profile_data)

    scopes    = [s.strip() for s in args.scopes.split()] if getattr(args, "scopes", None) else None
    token_url = getattr(args, "token_url", None) or None

    logger.info("Requesting access token for profile '%s' from %s …", profile, endpoint)
    token_resp = _fetch_oauth_token(endpoint, client_id, client_secret,
                                    scopes=scopes, token_url=token_url)
    session.store_token(profile, endpoint, client_id, client_secret, token_resp,
                        scopes=scopes, token_url=token_url)

    s = session.profile_status(profile)
    print(f"Login successful (profile: {profile}).")
    print(f"  Endpoint           : {s['endpoint']}")
    print(f"  Client ID          : {s['client_id']}")
    print(f"  Expires at (UTC)   : {s['expires_at_utc']}  ({s['remaining']} remaining)")
    print(f"  Secret in keychain : {s['client_secret_stored']}")
    if scopes:
        print(f"  Scopes             : {' '.join(scopes)}")
    if token_url:
        print(f"  Token URL          : {token_url}")


def cmd_logout(args: argparse.Namespace, session: Session) -> None:
    profile = args.profile
    p = session.get(profile)
    if not p:
        print(f"Profile '{profile}' has no session.")
        return
    # Clear only the token fields, keep profile config intact
    for key in ("access_token", "token_type", "expires_at", "expires_in"):
        p.pop(key, None)
    session.set(profile, p)
    print(f"Token cleared for profile '{profile}'. Profile config retained.")
    print("Use 'delete-profile' to remove the profile entirely, "
          "or 'clear-creds' to remove keychain secrets.")


def cmd_export_env(args: argparse.Namespace, session: Session) -> None:
    """Print shell export statements for MCP environment variables."""
    profile      = args.profile
    profile_data = session.get(profile)
    p            = profile_data

    client_id     = p.get("client_id") or ""
    client_secret = _keychain_get(_client_secret_key(profile)) or ""
    endpoint      = p.get("endpoint", "")

    # Derive token URL from known endpoint mapping, fallback to env or default
    token_url = (
        p.get("token_url")
        or _API_TO_TOKEN_URL.get(endpoint.rstrip("/"))
        or os.environ.get("SUMOLOGIC_OAUTH_TOKEN_URL", "")
    )

    # Get (or refresh) the access token
    access_token = ""
    if client_id and client_secret:
        bearer = session.require_token(profile)
        access_token = bearer.removeprefix("Bearer ")

    if not client_secret:
        logger.warning(
            "client_secret not found in keychain for profile '%s'. "
            "Run 'store-creds' or 'create-oauth-client --save-creds' first.",
            profile,
        )

    lines = [
        f'export SUMOLOGIC_MCP_URL="https://mcp.sumologic.com/mcp"',
        f'export SUMOLOGIC_OAUTH_CLIENT_ID="{client_id}"',
        f'export SUMOLOGIC_OAUTH_CLIENT_SECRET="{client_secret}"',
        f'export SUMOLOGIC_OAUTH_TOKEN_URL="{token_url}"',
        f'export SUMOLOGIC_OAUTH_ACCESS_TOKEN="{access_token}"',
    ]

    if args.shell == "fish":
        lines = [
            f'set -x SUMOLOGIC_MCP_URL "https://mcp.sumologic.com/mcp"',
            f'set -x SUMOLOGIC_OAUTH_CLIENT_ID "{client_id}"',
            f'set -x SUMOLOGIC_OAUTH_CLIENT_SECRET "{client_secret}"',
            f'set -x SUMOLOGIC_OAUTH_TOKEN_URL "{token_url}"',
            f'set -x SUMOLOGIC_OAUTH_ACCESS_TOKEN "{access_token}"',
        ]

    for line in lines:
        print(line)


def cmd_token(args: argparse.Namespace, session: Session) -> None:
    profile = args.profile
    auth    = session.require_token(profile)
    if args.raw:
        print(auth)
        return
    s = session.profile_status(profile)
    print(f"Profile            : {profile}")
    print(f"Status             : {s['status']}")
    print(f"Endpoint           : {s['endpoint']}")
    print(f"Client ID          : {s['client_id']}")
    print(f"Expires at (UTC)   : {s['expires_at_utc']}  ({s['remaining']} remaining)")
    print(f"Secret in keychain : {s['client_secret_stored']}")
    print(f"Token              : {auth[:50]}…")


def cmd_status(args: argparse.Namespace, session: Session) -> None:
    profile = args.profile
    if profile == "__all__":
        print(json.dumps([session.profile_status(n) for n in session.names()], indent=2))
    else:
        print(json.dumps(session.profile_status(profile), indent=2))


def _apply_regex_filter(items: list[dict], pattern: str | None,
                        fields: list[str]) -> list[dict]:
    """
    Return items where any of the given fields matches pattern (case-insensitive regex).
    fields is checked in order; the item is included if any field matches.
    """
    if not pattern:
        return items
    import re
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        logger.error("Invalid filter regex '%s': %s", pattern, exc)
        sys.exit(1)
    matched = [
        item for item in items
        if any(rx.search(str(item.get(f, ""))) for f in fields)
    ]
    logger.info(
        "Filter '%s' on [%s] matched %d of %d result(s)",
        pattern, ", ".join(fields), len(matched), len(items),
    )
    return matched


def cmd_access_keys(args: argparse.Namespace, session: Session) -> None:
    profile      = args.profile
    profile_data = session.get(profile)
    endpoint     = _resolve_endpoint(args, profile_data)
    aid, akey    = _require_basic_auth(args, profile, profile_data)
    logger.info("Fetching access keys [profile=%s, endpoint=%s] …", profile, endpoint)
    all_fields = ["id", "label", "createdBy", "serviceAccountId"]
    filter_fields = all_fields if args.filter_field == "all" else [args.filter_field]
    keys = _apply_regex_filter(
        list_access_keys(endpoint, _basic_auth_header(aid, akey), args.limit),
        args.filter, filter_fields,
    )
    print_access_keys(keys, args.output)


def cmd_users(args: argparse.Namespace, session: Session) -> None:
    profile      = args.profile
    profile_data = session.get(profile)
    endpoint     = _resolve_endpoint(args, profile_data)
    aid, akey    = _require_basic_auth(args, profile, profile_data)
    logger.info("Fetching users [profile=%s, endpoint=%s] …", profile, endpoint)
    users = _apply_regex_filter(
        list_users(endpoint, _basic_auth_header(aid, akey), args.limit),
        args.filter, ["email"],
    )
    print_users(users, args.output)


def cmd_service_accounts(args: argparse.Namespace, session: Session) -> None:
    profile      = args.profile
    profile_data = session.get(profile)
    endpoint     = _resolve_endpoint(args, profile_data)
    aid, akey    = _require_basic_auth(args, profile, profile_data)
    logger.info("Fetching service accounts [profile=%s, endpoint=%s] …", profile, endpoint)
    accounts = _apply_regex_filter(
        list_service_accounts(endpoint, _basic_auth_header(aid, akey), args.limit),
        args.filter, ["email"],
    )
    print_service_accounts(accounts, args.output)


def cmd_oauth_consents(args: argparse.Namespace, session: Session) -> None:
    profile      = args.profile
    profile_data = session.get(profile)
    endpoint     = _resolve_endpoint(args, profile_data)
    aid, akey    = _require_basic_auth(args, profile, profile_data)
    logger.info("Fetching OAuth consents [profile=%s, endpoint=%s] …", profile, endpoint)
    consents = _apply_regex_filter(
        list_oauth_consents(endpoint, _basic_auth_header(aid, akey), args.limit),
        args.filter, ["clientId", "userId"],
    )
    print_oauth_consents(consents, args.output)


def cmd_oauth_scopes(args: argparse.Namespace, session: Session) -> None:
    profile      = args.profile
    profile_data = session.get(profile)
    endpoint     = _resolve_endpoint(args, profile_data)
    aid, akey    = _require_basic_auth(args, profile, profile_data)
    logger.info("Fetching OAuth scopes [profile=%s, endpoint=%s] …", profile, endpoint)
    filter_fields = [args.filter_field] if args.filter_field != "both" else ["id", "label"]
    scopes = _apply_regex_filter(
        list_oauth_scopes(endpoint, _basic_auth_header(aid, akey)),
        args.filter, filter_fields,
    )
    print_oauth_scopes(scopes, args.output)


def cmd_update_oauth_client(args: argparse.Namespace, session: Session) -> None:
    profile      = args.profile
    profile_data = session.get(profile)
    endpoint     = _resolve_endpoint(args, profile_data)
    aid, akey    = _require_basic_auth(args, profile, profile_data)

    if args.from_file:
        try:
            payload = json.loads(Path(args.from_file).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Cannot read --from-file '%s': %s", args.from_file, exc)
            sys.exit(1)
        logger.info("Updating OAuth client '%s' from file '%s' [profile=%s, endpoint=%s] …",
                    args.id, args.from_file, profile, endpoint)
    else:
        if not args.name:
            logger.error("--name is required when not using --from-file")
            sys.exit(1)
        payload = {"name": args.name}
        if args.description:
            payload["description"] = args.description
        if args.redirect_uris:
            payload["redirectUris"] = [u.strip() for u in args.redirect_uris.split(",") if u.strip()]
        if args.scopes:
            payload["scopes"] = [s.strip() for s in args.scopes.split(",") if s.strip()]
        logger.info("Updating OAuth client '%s' [profile=%s, endpoint=%s] …",
                    args.id, profile, endpoint)

    client = update_oauth_client(endpoint, _basic_auth_header(aid, akey), args.id, payload)
    print(f"OAuth client '{args.id}' updated.")
    print_oauth_client(client, args.output)


def cmd_delete_oauth_client(args: argparse.Namespace, session: Session) -> None:
    profile      = args.profile
    profile_data = session.get(profile)
    endpoint     = _resolve_endpoint(args, profile_data)
    aid, akey    = _require_basic_auth(args, profile, profile_data)
    logger.info("Deleting OAuth client '%s' [profile=%s, endpoint=%s] …",
                args.id, profile, endpoint)
    delete_oauth_client(endpoint, _basic_auth_header(aid, akey), args.id)
    print(f"OAuth client '{args.id}' deleted.")


def cmd_get_oauth_client(args: argparse.Namespace, session: Session) -> None:
    profile      = args.profile
    profile_data = session.get(profile)
    endpoint     = _resolve_endpoint(args, profile_data)
    aid, akey    = _require_basic_auth(args, profile, profile_data)
    logger.info("Fetching OAuth client '%s' [profile=%s, endpoint=%s] …",
                args.id, profile, endpoint)
    client = get_oauth_client(endpoint, _basic_auth_header(aid, akey), args.id)
    print_oauth_client(client, args.output)


def cmd_create_oauth_client(args: argparse.Namespace, session: Session) -> None:
    profile      = args.profile
    profile_data = session.get(profile)
    endpoint     = _resolve_endpoint(args, profile_data)
    aid, akey    = _require_basic_auth(args, profile, profile_data)

    if args.from_file:
        try:
            payload = json.loads(Path(args.from_file).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Cannot read --from-file '%s': %s", args.from_file, exc)
            sys.exit(1)
        logger.info("Creating OAuth client from file '%s' [profile=%s, endpoint=%s] …",
                    args.from_file, profile, endpoint)
    else:
        if not args.name:
            logger.error("--name is required when not using --from-file")
            sys.exit(1)
        if not args.redirect_uris and not args.scopes:
            logger.error("--redirect-uris and --scopes are required when not using --from-file")
            sys.exit(1)
        payload = {"name": args.name}
        if args.description:
            payload["description"] = args.description
        if args.redirect_uris:
            payload["redirectUris"] = [u.strip() for u in args.redirect_uris.split(",") if u.strip()]
        if args.scopes:
            payload["scopes"] = [s.strip() for s in args.scopes.split(",") if s.strip()]
        logger.info("Creating OAuth client '%s' [profile=%s, endpoint=%s] …",
                    args.name, profile, endpoint)

    client = create_oauth_client(endpoint, _basic_auth_header(aid, akey), payload)
    print("OAuth client created.")
    print_oauth_client(client, args.output)

    if args.save_creds:
        returned_id     = client.get("clientId")
        returned_secret = client.get("clientSecret")
        if not returned_id or not returned_secret:
            logger.warning(
                "--save-creds requested but API response did not include clientId/clientSecret. "
                "Profile credentials unchanged."
            )
        else:
            p = session.get(profile)
            p["client_id"] = returned_id
            session.set(profile, p)
            if _keychain_available() and _keychain_set(_client_secret_key(profile), returned_secret):
                print(f"\nCredentials saved to profile '{profile}':")
                print(f"  client_id     : {returned_id}")
                print(f"  client_secret : stored in OS keychain")
                print("Run 'sumo-oauth login' to obtain a token with the new client.")
            else:
                logger.warning(
                    "client_id saved to profile '%s' but client_secret could not be stored "
                    "in keychain. Store it manually with 'store-creds --profile %s'.",
                    profile, profile,
                )


def cmd_oauth_clients(args: argparse.Namespace, session: Session) -> None:
    profile      = args.profile
    profile_data = session.get(profile)
    endpoint     = _resolve_endpoint(args, profile_data)
    aid, akey    = _require_basic_auth(args, profile, profile_data)
    logger.info("Fetching OAuth clients [profile=%s, endpoint=%s] …", profile, endpoint)
    clients = _apply_regex_filter(
        list_oauth_clients(endpoint, _basic_auth_header(aid, akey), args.limit),
        args.filter, ["name", "clientId"],
    )
    print_oauth_clients(clients, args.output)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _add_profile_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile", "-p",
        default=os.environ.get("SUMO_PROFILE", DEFAULT_PROFILE),
        metavar="PROFILE",
        help=f"Profile to use (default: '{DEFAULT_PROFILE}'). Env: SUMO_PROFILE",
    )


def _add_endpoint_args(parser: argparse.ArgumentParser) -> None:
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument(
        "--region",
        choices=list(REGIONS),
        metavar="REGION",
        help=f"Region override ({', '.join(REGIONS)}). Env: SUMO_REGION",
    )
    grp.add_argument(
        "--endpoint",
        help="Full API base URL override (e.g. https://api.us2.sumologic.com)",
    )


def _add_basic_auth_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--access-id",  metavar="AID",
                        help="Access ID override. Env: SUMO_ACCESS_ID")
    parser.add_argument("--access-key", metavar="AKEY",
                        help="Access key override. Prefer keychain (store-creds).")


def _add_output_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", "-o", choices=["table", "json"], default="table",
                        help="Output format (default: table)")


def _add_limit_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int, default=100,
                        help="Page size for API requests (default: 100)")


def _add_filter_arg(parser: argparse.ArgumentParser, help: str = "Filter results using a case-insensitive regex") -> None:
    parser.add_argument("--filter", "-f", metavar="REGEX", help=help)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sumo-oauth",
        description="Sumo Logic OAuth CLI – multi-profile session and API management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Profile setup (one-time per environment):
  sumo-oauth store-creds --profile prod --region us1 --client-id CID --access-id AID
  sumo-oauth store-creds --profile staging --region us2 --client-id CID2 --access-id AID2

OAuth token commands:
  sumo-oauth login  [--profile prod]
  sumo-oauth token  [--profile prod] [--raw]
  sumo-oauth logout [--profile prod]

Admin API commands (all resolved from profile):
  sumo-oauth users            [--profile prod]
  sumo-oauth service-accounts [--profile prod] [--output json]
  sumo-oauth oauth-clients    [--profile prod]

Profile management:
  sumo-oauth list-profiles
  sumo-oauth status         [--profile prod | --all]
  sumo-oauth delete-profile --profile prod
  sumo-oauth clear-creds    --profile prod

Credential resolution order (most to least preferred):
  CLI flag  →  env var  →  profile (session file + OS keychain)  →  error

Environment variables:
  SUMO_PROFILE         Active profile (default: 'default')
  SUMO_REGION          Region override
  SUMO_CLIENT_ID / SUMO_CLIENT_SECRET   OAuth credential overrides
  SUMO_ACCESS_ID / SUMO_ACCESS_KEY      Basic auth credential overrides

  A .env file in the current directory is loaded automatically
  if python-dotenv is installed: uv pip install "sumo-oauth[dotenv]"
        """,
    )

    # Global options
    parser.add_argument(
        "--profile", "-p",
        default=os.environ.get("SUMO_PROFILE", DEFAULT_PROFILE),
        metavar="PROFILE",
        help=f"Profile to use (default: '{DEFAULT_PROFILE}'). Env: SUMO_PROFILE",
    )
    parser.add_argument(
        "--session-file",
        type=Path,
        default=DEFAULT_SESSION_FILE,
        help=f"Path to session file (default: {DEFAULT_SESSION_FILE})",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # -- store-creds ---------------------------------------------------------
    p_store = sub.add_parser(
        "store-creds",
        help="Configure a profile: save settings and store secrets in OS keychain",
    )
    _add_profile_arg(p_store)
    _add_endpoint_args(p_store)
    p_store.add_argument("--client-id", metavar="CID",
                         help="OAuth client ID (non-sensitive; stored in profile config)")
    p_store.add_argument("--access-id", metavar="AID",
                         help="Access ID (non-sensitive; stored in profile config)")

    # -- clear-creds ---------------------------------------------------------
    p_cc = sub.add_parser(
        "clear-creds",
        help="Remove keychain secrets for a profile (profile config kept)",
    )
    _add_profile_arg(p_cc)

    # -- list-profiles -------------------------------------------------------
    p_lp = sub.add_parser("list-profiles", help="List all configured profiles")
    p_lp.add_argument("--output", "-o", choices=["table", "json"], default="table")

    # -- delete-profile ------------------------------------------------------
    p_dp = sub.add_parser(
        "delete-profile",
        help="Remove a profile and its keychain secrets entirely",
    )
    _add_profile_arg(p_dp)

    # -- login ---------------------------------------------------------------
    p_login = sub.add_parser("login", help="Obtain OAuth token for a profile")
    _add_profile_arg(p_login)
    _add_endpoint_args(p_login)
    p_login.add_argument("--client-id",     metavar="CID",
                         help="OAuth client ID override. Env: SUMO_CLIENT_ID")
    p_login.add_argument("--client-secret", metavar="SECRET",
                         help="OAuth client secret override. Prefer keychain.")
    p_login.add_argument("--scopes", metavar="SCOPE [SCOPE…]",
                         help="Space-separated list of scopes to request "
                              "(e.g. 'runLogSearch viewCollectors'). "
                              "Stored in profile and reused on auto-refresh.")
    p_login.add_argument("--token-url", metavar="URL",
                         help="Override the token endpoint URL "
                              "(default: {endpoint}/oauth/v2/token). "
                              "Use if your account uses a different token host "
                              "(e.g. https://service.sumologic.com/oauth2/token).")

    # -- logout --------------------------------------------------------------
    p_lo = sub.add_parser("logout", help="Clear the OAuth token for a profile")
    _add_profile_arg(p_lo)

    # -- export-env ----------------------------------------------------------
    p_ee = sub.add_parser(
        "export-env",
        help="Print shell export statements for MCP environment variables",
        description=(
            "Prints export statements for all environment variables required by the "
            "Sumo Logic MCP server, including SUMOLOGIC_OAUTH_CLIENT_SECRET from the "
            "OS keychain and a refreshed access token.\n\n"
            "Usage:\n"
            "  eval $(sumo-oauth export-env)\n"
            "  sumo-oauth export-env >> ~/.zshrc"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_profile_arg(p_ee)
    p_ee.add_argument(
        "--shell",
        choices=["bash", "fish"],
        default="bash",
        help="Shell syntax to use for export statements (default: bash)",
    )

    # -- token ---------------------------------------------------------------
    p_token = sub.add_parser("token", help="Show or refresh the access token for a profile")
    _add_profile_arg(p_token)
    p_token.add_argument("--raw", action="store_true",
                         help="Print only 'Bearer <token>' (for scripting)")

    # -- status --------------------------------------------------------------
    p_status = sub.add_parser("status", help="Show profile status as JSON")
    _add_profile_arg(p_status)
    p_status.add_argument("--all", dest="profile", action="store_const", const="__all__",
                           help="Show status of all profiles")

    # -- access-keys ---------------------------------------------------------
    p_ak = sub.add_parser("access-keys", help="List access keys [Basic auth]")
    _add_profile_arg(p_ak)
    _add_endpoint_args(p_ak)
    _add_basic_auth_args(p_ak)
    _add_output_arg(p_ak)
    _add_limit_arg(p_ak)
    _add_filter_arg(p_ak, "Filter using a case-insensitive regex (see --filter-field)")
    p_ak.add_argument(
        "--filter-field",
        choices=["id", "label", "createdBy", "serviceAccountId", "all"],
        default="all",
        help="Which field to apply --filter against (default: all)",
    )

    # -- users ---------------------------------------------------------------
    p_users = sub.add_parser("users", help="List users [Basic auth]")
    _add_profile_arg(p_users)
    _add_endpoint_args(p_users)
    _add_basic_auth_args(p_users)
    _add_output_arg(p_users)
    _add_limit_arg(p_users)
    _add_filter_arg(p_users, "Filter by email (case-insensitive regex)")

    # -- service-accounts ----------------------------------------------------
    p_sa = sub.add_parser("service-accounts", help="List service accounts [Basic auth]")
    _add_profile_arg(p_sa)
    _add_endpoint_args(p_sa)
    _add_basic_auth_args(p_sa)
    _add_output_arg(p_sa)
    _add_limit_arg(p_sa)
    _add_filter_arg(p_sa, "Filter by email (case-insensitive regex)")

    # -- oauth-consents ------------------------------------------------------
    p_oco = sub.add_parser("oauth-consents", help="List OAuth consents [Basic auth]")
    _add_profile_arg(p_oco)
    _add_endpoint_args(p_oco)
    _add_basic_auth_args(p_oco)
    _add_output_arg(p_oco)
    _add_limit_arg(p_oco)
    _add_filter_arg(p_oco, "Filter by clientId or userId (case-insensitive regex)")

    # -- oauth-scopes --------------------------------------------------------
    p_os = sub.add_parser("oauth-scopes", help="List available OAuth scopes [Basic auth]")
    _add_profile_arg(p_os)
    _add_endpoint_args(p_os)
    _add_basic_auth_args(p_os)
    _add_output_arg(p_os)
    _add_filter_arg(p_os, "Filter by id/label using a case-insensitive regex (see --filter-field)")
    p_os.add_argument(
        "--filter-field",
        choices=["id", "label", "both"],
        default="both",
        help="Which field to apply --filter regex against (default: both)",
    )

    # -- delete-oauth-client -------------------------------------------------
    p_doc = sub.add_parser("delete-oauth-client", help="Delete an OAuth client by ID [Basic auth]")
    _add_profile_arg(p_doc)
    _add_endpoint_args(p_doc)
    _add_basic_auth_args(p_doc)
    p_doc.add_argument("--id", required=True, metavar="CLIENT_ID",
                       help="ID of the OAuth client to delete")

    # -- update-oauth-client -------------------------------------------------
    p_uoc = sub.add_parser("update-oauth-client", help="Update an OAuth client by ID [Basic auth]")
    _add_profile_arg(p_uoc)
    _add_endpoint_args(p_uoc)
    _add_basic_auth_args(p_uoc)
    _add_output_arg(p_uoc)
    p_uoc.add_argument("--id", required=True, metavar="CLIENT_ID",
                       help="ID of the OAuth client to update")
    p_uoc.add_argument("--from-file", metavar="FILE",
                       help="Path to a JSON file containing the full update payload (posted as-is)")
    p_uoc.add_argument("--name", default=None,
                       help="New display name (required without --from-file)")
    p_uoc.add_argument("--description", default="",
                       help="New description")
    p_uoc.add_argument("--redirect-uris", default=None, metavar="URI[,URI…]",
                       help="Comma-separated list of allowed redirect URIs")
    p_uoc.add_argument("--scopes", default=None, metavar="SCOPE[,SCOPE…]",
                       help="Comma-separated list of OAuth scope IDs")

    # -- get-oauth-client ----------------------------------------------------
    p_goc = sub.add_parser("get-oauth-client", help="Get an OAuth client by ID [Basic auth]")
    _add_profile_arg(p_goc)
    _add_endpoint_args(p_goc)
    _add_basic_auth_args(p_goc)
    _add_output_arg(p_goc)
    p_goc.add_argument("--id", required=True, metavar="CLIENT_ID",
                       help="ID of the OAuth client to retrieve")

    # -- create-oauth-client -------------------------------------------------
    p_coc = sub.add_parser("create-oauth-client", help="Create a new OAuth client [Basic auth]")
    _add_profile_arg(p_coc)
    _add_endpoint_args(p_coc)
    _add_basic_auth_args(p_coc)
    _add_output_arg(p_coc)
    p_coc.add_argument("--save-creds", action="store_true",
                       help="Save the returned clientId to the profile and store "
                            "clientSecret in the OS keychain (enables immediate 'login')")
    p_coc.add_argument("--from-file", metavar="FILE",
                       help="Path to a JSON file containing the full client payload "
                            "(posted as-is; overrides all other field flags)")
    p_coc.add_argument("--name", default=None,
                       help="Display name for the OAuth client (required without --from-file)")
    p_coc.add_argument("--description", default="",
                       help="Optional description")
    p_coc.add_argument("--redirect-uris", default=None, metavar="URI[,URI…]",
                       help="Comma-separated list of allowed redirect URIs")
    p_coc.add_argument("--scopes", default=None, metavar="SCOPE[,SCOPE…]",
                       help="Comma-separated list of OAuth scope IDs to grant")

    # -- oauth-clients -------------------------------------------------------
    p_oc = sub.add_parser("oauth-clients", help="List OAuth clients [Basic auth]")
    _add_profile_arg(p_oc)
    _add_endpoint_args(p_oc)
    _add_basic_auth_args(p_oc)
    _add_output_arg(p_oc)
    _add_limit_arg(p_oc)
    _add_filter_arg(p_oc, "Filter by name or clientId (case-insensitive regex)")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

COMMAND_MAP = {
    "store-creds":      cmd_store_creds,
    "clear-creds":      cmd_clear_creds,
    "list-profiles":    cmd_list_profiles,
    "delete-profile":   cmd_delete_profile,
    "export-env":       cmd_export_env,
    "login":            cmd_login,
    "logout":           cmd_logout,
    "token":            cmd_token,
    "status":           cmd_status,
    "access-keys":      cmd_access_keys,
    "users":            cmd_users,
    "service-accounts": cmd_service_accounts,
    "oauth-consents":   cmd_oauth_consents,
    "oauth-scopes":     cmd_oauth_scopes,
    "delete-oauth-client": cmd_delete_oauth_client,
    "update-oauth-client": cmd_update_oauth_client,
    "get-oauth-client":    cmd_get_oauth_client,
    "create-oauth-client": cmd_create_oauth_client,
    "oauth-clients":       cmd_oauth_clients,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.log_level)
    session = Session(args.session_file)
    COMMAND_MAP[args.command](args, session)


if __name__ == "__main__":
    main()
