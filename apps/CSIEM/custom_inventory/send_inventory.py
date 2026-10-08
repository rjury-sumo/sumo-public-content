#!/usr/bin/env python3
"""Post mock Cloud SIEM custom inventory records to a Sumo Logic HTTP source.

Delivery uses the generic custom inventory webhook schema:
https://www.sumologic.com/help/docs/cse/administration/custom-inventory-sources/

--source may be any free-text label (generic/custom mock), or one of the
known native inventory sources from
https://www.sumologic.com/help/docs/cse/administration/inventory-sources-and-data/
(okta, azuread, crowdstrike, carbonblack, awsec2, cylance, googleworkspace,
qualys, rapid7, sailpoint, sentinelone, tenable, windowsad, armis) -- run
--list-sources to see each one's supported entity type(s). For those, the
mocked uniqueID/deviceUniqueId follow that source's real ID prefix/format
per that page's "Inventory Source Mappings" section, so the data looks like
what Sumo's actual connector for that source would produce.

Each (source, entity-type) pair keeps a local JSON pool file next to this
script (inventory_pool_<source>_<type>.json) so uniqueID/deviceUniqueId and
the rest of an entity's mocked attributes stay consistent across runs. Pools
grow on demand up to --pool-size (default 1000) unique entities.

Examples:
  SUMO_URL=https://.../receiver/v1/http/XXXX ./send_inventory.py --source okta --count 5
  ./send_inventory.py --source crowdstrike --count 3 --url https://... --dry-run
  ./send_inventory.py --source azuread --type computer --list
  ./send_inventory.py --list-sources
"""
import argparse
import hashlib
import json
import os
import random
import re
import string
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Margaret", "Anthony", "Sandra", "Mark", "Ashley", "Steven", "Emily",
    "Paul", "Donna", "Andrew", "Michelle", "Joshua", "Dorothy", "Kevin", "Priya",
    "Wei", "Mei", "Yuki", "Hiroshi", "Soo-jin", "Min-jun", "Aditya", "Ananya",
    "Fatima", "Ahmed", "Mohammed", "Amara", "Chidi", "Ngozi", "Kwame", "Amina",
    "Olumide", "Ravi", "Lakshmi", "Arjun", "Divya", "Jose", "Maria", "Carlos",
    "Sofia", "Luis", "Camila", "Diego", "Valentina", "Mateo", "Isabella", "Giulia",
    "Marco", "Luca", "Elena", "Dmitri", "Natasha", "Olga", "Sven", "Ingrid",
    "Nadia", "Youssef", "Layla", "Hassan", "Zainab", "Tran", "Linh", "Duc",
    "Hana", "Jin", "Seo-yeon",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas",
    "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White",
    "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young",
    "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Patel",
    "Kim", "Park", "Choi", "Wang", "Zhang", "Liu", "Chen", "Yang",
    "Huang", "Tanaka", "Suzuki", "Yamamoto", "Sato", "Singh", "Kumar", "Sharma",
    "Gupta", "Khan", "Ibrahim", "Okafor", "Okonkwo", "Adeyemi", "Mensah", "Diallo",
    "Traore", "Rossi", "Russo", "Ferrari", "Bianchi", "Muller", "Schmidt", "Fischer",
    "Weber", "Kowalski", "Nowak", "Petrov", "Ivanov", "Smirnov", "Dubois", "Bernard",
    "Moreau", "Tran", "Pham", "Vo", "Dang", "Bui",
]
MIDDLE_INITIALS = list("ABCDEFGHJKLMNPQRSTVW")
DEPARTMENTS = [
    "Engineering", "IT", "Sales", "Marketing", "Finance", "HR", "Legal",
    "Operations", "Support", "Product",
]
LOCATIONS = [
    ("NYC", "NYC-HQ"), ("SFO", "SF-Office"), ("AUS", "Austin-Office"),
    ("LON", "London-Office"), ("CHI", "Chicago-Office"), ("SEA", "Seattle-Office"),
    ("RMT", "Remote-US"), ("RMU", "Remote-EU"),
]
DEVICE_KINDS = ["LT", "DT", "WS"]
OS_CHOICES = [
    ("Windows", "11 23H2"), ("Windows", "10 22H2"), ("macOS", "14.5 Sonoma"),
    ("macOS", "15.1 Sequoia"), ("Ubuntu", "22.04 LTS"), ("Ubuntu", "24.04 LTS"),
]
AWSEC2_OS_CHOICES = [
    ("Amazon Linux", "2023"), ("Ubuntu", "22.04 LTS"),
    ("Windows Server", "2022"), ("Red Hat Enterprise Linux", "9.3"),
]

