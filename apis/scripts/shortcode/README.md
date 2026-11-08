# shortcode

Resolves a Sumo Logic log search shortcode to the search it represents, printed as JSON.

## Requirements

Python 3 and `requests`.

## Usage

```bash
python3 shortcode.py CODE
python3 shortcode.py "_code=CODE"
python3 shortcode.py "https://<instance>.sumologic.com/log-search/create?id=CODE"
```

CODE can be given in any of these three forms. Quote URLs so the shell leaves `?` and `&` alone.

| Option | Meaning |
|---|---|
| `--region REGION` | Deployment to call: `prod` (us1, the default), `us2`, `dub` (eu), `fed`, `fra` (de), `kor` (kr), `mon` (ca), `syd` (au), `tky` (jp), `zrh` (ch), `esc` |
| `--instance NAME` | A named instance from `instances.json` |
| `--decode-properties` | Unpack the `properties` JSON string into objects |
| `--compact` | Print the JSON on one line |

## Auth

Access ID/key only. The script reads `SUMO_ACCESS_ID` / `SUMO_ACCESS_KEY`, or the variables an instance names. The API host comes from `--region`, then the instance, then `SUMO_API_URL`, then `prod` (`api.sumologic.com`).

**Instances (optional):** `instances.json` next to the script. Its `default` is used when `--instance` isn't given:

```json
{
  "default": "us2",
  "instances": {
    "us2": {"region": "us2",
            "access_id_env": "SUMO_ACCESS_ID", "access_key_env": "SUMO_ACCESS_KEY"}
  }
}
```

## Output

```json
{
  "queryString": "_sourcecategory=\"syd/stream\" | count by _collector",
  "timeRange": {"type": "BeginBoundedTimeRange", "from": {...}, "to": {...}},
  "runByReceiptTime": false,
  "queryParameters": [],
  "intervalTimeType": "messageTime",
  "parsingMode": "AutoParse",
  "properties": "{...}"
}
```

A shortcode only resolves in the org it was created in. The script exits 1 on errors.
