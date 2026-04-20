# Sumo Logic MCP Server Setup with sumo-oauth

This guide walks through configuring the Sumo Logic MCP server using the `sumo-oauth` CLI. It covers Steps 1–3 of the [official setup docs](https://www.sumologic.com/help/docs/api/mcp-server/). For IDE configuration (Claude Code, VS Code + GitHub Copilot) refer to that page directly.

## Prerequisites

- Sumo Logic Administrator role
- `sumo-oauth` installed — see [README.md](README.md) for installation steps
- A service account already created in your Sumo Logic org
- MCP-compatible client (Claude Code CLI or VS Code + GitHub Copilot)

## Understanding credential types

`sumo-oauth` uses two separate credential types depending on the operation:

| Credential type | What it's for | Commands that use it |
| --- | --- | --- |
| **Access ID + Access Key** (Basic auth) | Admin API operations — listing users, service accounts, OAuth clients and scopes | `service-accounts`, `users`, `oauth-clients`, `oauth-scopes`, `create-oauth-client`, `delete-oauth-client` |
| **Client ID + Client Secret** (OAuth) | Obtaining a Bearer token for the MCP server | `login`, `token` |

For this setup you will need both. The steps below walk through configuring them in order.

## Step 1: Configure your profile

A profile stores your region and credentials so you don't have to pass them on every command. Secrets are stored in the OS keychain — never on disk.

### 1a. Set up Basic auth credentials

Basic auth (access ID + access key) is required for the admin API commands used in Steps 1 and 2. You can generate an access key in the Sumo Logic UI under **Preferences → Access Keys**.

```bash
sumo-oauth store-creds --region <REGION> --access-id <YOUR_ACCESS_ID>
```

Replace `<REGION>` with your deployment (e.g. `au`, `us1`, `us2`, `eu`). You will be prompted for:

```
Configuring profile 'default' – press Enter to keep the current value.

  region or endpoint URL [current: not set]: au        ← pre-filled from --region
  client_id     [current: not set]:                    ← press Enter to skip for now
  client_secret [enter value]:                         ← press Enter to skip for now
  access_id     [current: not set]: su0ABC...          ← pre-filled from --access-id
  access_key    [enter value]: ****                    ← enter your access key securely
```

Verify the profile was saved:

```bash
sumo-oauth status
```

At this point `access_key_stored` should be `true`. `client_secret_stored` will be `false` — that is expected; the OAuth client does not exist yet.

### 1b. OAuth client credentials (added in Step 3)

You do not need a client ID or secret yet. After creating the OAuth client in Step 2, `store-creds` will be re-run automatically via `--save-creds` to add those credentials to the same profile.

---

## Step 2: Find your service account ID

The OAuth client will run as a service account. You need its ID (`runAsId`) for the client config.

```bash
sumo-oauth service-accounts
```

Example output:

```
ID                   | Name              | Email                        | Active | Created
---------------------+-------------------+------------------------------+--------+----------
0000000000A123456    | mcp-service-acct  | mcp-svc@example.com          | True   | 2026-01-15
```

Use `--filter` to narrow results if you have many accounts:

```bash
sumo-oauth service-accounts --filter "mcp"
```

Note the **ID** value — you will use it as `runAsId` in the next step.

## Step 3: Create the OAuth client

### 3a. Review available scopes

List all available OAuth scopes to select what the MCP client should be permitted to do:

```bash
sumo-oauth oauth-scopes
```

Filter by keyword to find relevant scopes:

```bash
sumo-oauth oauth-scopes --filter "log|search|alert|dashboard|insight"
```

The MCP server typically requires scopes covering log search, alerts, dashboards, and Cloud SIEM. Scopes are limited to the intersection of the service account's roles and the OAuth client's declared scopes, so there is no privilege escalation risk in requesting broadly.

### 3b. Create a client config file

Create a JSON file describing the OAuth client. Replace the `runAsId` with the service account ID from Step 2, and adjust `scopes` to match your requirements.

```json
{
    "type": "ClientCredentialsClient",
    "name": "Sumo Logic MCP Client",
    "description": "OAuth client for MCP server access",
    "scopes": [
        "runLogSearch",
        "viewCollectors",
        "viewPartitions",
        "viewScheduledViews",
        "viewFields",
        "viewFieldExtractionRules",
        "viewMonitorsV2",
        "manageSlos",
        "viewSlos",
        "managePartitions",
        "manageScheduledViews",
        "manageFields",
        "manageFieldExtractionRules",
        "manageCollectors",
        "runMetricsQuery",
        "viewLibrary",
        "manageS3DataForwarding"
    ],
    "runAs": {
        "type": "ServiceAccount",
        "runAsId": "0000000000A123456"
    }
}
```

Save this as `mcp-client.json`.

### 3c. Create the client and save credentials

```bash
sumo-oauth create-oauth-client --from-file mcp-client.json --save-creds
```

The `--save-creds` flag automatically saves the returned `clientId` to your profile and stores the `clientSecret` in the OS keychain. The secret is only returned at creation time — `--save-creds` ensures you don't lose it.

Example output:

```
OAuth client created.
  clientId                : ICIEWKrJok-7H6ctnIlKCGtcrzy_cBEjeJPFnGkiAiM
  name                    : Sumo Logic MCP Client
  ...

Credentials saved to profile 'default':
  client_id     : ICIEWKrJok-7H6ctnIlKCGtcrzy_cBEjeJPFnGkiAiM
  client_secret : stored in OS keychain
Run 'sumo-oauth login' to obtain a token with the new client.
```

To verify the client was created:

```bash
sumo-oauth oauth-clients --filter "MCP"
```

## Step 4: Generate an access token

### Obtain and store a token

```bash
sumo-oauth login
```

This exchanges the client credentials for a Bearer token (valid 30 minutes) and stores it in your session profile for automatic refresh.

### Get the raw token for MCP configuration

```bash
sumo-oauth token --raw
```

This prints the full `Bearer <token>` string. Copy the token value (without the `Bearer ` prefix) for use in your MCP client configuration.

To automate token retrieval in scripts:

```bash
# Token only (strip "Bearer " prefix)
TOKEN=$(sumo-oauth token --raw | sed 's/Bearer //')

# Or export directly
export SUMOLOGIC_OAUTH_ACCESS_TOKEN=$(sumo-oauth token --raw | sed 's/Bearer //')
```

Tokens expire after 30 minutes. Re-run `sumo-oauth login` to refresh, or `sumo-oauth token --raw` which auto-refreshes if the stored token is expiring.

---

## Next: Configure your MCP client

With your `clientId`, `clientSecret`, and access token in hand, continue with the IDE configuration steps in the official docs:

**[https://www.sumologic.com/help/docs/api/mcp-server/](https://www.sumologic.com/help/docs/api/mcp-server/)**

The key values you will need:

| Value | How to get it |
| --- | --- |
| `SUMOLOGIC_OAUTH_CLIENT_ID` | From `sumo-oauth status` → `client_id` field |
| `SUMOLOGIC_OAUTH_CLIENT_SECRET` | Shown at creation time; stored in keychain |
| `SUMOLOGIC_OAUTH_ACCESS_TOKEN` | `sumo-oauth token --raw \| sed 's/Bearer //'` |
| `SUMOLOGIC_OAUTH_TOKEN_URL` | `https://service.<region>.sumologic.com/oauth2/token` |
| `SUMOLOGIC_MCP_URL` | `https://mcp.sumologic.com/mcp` |

The token URL for common regions:

| Region | Token URL |
| --- | --- |
| us1 | `https://service.sumologic.com/oauth2/token` |
| us2 | `https://service.us2.sumologic.com/oauth2/token` |
| au | `https://service.au.sumologic.com/oauth2/token` |
| eu | `https://service.eu.sumologic.com/oauth2/token` |
| de | `https://service.de.sumologic.com/oauth2/token` |
| jp | `https://service.jp.sumologic.com/oauth2/token` |
| ca | `https://service.ca.sumologic.com/oauth2/token` |
| in | `https://service.in.sumologic.com/oauth2/token` |