DEFAULT_POOL_SIZE = 1000
DEFAULT_FIELDS = "_siemdatatype=inventory,_siemForward=true"

# Native inventory sources from
# https://www.sumologic.com/help/docs/cse/administration/inventory-sources-and-data/
# Each profile's id formats/prefixes mirror that page's "Inventory Source Mappings"
# so uniqueID/deviceUniqueId look like what Sumo's real connector for that source
# would produce, even though delivery here goes through the generic custom
# inventory webhook (https://www.sumologic.com/help/docs/cse/administration/custom-inventory-sources/).
PROFILES = {
    "armis": {"display": "Armis", "types": ["computer"]},
    "carbonblack": {"display": "CarbonBlack", "types": ["computer"]},
    "crowdstrike": {"display": "CrowdStrike", "types": ["computer"]},
    "awsec2": {"display": "AWS EC2", "types": ["computer"]},
    "cylance": {"display": "Cylance", "types": ["computer"]},
    "googleworkspace": {"display": "Google Workspace", "types": ["user"]},
    "azuread": {"display": "Azure AD", "types": ["user", "computer"]},
    "okta": {"display": "Okta", "types": ["user"]},
    "qualys": {"display": "Qualys VMDR", "types": ["computer"]},
    "rapid7": {"display": "Rapid7", "types": ["computer"]},
    "sailpoint": {"display": "SailPoint", "types": ["user"]},
    "sentinelone": {"display": "SentinelOne", "types": ["computer"]},
    "tenable": {"display": "Tenable", "types": ["computer"]},
    "windowsad": {"display": "Windows AD", "types": ["user", "computer"]},
}
PROFILE_ALIASES = {
    "armis": "armis",
    "carbonblack": "carbonblack", "carbon_black": "carbonblack",
    "crowdstrike": "crowdstrike", "crowdstrikefdr": "crowdstrike", "crowdstrike_fdr": "crowdstrike",
    "awsec2": "awsec2", "aws": "awsec2", "aws_ec2": "awsec2", "ec2": "awsec2",
    "cylance": "cylance",
    "googleworkspace": "googleworkspace", "google_workspace": "googleworkspace",
    "gsuite": "googleworkspace", "gworkspace": "googleworkspace", "google": "googleworkspace",
    "azuread": "azuread", "azure_ad": "azuread", "azure": "azuread", "aad": "azuread",
    "okta": "okta",
    "qualys": "qualys", "qualysvmdr": "qualys", "qualys_vmdr": "qualys",
    "rapid7": "rapid7",
    "sailpoint": "sailpoint",
    "sentinelone": "sentinelone", "sentinel_one": "sentinelone", "s1": "sentinelone",
    "tenable": "tenable",
    "windowsad": "windowsad", "windows_ad": "windowsad", "activedirectory": "windowsad",
    "active_directory": "windowsad", "ad": "windowsad", "winad": "windowsad",
}
EMAIL_AS_USERNAME = {"googleworkspace", "azuread", "sailpoint", "okta"}


def resolve_profile_key(source: str) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", source.lower())
    return PROFILE_ALIASES.get(normalized)


def _hex(rng: random.Random, length: int) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(length))


def _guid(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128)))


