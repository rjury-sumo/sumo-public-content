# sumo-oauth

A command-line utility for managing Sumo Logic OAuth clients, users, and service accounts.

Supports multiple named profiles so different Sumo Logic instances (regions, accounts) can be managed from one tool. Secrets are stored in the OS keychain — never on disk.

> For a step-by-step walkthrough of setting up OAuth for the Sumo Logic MCP server, see [mcp-setup.md](mcp-setup.md).

## Upgrading from 0.1.x

Version 0.2.0 added `oauth_client_type` as a required field on profiles (values: `ClientCredentialsClient` or `AuthorizationCodeClient`). Existing profiles created with 0.1.x do not have this field, which can cause errors when running `login`, `auth-code-login`, or `token`.

Run the migration command once after upgrading:

```bash
sumo-oauth migrate-profile
```

This walks every profile that has a `client_id` but is missing `oauth_client_type` and prompts you to classify it as `cc` (ClientCredentialsClient — used with `login`) or `ac` (AuthorizationCodeClient — used with `auth-code-login`). Profiles with no `client_id` (basic-auth-only) are skipped automatically.

## Requirements

- Python 3.9+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

```bash
cd apis/scripts/oauth

# Install with uv (creates a local .venv automatically)
uv sync

# Optional: load credentials from a .env file
uv sync --extra dotenv

# Run directly
uv run sumo_oauth.py --help

# Or install as a named CLI tool
uv pip install -e .
sumo-oauth --help
```

## Authentication

Two credential types are used depending on the operation:

| Credential | Used for | Resolution order |
| --- | --- | --- |
| `client_id` / `client_secret` | `login`, `token` (OAuth token exchange) | CLI flag → profile → env var |
| `access_id` / `access_key` | All admin API commands (Basic auth) | CLI flag → profile → env var |

Secrets (`client_secret`, `access_key`) are stored in the OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service). They are never written to disk.

## Quick Start

### 1. Configure a profile

`store-creds` is interactive. Use `--mode` to configure only what you need:

| Mode | Prompts for |
| --- | --- |
| `all` (default) | region, OAuth client creds, Basic auth creds |
| `oauth` | region, `client_id`, `client_secret`, `oauth_client_type` |
| `basic` | region, `access_id`, `access_key` |

```bash
# OAuth client only (for login / auth-code-login)
sumo-oauth store-creds --mode oauth --region au --client-id <CID>
# Prompts for client_secret (masked) and oauth_client_type (cc or ac)

# Basic auth only (for admin API commands)
sumo-oauth store-creds --mode basic --region au --access-id <AID>
# Prompts for access_key (masked)

# Full setup — both credential types at once
sumo-oauth store-creds --region au --client-id <CID> --access-id <AID>

# Skip the type prompt by passing it directly
sumo-oauth store-creds --mode oauth --client-type client-credentials --region au --client-id <CID>
sumo-oauth store-creds --mode oauth --client-type authorization-code  --region au --client-id <CID>

# Named profile (CLI flags pre-fill prompts; env vars are NOT used, avoiding cross-account bleed)
sumo-oauth store-creds --profile prod --mode oauth --region us1 --client-id <CID>
```

### 2. Obtain an OAuth token

The login command to use depends on the OAuth client type:

```bash
# ClientCredentialsClient (machine-to-machine)
sumo-oauth login

# AuthorizationCodeClient (browser login — see experimental section below)
sumo-oauth auth-code-login
```

### 3. List resources

```bash
sumo-oauth users
sumo-oauth service-accounts
sumo-oauth oauth-clients
sumo-oauth oauth-scopes
```

## Regions

| Key | Endpoint |
| --- | --- |
| `us1` | `https://api.sumologic.com` |
| `us2` | `https://api.us2.sumologic.com` |
| `eu` | `https://api.eu.sumologic.com` |
| `au` | `https://api.au.sumologic.com` |
| `de` | `https://api.de.sumologic.com` |
| `jp` | `https://api.jp.sumologic.com` |
| `ca` | `https://api.ca.sumologic.com` |
| `in` | `https://api.in.sumologic.com` |

