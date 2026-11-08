#Resolves a Sumo Logic log search share shortcode (the code from the UI's Share dialog) to its search JSON:
#queryString, timeRange, parsingMode, properties and so on, via GET /api/v1/logSearches/shortCode/{code}.
#Authenticates with an access ID/key on the deployment's API host

import argparse
import base64
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

#instances.json is optional and lives next to this script
SCRIPT_DIR = Path(__file__).resolve().parent
INSTANCES_FILE = SCRIPT_DIR / "instances.json"
DEFAULT_ACCESS_ID_ENV = "SUMO_ACCESS_ID"
DEFAULT_ACCESS_KEY_ENV = "SUMO_ACCESS_KEY"
DEFAULT_REGION = "prod"

#Glass region names mapped to the public API host of each deployment
REGION_API_HOSTS = {
    "prod": "api.sumologic.com",
    "us2": "api.us2.sumologic.com",
    "dub": "api.eu.sumologic.com",
    "fed": "api.fed.sumologic.com",
    "fra": "api.de.sumologic.com",
    "kor": "api.kr.sumologic.com",
    "mon": "api.ca.sumologic.com",
    "syd": "api.au.sumologic.com",
    "tky": "api.jp.sumologic.com",
    "zrh": "api.ch.sumologic.com",
    "esc": "api.esc.sumologic.com",
}
REGION_ALIASES = {"us1": "prod", "au": "syd", "eu": "dub", "jp": "tky", "de": "fra", "ca": "mon", "kr": "kor", "ch": "zrh"}


def region_api_url(region: str) -> str:
    key = region.strip().lower()
    key = REGION_ALIASES.get(key, key)
    if key not in REGION_API_HOSTS:
        raise SystemExit(f"Unknown region '{region}'. Valid: {', '.join(REGION_API_HOSTS)} "
                         f"(aliases: {', '.join(f'{a}={r}' for a, r in REGION_ALIASES.items())}).")
    return f"https://{REGION_API_HOSTS[key]}"


def load_instances():
    if not INSTANCES_FILE.is_file():
        return None
    try:
        data = json.loads(INSTANCES_FILE.read_text())
    except ValueError as e:
        raise SystemExit(f"{INSTANCES_FILE} is not valid JSON: {e}")
    if not isinstance(data, dict) or not isinstance(data.get("instances"), dict):
        raise SystemExit(f'{INSTANCES_FILE} needs an "instances" object; see README.md')
    return data


#The --instance named, else the file's "default", else None (region and key env vars from flags and defaults)
def resolve_instance(name):
    data = load_instances()
    if name is None:
        if not data or not data.get("default"):
            return None
        name, source = data["default"], f'"default" in {INSTANCES_FILE.name}'
    else:
        if data is None:
            raise SystemExit(f"--instance {name}: {INSTANCES_FILE} not found; see README.md for its format.")
        source = "--instance"
    instances = data["instances"]
    match = next((k for k in instances if k.lower() == name.lower()), None)
    if match is None:
        raise SystemExit(f"Unknown instance '{name}' ({source}). Defined: {', '.join(instances) or 'none'}.")
    return dict(instances[match], name=match)


#API base URL and Basic auth headers from an access ID/key
def configure_auth(region: str = None,
                   access_id_env: str = DEFAULT_ACCESS_ID_ENV, access_key_env: str = DEFAULT_ACCESS_KEY_ENV):
    access_id = os.environ.get(access_id_env)
    access_key = os.environ.get(access_key_env)
    if not access_id or not access_key:
        raise SystemExit(f"Access key auth needs {access_id_env} and {access_key_env} set in the environment.")
    #--region (or the instance's region) wins, then an explicit SUMO_API_URL, then prod
    api_url = region_api_url(region) if region else os.environ.get("SUMO_API_URL") or region_api_url(DEFAULT_REGION)
    token = base64.b64encode(f"{access_id}:{access_key}".encode()).decode()
    return api_url.rstrip("/"), {"Accept": "application/json", "Authorization": f"Basic {token}"}


