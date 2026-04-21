#!/usr/bin/env python3
"""
Fetch one example API response item from each sumo_oauth endpoint, sanitize
sensitive values, and save as JSON mock data for unit tests.

Usage:
    uv run fetch_mock_data.py [--profile PROFILE] [--output-dir DIR]

Requires a configured profile with both Basic auth and OAuth credentials.
Output is written to mock_data/ (or --output-dir) as one JSON file per endpoint.
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

# Allow importing sumo_oauth from the same directory
sys.path.insert(0, str(Path(__file__).parent))
import sumo_oauth as so  # noqa: E402

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sanitizer: replace real IDs / emails with deterministic dummy values
# ---------------------------------------------------------------------------

class Sanitizer:
    """
    Replace sensitive values with deterministic dummy equivalents.

    The same original value always maps to the same dummy, so foreign-key
    relationships within the mock data remain internally consistent.
    """

    # Patterns ordered from most specific to least
    _PATTERNS = [
        # Sumo access key IDs: su<digit><alphanum 8+>
        (re.compile(r'^su\d[A-Za-z0-9]{8,}$'),
         lambda n: f"su0TESTKEY{n:04d}"),
        # 16-char uppercase hex IDs (Sumo entity IDs)
        (re.compile(r'^[0-9A-F]{16}$'),
         lambda n: f"{n:016X}"),
        # Mixed-case hex IDs (some endpoints use lowercase)
        (re.compile(r'^[0-9a-f]{16}$'),
         lambda n: f"{n:016x}"),
        # Email addresses
        (re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'),
         lambda n: f"test-user-{n:03d}@example.com"),
        # Long random client/token strings: must contain at least one - or _
        # (excludes camelCase scope IDs like "manageFieldExtractionRules")
        (re.compile(r'^(?=.*[-_])[A-Za-z0-9_\-]{25,}$'),
         lambda n: f"TEST-CLIENT-ID-{n:04d}"),
    ]

    def __init__(self):
        self._map: dict[str, str] = {}
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    def _replace_str(self, value: str) -> str:
        if value in self._map:
            return self._map[value]
        for pattern, fmt in self._PATTERNS:
            if pattern.match(value):
                dummy = fmt(self._next())
                self._map[value] = dummy
                return dummy
        return value

    _NAME_FIELDS = {"firstName", "lastName", "name"}
    _NAME_VALUES = {"firstName": "Jane", "lastName": "Doe", "name": "Test User"}

    def sanitize(self, obj, _key=None):
        if isinstance(obj, dict):
            return {k: self.sanitize(v, _key=k) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.sanitize(v) for v in obj]
        if isinstance(obj, str) and obj:
            if _key in self._NAME_FIELDS:
                return self._NAME_VALUES[_key]
            return self._replace_str(obj)
        return obj


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def _fetch_one(endpoint: str, path: str, auth: str, params: dict | None = None) -> dict | None:
    """Fetch a single page and return the first item, without following pagination."""
    resp = so._api_get(f"{endpoint}{path}", auth, params or {"limit": 1})
    items = resp.get("data", [])
    return items[0] if items else None


def fetch_all(profile: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    sanitizer = Sanitizer()

    session   = so.Session(so.DEFAULT_SESSION_FILE)
    p         = session.get(profile)
    endpoint  = p.get("endpoint")

    if not endpoint:
        logger.error("Profile '%s' has no endpoint configured. Run store-creds first.", profile)
        sys.exit(1)

    access_id  = p.get("access_id")
    access_key = so._keychain_get(so._access_key_key(profile))
    client_id  = p.get("client_id")
    client_secret = so._keychain_get(so._client_secret_key(profile))

    if not access_id or not access_key:
        logger.error("Basic auth credentials not found for profile '%s'.", profile)
        sys.exit(1)

    basic_auth = so._basic_auth_header(access_id, access_key)

    results: dict[str, str] = {}

    # -----------------------------------------------------------------------
    # Basic auth endpoints — one page, one item each
    # -----------------------------------------------------------------------

    endpoints_basic = [
        ("users",            "/api/v1/users"),
        ("service_accounts", "/api/v1/serviceAccounts"),
        ("access_keys",      "/api/v1/accessKeys"),
        ("oauth_clients",    "/api/v1/oauth/clients"),
        ("oauth_consents",   "/api/v1/oauth/consents"),
    ]

    for name, path in endpoints_basic:
        logger.info("Fetching %s …", name)
        try:
            sample = _fetch_one(endpoint, path, basic_auth)
            if sample is None:
                logger.warning("  %s returned no results — skipping", name)
                results[name] = "no data"
                continue
            clean = sanitizer.sanitize(sample)
            out = output_dir / f"{name}.json"
            out.write_text(json.dumps(clean, indent=2))
            logger.info("  Saved %s → %s", name, out)
            results[name] = str(out)
        except Exception as exc:
            logger.error("  %s failed: %s", name, exc)
            results[name] = f"error: {exc}"

    # oauth_scopes has no pagination — response is a flat list or {data:[]}
    logger.info("Fetching oauth_scopes …")
    try:
        resp = so._api_get(f"{endpoint}/api/v1/oauth/scopes", basic_auth)
        items = resp.get("data", resp) if isinstance(resp, dict) else resp
        sample = items[0] if items else None
        if sample is None:
            logger.warning("  oauth_scopes returned no results — skipping")
            results["oauth_scopes"] = "no data"
        else:
            clean = sanitizer.sanitize(sample)
            out = output_dir / "oauth_scopes.json"
            out.write_text(json.dumps(clean, indent=2))
            logger.info("  Saved oauth_scopes → %s", out)
            results["oauth_scopes"] = str(out)
    except Exception as exc:
        logger.error("  oauth_scopes failed: %s", exc)
        results["oauth_scopes"] = f"error: {exc}"

    # -----------------------------------------------------------------------
    # get_oauth_client — single item GET (reuse first client from list)
    # -----------------------------------------------------------------------

    logger.info("Fetching oauth_client (single) …")
    try:
        sample = _fetch_one(endpoint, "/api/v1/oauth/clients", basic_auth)
        if sample:
            raw_client_id = sample.get("clientId", "")
            client_obj = so.get_oauth_client(endpoint, basic_auth, raw_client_id)
            clean = sanitizer.sanitize(client_obj)
            out = output_dir / "oauth_client.json"
            out.write_text(json.dumps(clean, indent=2))
            logger.info("  Saved oauth_client → %s", out)
            results["oauth_client"] = str(out)
        else:
            logger.warning("  No OAuth clients found — skipping oauth_client")
            results["oauth_client"] = "no data"
    except Exception as exc:
        logger.error("  oauth_client failed: %s", exc)
        results["oauth_client"] = f"error: {exc}"

    # -----------------------------------------------------------------------
    # OAuth token endpoint
    # -----------------------------------------------------------------------

    if client_id and client_secret:
        logger.info("Fetching oauth_token …")
        try:
            token_url = so._API_TO_TOKEN_URL.get(endpoint.rstrip("/"))
            token_resp = so._fetch_oauth_token(endpoint, client_id, client_secret,
                                               token_url=token_url)
            clean = sanitizer.sanitize(token_resp)
            # Mask the actual access token value (too long / always changes)
            if "access_token" in clean:
                clean["access_token"] = "TEST_ACCESS_TOKEN"
            out = output_dir / "oauth_token.json"
            out.write_text(json.dumps(clean, indent=2))
            logger.info("  Saved oauth_token → %s", out)
            results["oauth_token"] = str(out)
        except Exception as exc:
            logger.error("  oauth_token failed: %s", exc)
            results["oauth_token"] = f"error: {exc}"
    else:
        logger.warning("OAuth client credentials not found — skipping oauth_token")
        results["oauth_token"] = "no credentials"

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------

    print("\n── Mock data fetch summary ──────────────────────────────────")
    for name, status in results.items():
        icon = "✓" if status not in ("no data", "no credentials") and not status.startswith("error") else "✗"
        print(f"  {icon}  {name:<22}  {status}")
    print(f"\nOutput dir: {output_dir.resolve()}")
    print("Run 'uv run pytest' to execute the unit tests.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", "-p", default="default",
                        help="Profile to use (default: 'default')")
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).parent / "mock_data",
                        help="Directory to write mock JSON files (default: ./mock_data)")
    parser.add_argument("--log-level", "-l",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        default="INFO",
                        help="Logging level (default: INFO)")
    args = parser.parse_args()

    # Set up logging for both this script and sumo_oauth internals
    level = getattr(logging, args.log_level)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    so.setup_logging(args.log_level)
    fetch_all(args.profile, args.output_dir)


if __name__ == "__main__":
    main()