A full base URL can be passed instead of a region key via `--endpoint`.

## Commands

### Profile management

`store-creds` is interactive. Use `--mode` to configure only what you need. Press Enter at any prompt to keep the current value.

```bash
# OAuth client credentials only (ClientCredentialsClient)
sumo-oauth store-creds --mode oauth --region au --client-id <CID> --client-type client-credentials

# OAuth client credentials only (AuthorizationCodeClient)
sumo-oauth store-creds --mode oauth --region au --client-id <CID> --client-type authorization-code

# Basic auth only (admin API commands)
sumo-oauth store-creds --mode basic --region au --access-id <AID>

# Both credential types at once (default mode)
sumo-oauth store-creds --region au --client-id <CID> --access-id <AID>

# Update the client type on an existing profile (without re-entering secrets)
sumo-oauth store-creds --mode oauth --client-type authorization-code
# → press Enter for client_id and client_secret to keep them unchanged

# Named profile — CLI flags pre-fill prompts; env vars are NOT read here
# so named profiles stay isolated from the active account's credentials
sumo-oauth store-creds --profile prod --mode oauth --region us1 --client-id <CID>

# List all configured profiles (Type column shows cc/ac/-)
sumo-oauth list-profiles [--output {table,json}]

# Show status for a profile (includes token validity, expiry, oauth_client_type, keychain state)
sumo-oauth status [--profile NAME]
sumo-oauth status --all

# Remove keychain secrets for a profile (keeps profile config)
sumo-oauth clear-creds [--profile NAME]

# Remove a profile entirely (config + keychain secrets)
sumo-oauth delete-profile --profile NAME

# Migrate all profiles to the current format (prompts for any missing fields)
# Run once after upgrading from 0.1.x — classifies each profile as cc or ac
sumo-oauth migrate-profile
```

### OAuth token commands

Token exchange uses HTTP Basic auth against the regional `service.*` host, not `api.*`.

```bash
# Exchange client credentials for a Bearer token (stored in session file)
sumo-oauth login [--profile NAME]

# Request specific OAuth scopes (space- or comma-separated)
sumo-oauth login --scopes "runLogSearch viewCollectors"

# Override the token endpoint URL (advanced; normally derived from region automatically)
sumo-oauth login --token-url https://service.au.sumologic.com/oauth2/token

# Show the current token (auto-refreshes if expired)
sumo-oauth token [--profile NAME]

# Print only the raw 'Bearer <token>' string (for scripting)
sumo-oauth token --raw

# Clear the stored token (profile config kept)
sumo-oauth logout [--profile NAME]
```

### Authorization Code flow (experimental)

> **Experimental.** The authorization endpoint URL (`service.<region>.sumologic.com/oauth2/authorize`) is inferred from the token endpoint and has not been validated against a live Sumo Logic deployment. Behaviour may differ from what is documented here. Please open an issue if you encounter problems.

`auth-code-login` implements the OAuth 2.0 Authorization Code grant with PKCE (RFC 6749 §4.1 / RFC 7636). Unlike `login` (which uses `client_credentials` and runs as a service account), this flow authenticates as a real user via the browser. The resulting token is scoped to that user's roles intersected with the OAuth client's declared scopes.

**Before running**, register the redirect URI on the OAuth client in Sumo Logic (Administration → Security → OAuth Clients):

```text
http://localhost:8765/callback
```

Use a different port if 8765 is taken — just pass `--port` and update the registered URI to match.

```bash
# Opens browser, waits for callback on localhost:8765, exchanges code for tokens
sumo-oauth auth-code-login [--profile NAME]

# Use a different callback port (must match the redirect URI registered on the OAuth client)
sumo-oauth auth-code-login --port 9000

# Override both endpoints if auto-derivation doesn't work for your deployment
sumo-oauth auth-code-login \
  --auth-url  https://service.au.sumologic.com/oauth2/authorize \
  --token-url https://service.au.sumologic.com/oauth2/token
```