#The UI hands out a shortcode in two forms: "_code=XXXX" to paste into a search, or a
#.../log-search/create?id=XXXX link. Accept either, or the bare code
def extract_code(value: str) -> str:
    value = value.strip()
    if "://" in value:
        query = parse_qs(urlparse(value).query)
        code = (query.get("id") or query.get("_code") or [""])[0]
    else:
        m = re.search(r"(?:^|[?&\s])(?:_code|id)=(\S+)", value)
        code = m.group(1) if m else value
    code = code.strip().strip("&")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", code):
        raise SystemExit(f"Can't find a shortcode in {value!r}. Pass the code, _code=CODE, or a log-search URL with ?id=CODE.")
    return code


def resolve_shortcode(base_url: str, headers: dict, code: str) -> dict:
    try:
        resp = requests.get(f"{base_url}/api/v1/logSearches/shortCode/{code}", headers=headers, timeout=30)
    except requests.RequestException as e:
        raise SystemExit(f"Request to {base_url} failed: {e}")
    if resp.status_code != 200:
        raise SystemExit(f"Shortcode lookup failed: HTTP {resp.status_code} from {urlparse(base_url).hostname}: "
                         f"{resp.text[:500]}")
    try:
        return resp.json()
    except ValueError:
        raise SystemExit(f"Shortcode lookup returned non-JSON: {resp.text[:500]}")


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Resolve a Sumo Logic log search shortcode (from the UI's Share dialog) and print its search JSON.",
        epilog="""examples:
  python3 shortcode.py CODE
      access ID/key from SUMO_ACCESS_ID / SUMO_ACCESS_KEY against prod (api.sumologic.com)
  python3 shortcode.py "_code=CODE"
  python3 shortcode.py "https://service.us2.sumologic.com/log-search/create?id=CODE"
      the paste-into-search form and the share link work too
  python3 shortcode.py --region us2 CODE
      against api.us2.sumologic.com
  python3 shortcode.py --instance NAME CODE
      a named instance from instances.json (its region and key env vars)
  python3 shortcode.py CODE | jq -r .queryString
      just the query

A shortcode only resolves in the org (and deployment) it was created in.""",
    )
    parser.add_argument("code", help="The shortcode: the bare code, _code=CODE, or a log-search URL with ?id=CODE "
                                     "(quote URLs so the shell leaves & and ? alone)")
    parser.add_argument("--instance", metavar="NAME",
                        help=f"Use a named instance from {INSTANCES_FILE.name} (region, key env vars). "
                             "Default: the file's \"default\" instance if set")
    parser.add_argument("--region", metavar="REGION",
                        help="The deployment to call: prod (us1), us2, dub (eu), fed, fra (de), "
                             "kor (kr), mon (ca), syd (au), tky (jp), zrh (ch), esc; any case. Overrides the instance's region. Default: SUMO_API_URL if set, else prod")
    parser.add_argument("--decode-properties", action="store_true",
                        help="Parse the JSON-in-a-string properties field (and its aggregateResultsSettings) into objects")
    parser.add_argument("--compact", action="store_true", help="Print the JSON on one line instead of indented")
    return parser.parse_args()


def decode_properties(payload: dict) -> dict:
    props = payload.get("properties")
    if isinstance(props, str):
        try:
            props = json.loads(props)
        except ValueError:
            return payload
        for k, v in props.items():
            if isinstance(v, str) and v[:1] in "{[":
                try:
                    props[k] = json.loads(v)
                except ValueError:
                    pass
        payload["properties"] = props
    return payload


def main():
    args = parse_args()
    instance = resolve_instance(args.instance) or {}
    base_url, headers = configure_auth(args.region or instance.get("region"),
                                       instance.get("access_id_env", DEFAULT_ACCESS_ID_ENV),
                                       instance.get("access_key_env", DEFAULT_ACCESS_KEY_ENV))
    payload = resolve_shortcode(base_url, headers, extract_code(args.code))
    if args.decode_properties:
        payload = decode_properties(payload)
    print(json.dumps(payload, separators=(",", ":")) if args.compact else json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
