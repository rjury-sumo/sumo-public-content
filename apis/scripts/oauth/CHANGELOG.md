# Changelog

All notable changes to `sumo-oauth` are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.2.0] — 2026-05-18

### Added
- **`oauth_client_type` field on profiles** — distinguishes `ClientCredentialsClient` (use `login`) from `AuthorizationCodeClient` (use `auth-code-login`). Stored in the session file; displayed in `list-profiles` and `status`.
- **`auth-code-login` command** — OAuth 2.0 Authorization Code + PKCE flow (RFC 7636). Opens a browser, captures the local redirect, exchanges the code for tokens, and stores the refresh token in the OS keychain.
- **Automatic token refresh via refresh token** — `require_token` (used by `token`, `client-config`) now prefers the stored refresh token before falling back to `client_credentials` grant. Auth-code profiles without a refresh token exit with a clear re-login message.
- **`client-config` command** — prints ready-to-paste MCP server configuration for Claude Code, Claude Code JSON, VS Code, Cursor, Windsurf, Gemini CLI, and OpenAI Codex CLI. Supports `--format all` to print every format at once.
- **`oauth_client_type` prompt in `store-creds`** — interactive prompt for `cc` (client-credentials) or `ac` (authorization-code); skippable via `--client-type` flag.
- **`migrate-profile` command** — walks all existing profiles and interactively prompts for any fields required by the current version that are absent from older profiles (currently: `oauth_client_type`).
- **`--version` / `-V` flag** — prints the tool version and exits.
- **`store-creds --client-type` flag** — skips the interactive type prompt when provided (`client-credentials` or `authorization-code`).
- **Refresh token stored in OS keychain** — keyed as `{profile}:refresh_token`; never written to disk.
- **`access-keys` command** — lists access keys via `/api/v1/accessKeys` with `--filter` and `--filter-field` support.
- **`oauth-consents` command** — lists OAuth consents via `/api/v1/oauth/consents`.
- **`oauth-scopes` command** — lists available OAuth scopes via `/api/v1/oauth/scopes`.
- **`roles` command** — lists roles via `/api/v2/roles`.
- **`get-oauth-client` / `update-oauth-client` / `delete-oauth-client` commands** — CRUD operations on OAuth clients.
- **`users --resolve-roles` flag** — resolves role IDs to names using `/api/v2/roles`.
- **MCP URL derivation** — `export-env` and `client-config` auto-derive `SUMOLOGIC_MCP_URL` from the profile endpoint.

### Fixed
- **`export-env` no longer refreshes tokens** — the command now exports the stored token as-is. Run `sumo-oauth token` first if you need a fresh token before exporting.
- **Profile default consistency** — added a defensive guard in `main()` so `args.profile` always resolves to `SUMO_PROFILE` env var or `"default"`, regardless of argparse version behaviour with `SUPPRESS` defaults.
- **`store-creds` env-var bleed** — CLI flags pre-fill prompts; env vars (`SUMO_ACCESS_ID`, `SUMO_CLIENT_ID`, …) are explicitly excluded from pre-filling to prevent cross-account credential bleed into named profiles.
- **Auth-code client guard in `require_token`** — if an `AuthorizationCodeClient` profile has an expired token and no refresh token, the tool exits with a clear error instead of attempting the unsupported `client_credentials` grant.
- **`create-oauth-client --save-creds`** — correctly persists `oauth_client_type` returned by the API when saving credentials to the profile.

### Changed
- `list-profiles` table now shows a `Type` column (`cc` / `ac` / `-`).
- `status` JSON now includes `oauth_client_type`, `refresh_token_stored`, and `keychain_available` fields.
- Token refresh logic in `require_token` now prefers the refresh token grant over client credentials.

---

## [0.1.0] — initial release

- Multi-profile session management (`store-creds`, `list-profiles`, `delete-profile`, `clear-creds`, `status`).
- OAuth client-credentials flow (`login`, `token`, `logout`).
- Basic auth admin API commands: `users`, `service-accounts`, `oauth-clients`, `create-oauth-client`.
- `export-env` command for MCP environment variable setup.
- OS keychain storage for `client_secret` and `access_key` (never written to disk).
- Automatic legacy session file migration to multi-profile format.