**Scopes** are not passed in the authorization request — Sumo Logic returns `invalid_scope` if you do. Effective scopes are determined by what is configured on the OAuth client in the Sumo Logic UI. The `--scopes` flag exists for deployments that may support it but should be omitted for standard Sumo Logic accounts.

If the server returns a refresh token it is stored in the OS keychain under `{profile}:refresh_token`. Subsequent `token`, `export-env`, and `login`-style auto-refreshes will use the refresh token grant automatically, falling back to `client_credentials` only if the refresh token is absent or rejected.

### MCP client configuration

Prints a ready-to-use configuration block (or CLI command) for registering the Sumo Logic MCP server in a supported AI client or IDE. Values are read from the active profile.

```bash
# Claude Code CLI command (default)
sumo-oauth client-config [--profile NAME]

# Specific format
sumo-oauth client-config --format vscode
sumo-oauth client-config --format cursor

# All formats at once
sumo-oauth client-config --format all

# Custom server name and callback port
sumo-oauth client-config --server-name my-sumo --callback-port 9000
```

Supported formats:

| Format | Config location | Auth approach |
| --- | --- | --- |
| `claude-code` | CLI command | OAuth authorization code + fixed callback port |
| `claude-code-json` | `.mcp.json` / `~/.claude.json` | OAuth authorization code + fixed callback port |
| `vscode` | `.vscode/mcp.json` | `clientId`/`clientSecret` inline (no fixed callback port) |
| `cursor` | `~/.cursor/mcp.json` | Bearer token (OAuth callback not supported) |
| `windsurf` | `~/.codeium/windsurf/mcp_config.json` | Bearer token (OAuth callback not supported) |
| `gemini` | `~/.gemini/settings.json` | OAuth `dynamic_discovery` + `redirectUri` |
| `codex` | `~/.codex/config.toml` | OAuth callback port (OpenAI Codex CLI) |
| `all` | — | All of the above |

For formats that use bearer tokens (`cursor`, `windsurf`), the command automatically uses the current stored access token. Tokens expire — re-run `client-config` to get a fresh one.

For formats that store `clientSecret` inline (`vscode`, `gemini`), **do not commit the config file to source control**.

---

### Export environment variables (MCP setup)

Prints shell `export` statements for all variables required by the Sumo Logic MCP server. Retrieves the `client_secret` from the OS keychain and auto-refreshes the token if needed.

```bash
sumo-oauth export-env [--profile NAME]
```

Output:

```bash
export SUMOLOGIC_MCP_URL="https://mcp.sumologic.com/mcp"
export SUMOLOGIC_OAUTH_CLIENT_ID="<client_id>"
export SUMOLOGIC_OAUTH_CLIENT_SECRET="<client_secret>"
export SUMOLOGIC_OAUTH_TOKEN_URL="https://service.sumologic.com/oauth2/token"
export SUMOLOGIC_OAUTH_ACCESS_TOKEN="<access_token>"
```

Pipe directly to your shell to apply:

```bash
eval "$(sumo-oauth export-env)"
```

### Users and service accounts

```bash
# List users
sumo-oauth users [--profile NAME] [--filter REGEX] [--output {table,json}] [--limit N]

# Filter by email (case-insensitive regex)
sumo-oauth users --filter "@example.com"

# Resolve role IDs to names (fetches /api/v2/roles and maps IDs in the Role IDs column)
sumo-oauth users --resolve-roles
sumo-oauth users --resolve-roles --filter "@example.com"

# List service accounts
sumo-oauth service-accounts [--profile NAME] [--filter REGEX] [--output {table,json}] [--limit N]
```

### Access keys