def native_identity(profile_key: str, rng: random.Random, hostname: str = None) -> dict:
    if profile_key == "armis":
        nid = str(rng.randint(100000, 999999))
        return {"unique_id": f"armis-{nid}", "device_unique_id": nid}
    if profile_key == "carbonblack":
        nid = str(rng.randint(1000000, 9999999))
        return {"unique_id": f"carbonblack{nid}", "device_unique_id": nid}
    if profile_key == "crowdstrike":
        nid = _hex(rng, 32)
        return {"unique_id": f"crowdstrike-{nid}", "device_unique_id": nid}
    if profile_key == "awsec2":
        account_id = str(rng.randint(10 ** 11, 10 ** 12 - 1))
        instance_id = "i-" + _hex(rng, 17)
        return {
            "unique_id": f"{account_id}{instance_id}",
            "device_unique_id": instance_id,
            "account_id": account_id,
            "instance_id": instance_id,
        }
    if profile_key == "cylance":
        return {"unique_id": f"cylance{hostname}", "device_unique_id": _guid(rng)}
    if profile_key == "googleworkspace":
        nid = str(rng.randint(10 ** 20, 10 ** 21 - 1))
        return {"unique_id": f"google-workspace{nid}", "user_native_id": nid}
    if profile_key == "azuread":
        oid = _guid(rng)
        return {"unique_id": f"AzureAD{oid}", "device_unique_id": oid, "user_native_id": oid}
    if profile_key == "okta":
        chars = string.ascii_letters + string.digits
        nid = "00u" + "".join(rng.choice(chars) for _ in range(17))
        return {"unique_id": f"okta{nid}", "user_native_id": nid}
    if profile_key == "qualys":
        nid = str(rng.randint(10 ** 7, 10 ** 8 - 1))
        return {"unique_id": f"qualys-{nid}", "device_unique_id": _guid(rng)}
    if profile_key == "rapid7":
        nid = str(rng.randint(10 ** 7, 10 ** 8 - 1))
        return {"unique_id": f"rapid7-{nid}", "device_unique_id": nid}
    if profile_key == "sailpoint":
        nid = _hex(rng, 22)
        return {"unique_id": f"sailpoint{nid}", "user_native_id": nid}
    if profile_key == "sentinelone":
        nid = str(rng.randint(10 ** 17, 10 ** 18 - 1))
        return {"unique_id": f"sentinelOne-{nid}", "device_unique_id": _guid(rng)}
    if profile_key == "tenable":
        nid = str(rng.randint(10 ** 7, 10 ** 8 - 1))
        return {"unique_id": f"tenable{nid}", "device_unique_id": nid}
    if profile_key == "windowsad":
        object_sid = (
            f"S-1-5-21-{rng.randint(10 ** 8, 10 ** 9 - 1)}-{rng.randint(10 ** 8, 10 ** 9 - 1)}"
            f"-{rng.randint(10 ** 8, 10 ** 9 - 1)}-{rng.randint(1000, 9999)}"
        )
        return {
            "unique_id_computer": _guid(rng),
            "unique_id_user": object_sid,
            "device_unique_id": object_sid,
            "user_native_id": object_sid,
        }
    return {}


def sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def seeded_rng(source: str, entity_type: str, index: int) -> random.Random:
    digest = hashlib.sha256(f"{source}:{entity_type}:{index}".encode()).hexdigest()
    return random.Random(int(digest, 16))


def pool_path(source: str, entity_type: str) -> Path:
    return SCRIPT_DIR / f"inventory_pool_{sanitize(source)}_{sanitize(entity_type)}.json"


def load_pool(source: str, entity_type: str) -> list:
    path = pool_path(source, entity_type)
    if path.exists():
        return json.loads(path.read_text())
    return []


def save_pool(source: str, entity_type: str, pool: list) -> None:
    pool_path(source, entity_type).write_text(json.dumps(pool, indent=2))


def person_name(index: int) -> tuple:
    grid = len(FIRST_NAMES) * len(LAST_NAMES)
    first = FIRST_NAMES[index % len(FIRST_NAMES)]
    # Stride by a prime larger than any plausible LAST_NAMES length so
    # index*97 mod len(LAST_NAMES) is a full permutation: consecutive
    # indices get distinct last names instead of repeating the same one
    # for a whole first-names cycle (previously everyone was "Smith"
    # until 40+ records were generated).
    last = LAST_NAMES[(index * 97 + 11) % len(LAST_NAMES)]
    if index >= grid:
        last = f"{last}{index // grid + 1}"
    return first, last


def mock_mac(rng: random.Random) -> str:
    octets = [0x02] + [rng.randint(0, 255) for _ in range(5)]  # locally administered
    return ":".join(f"{o:02x}" for o in octets)


def mock_doc_ip(rng: random.Random) -> str:
    block = rng.choice(["192.0.2", "198.51.100", "203.0.113"])  # TEST-NET ranges, non-routable
    return f"{block}.{rng.randint(1, 254)}"


def mock_private_ip(rng: random.Random) -> str:
    return f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


def generate_user(source: str, index: int, domain: str) -> dict:
    rng = seeded_rng(source, "user", index)
    first, last = person_name(index)
    local = f"{first[0].lower()}{last.lower()}"
    email = f"{local}@{domain}"
    department = rng.choice(DEPARTMENTS)
    loc_code, _ = rng.choice(LOCATIONS)
    device_kind = rng.choice(DEVICE_KINDS)
    _, os_version = rng.choice(OS_CHOICES)

    profile_key = resolve_profile_key(source)
    native = native_identity(profile_key, rng)
    unique_id = native.get("unique_id_user") or native.get("unique_id") or str(uuid.uuid4())
    username = email if profile_key in EMAIL_AS_USERNAME else local
    user_id = native.get("user_native_id") or email

    return {
        "index": index,
        "uniqueID": unique_id,
        "givenName": first,
        "middleName": rng.choice(MIDDLE_INITIALS) if rng.random() < 0.3 else "",
        "lastName": last,
        "username": username,
        "userId": user_id,
        "emails": [email],
        "department": department,
        "groups": ["Domain Users", f"{department}-Team"],
        "assignedHostname": f"{loc_code}-{device_kind}-{index:04d}",
        "assignedIp": mock_private_ip(rng),
        "assignedOsVersion": os_version,
        "assignedMac": mock_mac(rng),
    }


