# shortcode

Resolve a Sumo Logic log search **shortcode** (the code the UI's Share dialog gives you) into the search it stands for, as JSON: the query, the time range, the parsing mode and the UI display settings.

There's no documented public API for this. The UI calls an undocumented endpoint when you paste a code into a search window:

```
GET /api/v1/logSearches/shortCode/{code}
```

That endpoint accepts either:

- **Access ID/key** (Basic auth) on the deployment's API host, e.g. `api.us2.sumologic.com`
- **Browser session** (`ApiSession` + `Cookie`) on the UI host

`shortcode.py` is a standalone script with the same auth, region and instance behaviour as `mobot_client.py` in the project root.

## Requirements

- Python 3 and `requests`
- Credentials, set up the same way as for Skippie:
  - `skippie_instances.json` in the project root for named instances, and/or
  - access ID/key environment variables (default `SUMO_ACCESS_ID_CU` / `SUMO_ACCESS_KEY_CU`, or whichever variables the instance names), and/or
  - `local_config.py` in the project root for session auth

## Shortcode formats

The UI hands out a code in two forms. The script accepts both, as well as the bare code:

| Form | Example |
|---|---|
| Paste-into-search | `_code=AbCdEf0123456789AbCdEf0123456789AbCdEf01` |
| Share link | `https://<your-instance>.sumologic.com/log-search/create?id=AbCdEf0123456789AbCdEf0123456789AbCdEf01` |
| Bare code | `AbCdEf0123456789AbCdEf0123456789AbCdEf01` |

Put URLs in quotes so the shell leaves `?` and `&` alone.

The script only takes the code from the share link. It doesn't use the URL's host to choose where to send the request. A UI host, especially a custom-named subdomain, doesn't map reliably to an API host, so the request goes to the deployment chosen by `--instance` / `--auth` / `--region`.

## Usage

```bash
# default instance from skippie_instances.json
python3 shortcode/shortcode.py CODE

# either UI form works
python3 shortcode/shortcode.py "_code=CODE"
python3 shortcode/shortcode.py "https://<your-instance>.sumologic.com/log-search/create?id=CODE"

# a named instance (its region, auth method and key env vars)
python3 shortcode/shortcode.py --instance demo CODE

# access ID/key against an explicit deployment
python3 shortcode/shortcode.py --auth accesskey --region us2 CODE

# browser session from local_config.py
python3 shortcode/shortcode.py --auth session CODE

# parse the nested properties JSON string into objects
python3 shortcode/shortcode.py --decode-properties CODE

# one line of JSON, e.g. to extract just the query
python3 shortcode/shortcode.py --compact CODE | jq -r .queryString
```

### Options

| Option | Meaning |
|---|---|
| `code` | The shortcode, in any of the forms above |
| `--instance NAME` | A named instance from `skippie_instances.json`. Without it, the file's `"default"` is used if set |
| `--auth session\|accesskey` | Overrides the instance's auth method |
| `--region REGION` | With `--auth accesskey`: `prod` (us1), `us2`, `dub` (eu), `fed`, `fra` (de), `kor` (kr), `mon` (ca), `syd` (au), `tky` (jp), `zrh` (ch), `esc`; any case. Overrides the instance's region |
| `--decode-properties` | Parse `properties` (and its `aggregateResultsSettings`) from JSON strings into objects |
| `--compact` | Print the JSON on one line instead of indented |

The access key API host is chosen in this order: `--region`, then the instance's region, then `SUMO_API_URL_CU`, then the region of `BASE_URL` in `local_config.py`.

## Output

```json
{
  "queryString": "_sourcecategory=\"syd/stream\" | count by _collector",
  "timeRange": {
    "type": "BeginBoundedTimeRange",
    "from": { "type": "EpochTimeRangeBoundary", "epochMillis": 1794167237776 },
    "to":   { "type": "EpochTimeRangeBoundary", "epochMillis": 1794168137776 }
  },
  "runByReceiptTime": false,
  "queryParameters": [],
  "intervalTimeType": "messageTime",
  "parsingMode": "AutoParse",
  "properties": "{\"logsQueryMode\":\"Advanced\", ...}"
}
```

- `timeRange` is the absolute window the search had when it was shared. It isn't a relative range like "last 15 minutes".
- `properties` holds UI display state (query mode, table or chart settings) as JSON inside a string. `--decode-properties` unpacks it.

The JSON goes to stdout. Errors go to stderr and the script exits with code 1.

## Notes

- **Codes are org-scoped.** A code only resolves in the org and deployment it was created in. Elsewhere you get HTTP 400 `Log search not found for shortCode`.
- **Read-only.** The script only resolves codes. The UI creates them through an internal endpoint (`POST /json/v2/searchquery/{searchId}/shortCode`), which is tied to a browser search session and isn't supported here.
- **Undocumented.** The endpoint isn't part of the public API, so it could change without notice.