```bash
# List all access keys
sumo-oauth access-keys [--profile NAME] [--output {table,json}] [--limit N]

# Filter across all fields (id, label, createdBy, serviceAccountId) — default
sumo-oauth access-keys --filter "mcp"

# Filter by a specific field
sumo-oauth access-keys --filter "0000000000C49221" --filter-field serviceAccountId
sumo-oauth access-keys --filter "0000000000C40E60" --filter-field createdBy
sumo-oauth access-keys --filter "prod" --filter-field label
```

Table columns: `id`, `label`, `disabled`, `serviceAccountId`, `createdAt`, `lastUsed`, `expiresOn`, `scopes`, `effectiveScopes`.
Scopes are displayed as `(all)` when the array is empty (meaning no scope restriction), or as a preview with a count for large lists.
Use `--output json` to see the full `scopes`, `effectiveScopes`, and `corsHeaders` arrays.

### OAuth clients

```bash
# List all OAuth clients
sumo-oauth oauth-clients [--profile NAME] [--filter REGEX] [--output {table,json}] [--limit N]
```

Table columns: `clientId`, `name`, `type`, `disabled`, `scopes`, `runAsId`, `createdAt`.
Scopes show `(all)` when empty; large scope lists are shown as a preview with overflow count.

```bash
# Get a specific OAuth client by ID
sumo-oauth get-oauth-client --id <CLIENT_ID> [--profile NAME] [--output {table,json}]

# ---------------------------------------------------------------------------
# Creating a ClientCredentialsClient (machine-to-machine, runs as a service account)
# ---------------------------------------------------------------------------

# Inline flags — --run-as-id is required (use 'sumo-oauth service-accounts' to find it)
sumo-oauth create-oauth-client \
  --type client-credentials \
  --name "My MCP Client" \
  --run-as-id 0000000000A123456 \
  --scopes "runLogSearch,viewCollectors" \
  [--description "Optional description"] \
  [--save-creds] \
  [--profile NAME]

# From a JSON file (posted as-is — useful for runAs, full scopes lists, etc.)
sumo-oauth create-oauth-client --from-file oauth-client-example.json [--profile NAME]

# Add --save-creds to automatically persist the returned clientId/clientSecret to the profile
# (clientSecret is only returned at creation time — --save-creds ensures you don't lose it)
sumo-oauth create-oauth-client --from-file oauth-client-example.json --save-creds
# Then immediately log in with the new client:
sumo-oauth login

# ---------------------------------------------------------------------------
# Creating an AuthorizationCodeClient (browser-based user login)
# ---------------------------------------------------------------------------

# --redirect-uris is required; must match the URI used by auth-code-login (default port 8765)
sumo-oauth create-oauth-client \
  --type authorization-code \
  --name "My Browser App" \
  --redirect-uris "http://localhost:8765/callback" \
  [--scopes "runLogSearch,viewCollectors"] \
  [--description "Optional description"] \
  [--save-creds] \
  [--profile NAME]

# Multiple redirect URIs (comma-separated)
sumo-oauth create-oauth-client \
  --type authorization-code \
  --name "My Browser App" \
  --redirect-uris "http://localhost:8765/callback,https://myapp.example.com/callback"

# Update an OAuth client by ID
sumo-oauth update-oauth-client --id <CLIENT_ID> --from-file updated-client.json [--profile NAME]
# Or inline:
sumo-oauth update-oauth-client --id <CLIENT_ID> --name "New Name" --scopes "scope1,scope2"

# Delete an OAuth client
sumo-oauth delete-oauth-client --id <CLIENT_ID> [--profile NAME]
```

### OAuth scopes

```bash
# List all available OAuth scopes
sumo-oauth oauth-scopes [--profile NAME] [--filter REGEX] [--filter-field {id,label,both}] [--output {table,json}]

# Find scopes related to search
sumo-oauth oauth-scopes --filter search
sumo-oauth oauth-scopes --filter "^runLog" --filter-field id
```