def generate_computer(source: str, index: int) -> dict:
    rng = seeded_rng(source, "computer", index)
    profile_key = resolve_profile_key(source)
    loc_code, location = rng.choice(LOCATIONS)
    device_kind = rng.choice(DEVICE_KINDS)
    os_choices = AWSEC2_OS_CHOICES if profile_key == "awsec2" else OS_CHOICES
    os_name, os_version = rng.choice(os_choices)
    hostname = f"{loc_code}-{device_kind}-{index:04d}"
    ip = mock_private_ip(rng)

    if profile_key == "awsec2":
        native = native_identity(profile_key, rng)
        hostname = f"ip-{ip.replace('.', '-')}.ec2.internal"
        unique_id = native["unique_id"]
        device_unique_id = native["device_unique_id"]
    else:
        native = native_identity(profile_key, rng, hostname=hostname)
        unique_id = native.get("unique_id_computer") or native.get("unique_id") or str(uuid.uuid4())
        device_unique_id = native.get("device_unique_id") or str(uuid.uuid4())

    return {
        "index": index,
        "uniqueID": unique_id,
        "deviceUniqueId": device_unique_id,
        "hostname": hostname,
        "ip": ip,
        "natIp": mock_doc_ip(rng),
        "mac": mock_mac(rng),
        "os": os_name,
        "osVersion": os_version,
        "location": location,
        "groups": ["Workstations", f"{device_kind}-Devices"],
    }


def generate_custom(source: str, entity_type: str, index: int) -> dict:
    rng = seeded_rng(source, entity_type, index)
    return {
        "index": index,
        "uniqueID": str(uuid.uuid4()),
        "name": f"{sanitize(entity_type)}-{index:04d}",
        "status": rng.choice(["Active", "Inactive", "Pending"]),
    }


def ensure_pool(source: str, entity_type: str, min_size: int, pool_size: int, domain: str) -> list:
    pool = load_pool(source, entity_type)
    target = min(max(min_size, len(pool)), pool_size)
    while len(pool) < target:
        index = len(pool)
        if entity_type == "user":
            pool.append(generate_user(source, index, domain))
        elif entity_type == "computer":
            pool.append(generate_computer(source, index))
        else:
            pool.append(generate_custom(source, entity_type, index))
    if pool:
        save_pool(source, entity_type, pool)
    return pool


def build_user_payload(record: dict, source: str) -> dict:
    return {
        "userId": record["userId"],
        "username": record["username"],
        "givenName": record["givenName"],
        "middleName": record["middleName"],
        "lastName": record["lastName"],
        "emails": record["emails"],
        "department": record["department"],
        "groups": record["groups"],
        "uniqueID": record["uniqueID"],
        "hostname": record["assignedHostname"],
        "ip": record["assignedIp"],
        "osVersion": record["assignedOsVersion"],
        "mac": record["assignedMac"],
        "source": source,
        "customInventory": True,
        "type": "user",
    }


def build_computer_payload(record: dict, source: str) -> dict:
    return {
        "computername": record["hostname"],
        "hostname": record["hostname"],
        "normalizedComputerName": record["hostname"].lower(),
        "normalizedHostname": record["hostname"].lower(),
        "ip": record["ip"],
        "natIp": record["natIp"],
        "mac": record["mac"],
        "os": record["os"],
        "osVersion": record["osVersion"],
        "location": record["location"],
        "groups": record["groups"],
        "uniqueID": record["uniqueID"],
        "deviceUniqueId": record["deviceUniqueId"],
        "source": source,
        "customInventory": True,
        "type": "computer",
    }


def build_custom_payload(record: dict, source: str, entity_type: str) -> dict:
    return {
        "name": record["name"],
        "status": record["status"],
        "uniqueID": record["uniqueID"],
        "source": source,
        "customInventory": True,
        "type": entity_type,
    }


def build_payload(record: dict, source: str, entity_type: str) -> dict:
    if entity_type == "user":
        return build_user_payload(record, source)
    if entity_type == "computer":
        return build_computer_payload(record, source)
    return build_custom_payload(record, source, entity_type)


