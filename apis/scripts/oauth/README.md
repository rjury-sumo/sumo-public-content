# sumo-oauth

A command-line utility for managing Sumo Logic OAuth clients, users, and service accounts.

Supports multiple named profiles so different Sumo Logic instances (regions, accounts) can be managed from one tool. Secrets are stored in the OS keychain — never on disk.

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

`store-creds` is interactive — all fields are optional and you can leave any blank to skip it. Run it multiple times to add credentials incrementally.

```bash
# Minimal setup for admin API commands only (Basic auth — no OAuth client needed)
sumo-oauth store-creds --region au --access-id <AID>
# Prompts for: region (pre-filled), client_id (skip), client_secret (skip), access_id (pre-filled), access_key

# Minimal setup for OAuth token commands only (no Basic auth needed)
sumo-oauth store-creds --region au --client-id <CID>
# Prompts for: region (pre-filled), client_id (pre-filled), client_secret, access_id (skip), access_key (skip)

# Full setup — all credentials at once
sumo-oauth store-creds --region au --client-id <CID> --access-id <AID>
# Prompts for all secrets securely via keychain

# Re-run to add or update individual values without affecting others
sumo-oauth store-creds  # shows current values; press Enter to keep any unchanged
```

Any values passed as CLI flags (`--region`, `--client-id`, `--access-id`) are pre-filled in the prompts. Secrets (`client_secret`, `access_key`) are always entered interactively via a masked prompt and stored in the OS keychain — never on disk.

### 2. Obtain an OAuth token

```bash
sumo-oauth login
# Logs in using the 'default' profile; token is stored in ~/.sumo_oauth_session.json
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

`store-creds` is interactive. All fields are optional — press Enter at any prompt to keep the existing value. Run it as many times as needed to build up a profile incrementally.

```bash
# First-time setup: region + Basic auth credentials only (for users/service-accounts/oauth-clients)
sumo-oauth store-creds --region au --access-id <AID>

# First-time setup: region + OAuth client credentials only (for login/token)
sumo-oauth store-creds --region au --client-id <CID>

# Add OAuth client credentials to a profile that already has Basic auth set up
sumo-oauth store-creds --client-id <CID>
# → press Enter to keep region/access_id unchanged; enter client_secret at the prompt

# Add Basic auth credentials to a profile that already has OAuth set up
sumo-oauth store-creds --access-id <AID>
# → press Enter to keep region/client_id/client_secret unchanged; enter access_key at the prompt

# Update a single secret (e.g. rotated access_key) without changing anything else
sumo-oauth store-creds
# → press Enter for every field except access_key

# Named profile
sumo-oauth store-creds --profile prod --region us1 --client-id <CID> --access-id <AID>

# List all configured profiles
sumo-oauth list-profiles [--output {table,json}]

# Show status for a profile (token validity, expiry, keychain state)
sumo-oauth status [--profile NAME]
sumo-oauth status --all

# Remove keychain secrets for a profile (keeps profile config)
sumo-oauth clear-creds [--profile NAME]

# Remove a profile entirely (config + keychain secrets)
sumo-oauth delete-profile --profile NAME
```

### OAuth token commands

```bash
# Exchange client credentials for a Bearer token (stored in session file)
sumo-oauth login [--profile NAME]

# Show the current token (auto-refreshes if expired)
sumo-oauth token [--profile NAME]

# Print only the raw 'Bearer <token>' string (for scripting)
sumo-oauth token --raw

# Clear the stored token (profile config kept)
sumo-oauth logout [--profile NAME]
```

### Users and service accounts

```bash
# List users
sumo-oauth users [--profile NAME] [--filter REGEX] [--output {table,json}] [--limit N]

# Filter by email (case-insensitive regex)
sumo-oauth users --filter "@example.com"

# List service accounts
sumo-oauth service-accounts [--profile NAME] [--filter REGEX] [--output {table,json}] [--limit N]
```

### OAuth clients

```bash
# List all OAuth clients
sumo-oauth oauth-clients [--profile NAME] [--filter REGEX] [--output {table,json}] [--limit N]

# Get a specific OAuth client by ID
sumo-oauth get-oauth-client --id <CLIENT_ID> [--profile NAME] [--output {table,json}]

# Create a new OAuth client from a JSON file (recommended for complex payloads)
# The JSON is posted as-is, so fields like type, runAs, scopes array etc. are all supported
sumo-oauth create-oauth-client --from-file oauth-client-example.json [--profile NAME]

# Add --save-creds to automatically save the returned clientId/clientSecret to the profile
# (clientSecret is only returned at creation time — this avoids losing it)
sumo-oauth create-oauth-client --from-file oauth-client-example.json --save-creds
# Then immediately log in with the new client:
sumo-oauth login

# Or create inline with individual flags
sumo-oauth create-oauth-client \
  --name "My App" \
  --redirect-uris "https://myapp.example.com/callback" \
  --scopes "scope_id_1,scope_id_2" \
  [--description "Optional description"] \
  [--save-creds] \
  [--profile NAME] \
  [--output {table,json}]

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
sumo-oauth oauth-scopes --filter "^search:" --filter-field id
```

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

- `~/.sumo_oauth_session.json` is created with `chmod 600` and stores only non-sensitive data (endpoint, client_id, access_id, access_token, expiry). It is safe to inspect.
- `client_secret` and `access_key` are stored exclusively in the OS keychain, keyed per profile as `{profile}:client_secret` and `{profile}:access_key`.
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

# Run tests
uv run pytest
```