Table columns: `id`, `label`, `type`, `group`.

### Roles

```bash
# List all roles (v2 API)
sumo-oauth roles [--profile NAME] [--output {table,json}] [--limit N]

# Filter by name or ID (default: both)
sumo-oauth roles --filter "admin"
sumo-oauth roles --filter "0000000000001234" --filter-field id
sumo-oauth roles --filter "analyst" --filter-field name
```

Table columns: `id`, `name`, `description`, `systemDefined`, `capabilities`.
Capabilities show `(all)` when empty; large lists are shown as a preview with overflow count.
Use `--output json` to see full `capabilities`, `users`, and filter predicate fields.

### OAuth consents

```bash
# List all OAuth consents (granted authorizations)
sumo-oauth oauth-consents [--profile NAME] [--output {table,json}] [--limit N]
```

Table columns: `id`, `clientId`, `userId`, `scopes`, `createdAt`, `expiresAt`.

## Multiple profiles

```bash
# Configure separate profiles for prod and staging
sumo-oauth store-creds --profile prod    --region us1 --client-id CID1 --access-id AID1
sumo-oauth store-creds --profile staging --region us2 --client-id CID2 --access-id AID2

# Use a named profile
sumo-oauth users --profile prod
sumo-oauth oauth-clients --profile staging

# Set a default profile via environment variable
export SUMO_PROFILE=prod
sumo-oauth users   # uses prod
```

## Environment variables

| Variable | Description |
| --- | --- |
| `SUMO_PROFILE` | Default profile name (overrides built-in default of `default`) |
| `SUMO_REGION` | Region fallback when not set in profile |
| `SUMO_CLIENT_ID` | OAuth client ID fallback |
| `SUMO_CLIENT_SECRET` | OAuth client secret fallback (prefer keychain) |
| `SUMO_ACCESS_ID` | Basic auth access ID fallback |
| `SUMO_ACCESS_KEY` | Basic auth access key fallback (prefer keychain) |

If `python-dotenv` is installed, a `.env` file in the current directory is loaded automatically. Copy [`.env.example`](.env.example) as a starting point:

```bash
cp .env.example .env
# Edit .env with your values
uv sync --extra dotenv
```

## Credential resolution order

For each credential, the resolution order is:

1. CLI flag (`--client-secret`, `--access-key`, etc.)
2. Active profile — non-sensitive values from `~/.sumo_oauth_session.json`; secrets from OS keychain
3. Environment variable (`SUMO_CLIENT_SECRET`, `SUMO_ACCESS_KEY`, etc.)
4. Error

## Security notes

- `~/.sumo_oauth_session.json` is created with `chmod 600` and stores only non-sensitive data: endpoint, client_id, access_id, oauth_client_type, access_token, expiry. It is safe to inspect.
- `client_secret`, `access_key`, and `refresh_token` are stored exclusively in the OS keychain, keyed per profile as `{profile}:client_secret`, `{profile}:access_key`, and `{profile}:refresh_token`.
- Access tokens are short-lived and auto-refreshed from the keychain when they expire.
- Never commit `.env` to git — it is listed in `.gitignore`.

## Output formats

All list commands support `--output table` (default) and `--output json`. Use `--output json` to pipe results to `jq`:

```bash
sumo-oauth oauth-clients --output json | jq '.[].clientId'
sumo-oauth users --output json | jq '.[] | select(.isActive == true) | .email'
```

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Fetch sanitized mock API responses for unit tests (requires a configured profile)
uv run fetch_mock_data.py [--profile NAME] [--output-dir mock_data/]

# Run tests
uv run pytest

# Run tests with verbose output
uv run pytest -v
```

`fetch_mock_data.py` fetches one example response item per endpoint, replaces real IDs, emails, and secrets with deterministic dummy values, and writes the results to `mock_data/` as JSON files. The test suite (`test_sumo_oauth.py`) validates all core functions including table formatting, sanitization, session management, and API helpers.