def send(url: str, category: str, fields: str, payload: dict) -> tuple:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "X-Sumo-Category": category,
            "X-Sumo-Fields": fields,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default="mocksource", help="Inventory source name. One of the known native sources (okta, azuread, crowdstrike, carbonblack, awsec2, cylance, googleworkspace, qualys, rapid7, sailpoint, sentinelone, tenable, windowsad, armis) gets source-accurate mock IDs; any other value is treated as a generic/custom source (default: mocksource)")
    parser.add_argument("--type", default=None, dest="entity_type", help="Entity type: 'user', 'computer', or a custom value. Defaults to the entity type(s) the known --source supports, else 'user'")
    parser.add_argument("--list-sources", action="store_true", help="Print known native inventory sources and their supported entity types, then exit")
    parser.add_argument("--count", type=int, default=1, help="Number of entity records to send (default: 1)")
    parser.add_argument("--pool-size", type=int, default=DEFAULT_POOL_SIZE, help=f"Max unique mocked entities to maintain per source/type (default: {DEFAULT_POOL_SIZE})")
    parser.add_argument("--select", choices=["random", "sequential"], default="random", help="How to pick entities from the pool each run (default: random)")
    parser.add_argument("--indices", help="Comma-separated explicit pool indices to send, overrides --count/--select")
    parser.add_argument("--seed", type=int, help="Seed for --select random, for reproducible selection across runs")
    parser.add_argument("--domain", default="acme.corp", help="Email domain used for mocked users (default: acme.corp)")
    parser.add_argument("--url", default=os.environ.get("SUMO_URL"), help="Sumo HTTP source URL (default: $SUMO_URL)")
    parser.add_argument("--category", help="Override X-Sumo-Category (default: cse/custom/inventory/<source>)")
    parser.add_argument("--fields", default=DEFAULT_FIELDS, help=f"Override X-Sumo-Fields (default: {DEFAULT_FIELDS})")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be sent, without making HTTP requests")
    parser.add_argument("--list", action="store_true", dest="list_pool", help="Print pool info and exit, without sending")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    if args.list_sources:
        for key in sorted(PROFILES):
            profile = PROFILES[key]
            print(f"{key:18} {profile['display']:20} types: {', '.join(profile['types'])}")
        return 0

    profile_key = resolve_profile_key(args.source)
    profile = PROFILES.get(profile_key)
    if args.entity_type is None:
        args.entity_type = profile["types"][0] if profile else "user"
    elif profile and args.entity_type not in profile["types"]:
        print(
            f"Error: source '{args.source}' ({profile['display']}) only supports type(s): "
            f"{', '.join(profile['types'])}",
            file=sys.stderr,
        )
        return 1
    source_display = profile["display"] if profile else args.source

    pool = load_pool(args.source, args.entity_type)

    if args.list_pool:
        print(f"Pool file: {pool_path(args.source, args.entity_type)}")
        print(f"Entities stored: {len(pool)}")
        for record in pool:
            print(json.dumps(record))
        return 0

    if args.indices:
        indices = [int(i) for i in args.indices.split(",")]
        needed = max(indices) + 1 if indices else 0
        pool = ensure_pool(args.source, args.entity_type, needed, max(args.pool_size, needed), args.domain)
    else:
        count = min(args.count, args.pool_size)
        pool = ensure_pool(args.source, args.entity_type, count, args.pool_size, args.domain)
        rng = random.Random(args.seed)
        if args.select == "random":
            indices = rng.sample(range(len(pool)), count) if count <= len(pool) else list(range(len(pool)))
        else:
            indices = list(range(count))

    category = args.category or f"cse/custom/inventory/{args.source}"

    if not args.dry_run and not args.url:
        print("Error: no Sumo URL set. Pass --url or set SUMO_URL.", file=sys.stderr)
        return 1

    for index in indices:
        if index >= len(pool):
            print(f"Skipping index {index}: not present in pool (size {len(pool)})", file=sys.stderr)
            continue
        record = pool[index]
        payload = build_payload(record, source_display, args.entity_type)

        if args.dry_run:
            print(f"--- index {index} (uniqueID={record['uniqueID']}) ---")
            print(f"X-Sumo-Category: {category}")
            print(f"X-Sumo-Fields: {args.fields}")
            print(json.dumps(payload))
            continue

        status, response_body = send(args.url, category, args.fields, payload)
        print(f"index={index} uniqueID={record['uniqueID']} status={status} response={response_body[:200]!r}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
