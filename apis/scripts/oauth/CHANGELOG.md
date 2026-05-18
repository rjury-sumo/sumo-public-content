# Changelog

All notable changes to `sumo-oauth` are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.2.2] — 2026-05-18

### Added

- **`list-profiles --filter`** — filter listed profiles by name or `oauth_client_type` using a case-insensitive regex (e.g. `--filter authorization` or `--filter stg`).
- **`oauth-consents` `clientName` column** — tabular output now includes the OAuth client display name; `--filter` matches on `clientName` in addition to `clientId` and `userId`.
- **`mcp-setup.md` browser login screenshots** — 3-column image table (login → consent → authorization complete) with CLI output example added to Workflow B Step 3.
- **`mcp-setup.md` UI verification screenshots** — OAuth Clients administration tab screenshot added after Workflow A Step 3; Personal Authorized Apps screenshot and `oauth-consents --filter` example added after Workflow B Step 3.
- **`mcp-setup.md` UI alternative callouts** — both Step 1s and both OAuth-client-creation steps now note that clients can be created/managed in the UI, with skip-ahead instructions including the correct `store-creds --mode oauth --client-type` command.
- **`mcp-setup.md` `client-config` type-aware example** — explains that output is tailored to the profile's OAuth client type; adds a sanitized `claude-code-json` example for `AuthorizationCodeClient`.
- **`mcp-setup.md` `clientName` notes** — both workflows note that `--name` / `"name"` becomes the `clientName` visible in `oauth-consents` output.

### Fixed

- **`update-oauth-client` full-replace correctness** — PUT is a full-replace operation; the command now fetches the existing client first and merges only the supplied fields, preventing accidental clearing of scopes, redirectUris, or runAs. `--name` is no longer required when only updating other fields.

---

## [0.2.1] — 2026-05-18

### Added

- **Integration test suite** (`test_integration.py`) — live read-only tests against the real Sumo Logic API. Covers CC token refresh (`login`, `token`, `export-env`) via the `default` profile, AC token refresh via `stg-code` (skipped gracefully if the refresh token is expired), and all Basic-auth GET commands (`users`, `service-accounts`, `oauth-clients`, `oauth-scopes`, `access-keys`, `roles`, `oauth-consents`, `list-profiles`). AC tests probe token validity in setup and skip with a clear re-authenticate message if needed.
- **Unit tests for `store-creds --client-type`** — `TestPromptClientType` (8 tests) and `TestStoreCreds` (8 tests) covering `_prompt_client_type` aliases, interactive prompt flow, `--client-type` flag bypassing the prompt, argparse choices validation, and help output.
- **`HTTP_TIMEOUT = (10, 30)`** — all HTTP requests now carry a 10s connect / 30s read timeout, preventing indefinite hangs on network issues.
- **`integration` pytest marker** registered in `pyproject.toml`.

### Fixed

- **`export-env` docs** corrected — previously said "auto-refreshes the token"; now accurately states it outputs the stored token as-is.
- **Auth-code refresh token expiry** documented in README — explains `invalid_grant` error and the `auth-code-login` re-authentication command.
- **`store-creds` README** — mode table now lists `oauth_client_type` for `all` mode; added cc/ac legend table at first use; `--client-type` flag described as "skip the interactive prompt".
- **Integration test subprocess hang** — `_run()` helper now passes `stdin=DEVNULL` and enforces a 45s `timeout`, failing with a clear message instead of blocking indefinitely.
- **Integration test pagination hang** — removed erroneous `--limit 1` args (`--limit` is page size, not a result cap); O(N) API calls per test reduced back to the default single page of 100.

---

## [0.2.0] — 2026-05-18

### Added

- **`oauth_client_type` field on profiles** — distinguishes `ClientCredentialsClient` (use `login`) from `AuthorizationCodeClient` (use `auth-code-login`). Stored in the session file; displayed in `list-profiles` and `status`.
- **`auth-code-login` command** — OAuth 2.0 Authorization Code + PKCE flow (RFC 7636). Opens a browser, captures the local redirect, exchanges the code for tokens, and stores the refresh token in the OS keychain.
- **Automatic token refresh via refresh token** — `require_token` now prefers the stored refresh token before falling back to `client_credentials` grant. Auth-code profiles without a refresh token exit with a clear re-login message.
- **`client-config` command** — prints ready-to-paste MCP server configuration for Claude Code, VS Code, Cursor, Windsurf, Gemini CLI, and OpenAI Codex CLI. Supports `--format all`.
- **`oauth_client_type` prompt in `store-creds`** — interactive prompt for `cc` or `ac`; skippable via `--client-type` flag.
- **`migrate-profile` command** — walks all existing profiles and interactively prompts for fields required by the current version but absent from older profiles (currently: `oauth_client_type`).
- **`--version` / `-V` flag** — prints the tool version and exits.
- **`store-creds --client-type` flag** — skips the interactive type prompt (`client-credentials` or `authorization-code`).
- **Refresh token stored in OS keychain** — keyed as `{profile}:refresh_token`; never written to disk.
- **`access-keys` command** — lists access keys via `/api/v1/accessKeys` with `--filter` / `--filter-field` support.
- **`oauth-consents` command** — lists OAuth consents via `/api/v1/oauth/consents`.
- **`oauth-scopes` command** — lists available OAuth scopes via `/api/v1/oauth/scopes`.
- **`roles` command** — lists roles via `/api/v2/roles`.
- **`get-oauth-client` / `update-oauth-client` / `delete-oauth-client` commands** — CRUD operations on OAuth clients.
- **`users --resolve-roles` flag** — resolves role IDs to names using `/api/v2/roles`.
- **MCP URL derivation** — `export-env` and `client-config` auto-derive `SUMOLOGIC_MCP_URL` from the profile endpoint.

### Fixed

- **`export-env` no longer refreshes tokens** — exports the stored token as-is; run `sumo-oauth token` first if you need a fresh one.
- **Profile default consistency** — defensive guard in `main()` ensures `args.profile` always resolves to `SUMO_PROFILE` env var or `"default"`.
- **`store-creds` env-var bleed** — env vars excluded from prompt pre-fill to prevent cross-account credential bleed into named profiles.
- **Auth-code client guard in `require_token`** — expired AC profile with no refresh token exits with a clear error instead of attempting the unsupported `client_credentials` grant.
- **`create-oauth-client --save-creds`** — correctly persists `oauth_client_type` returned by the API.

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
