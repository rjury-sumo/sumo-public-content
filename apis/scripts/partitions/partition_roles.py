#!/usr/bin/env python3
"""
Sumo Logic Partition Role Manager

Finds partitions matching filter criteria and creates/updates scoped v2 roles
for each matched partition.

Modes:
  list      (default) — print matching partitions and report how many matching
                        roles already exist, without making any changes.
  execute             — create a role for each partition; if a role with the
                        generated name already exists, update it instead.
  terraform           — write terraform/partitions.tf with a sumologic_partition
                        resource block for every matched partition.
"""

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class SumoLogicClient:
    """Thin wrapper around the Sumo Logic REST API"""

    REGIONS = {
        'us1': 'https://api.sumologic.com',
        'us2': 'https://api.us2.sumologic.com',
        'eu':  'https://api.eu.sumologic.com',
        'au':  'https://api.au.sumologic.com',
        'de':  'https://api.de.sumologic.com',
        'jp':  'https://api.jp.sumologic.com',
        'ca':  'https://api.ca.sumologic.com',
        'in':  'https://api.in.sumologic.com',
    }

    def __init__(self, endpoint, access_id, access_key):
        self.endpoint = self._resolve_endpoint(endpoint)
        self._auth_header = self._make_auth_header(access_id, access_key)

    def _resolve_endpoint(self, endpoint):
        if endpoint.lower() in self.REGIONS:
            return self.REGIONS[endpoint.lower()]
        if endpoint.startswith('http'):
            return endpoint.rstrip('/')
        raise ValueError(
            f"Invalid endpoint. Use a region code "
            f"({', '.join(self.REGIONS)}) or a full URL."
        )

    def _make_auth_header(self, access_id, access_key):
        creds = base64.b64encode(f"{access_id}:{access_key}".encode()).decode()
        return f"Basic {creds}"

    def _request(self, path, method='GET', params=None, body=None):
        url = urljoin(self.endpoint, path)
        if params:
            url += '?' + urlencode(params)

        data = json.dumps(body).encode() if body is not None else None
        req = Request(url, data=data, method=method)
        req.add_header('Authorization', self._auth_header)
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')

        try:
            with urlopen(req) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except HTTPError as e:
            detail = e.read().decode() if e.fp else 'no body'
            print(f"HTTP {e.code} {e.reason}: {detail}", file=sys.stderr)
            sys.exit(1)
        except URLError as e:
            print(f"URL error: {e.reason}", file=sys.stderr)
            sys.exit(1)

    # ------------------------------------------------------------------
    # Partitions
    # ------------------------------------------------------------------

    def list_partitions_all(self):
        """Return every partition from the v1 API (unpaginated list)."""
        items = []
        token = None
        while True:
            params = {'token': token} if token else {}
            resp = self._request('/api/v1/partitions', params=params)
            items.extend(resp.get('data', []))
            token = resp.get('next')
            if not token:
                break
        return items

    # ------------------------------------------------------------------
    # Roles v2
    # ------------------------------------------------------------------

    def list_roles_all(self):
        """Return every role from the v2 API (unpaginated list)."""
        items = []
        token = None
        while True:
            params = {'token': token} if token else {}
            resp = self._request('/api/v2/roles', params=params)
            items.extend(resp.get('data', []))
            token = resp.get('next')
            if not token:
                break
        return items

    def create_role(self, payload):
        return self._request('/api/v2/roles', method='POST', body=payload)

    def update_role(self, role_id, payload):
        return self._request(f'/api/v2/roles/{role_id}', method='PUT', body=payload)


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

def filter_partitions(partitions, name_re, routing_re, tier_re, index_type_re, is_active):
    results = []
    for p in partitions:
        if not name_re.search(p.get('name', '')):
            continue
        if not routing_re.search(p.get('routingExpression', '')):
            continue
        if not tier_re.search(p.get('analyticsTier', '')):
            continue
        if not index_type_re.search(p.get('indexType', '')):
            continue
        if p.get('isActive') != is_active:
            continue
        results.append(p)
    return results


def role_name_for(partition, prefix):
    name  = partition.get('name', '')
    tier  = partition.get('analyticsTier', '')
    itype = partition.get('indexType', '')
    return f"{prefix}-{name}-{tier}-{itype}"


def build_role_payload(role_name, partition, log_analytics_filter='*',
                       audit_data_filter='*', security_data_filter='*',
                       capabilities=None):
    """Build the full payload for a create or update call."""
    return {
        "name": role_name,
        "description": (
            f"Auto-generated role for partition '{partition['name']}' "
            f"(tier={partition.get('analyticsTier', '')}, "
            f"type={partition.get('indexType', '')})"
        ),
        "logAnalyticsFilter": log_analytics_filter,
        "auditDataFilter": audit_data_filter,
        "securityDataFilter": security_data_filter,
        "selectionType": "Allow",
        "selectedViews": [{"viewName": partition['name']}],
        "users": [],
        "capabilities": capabilities or [],
        "autofillDependencies": True,
    }


def merge_update_payload(existing_role, partition, role_name,
                         log_analytics_filter='*', audit_data_filter='*',
                         security_data_filter='*', capabilities=None):
    """
    Produce the PUT payload by starting from the existing role (preserving
    users, capabilities, etc.) and overriding the partition-scoped fields.
    If capabilities is provided it replaces the existing list; otherwise the
    existing role's capabilities are preserved.
    """
    payload = dict(existing_role)
    # Strip read-only fields the API rejects on PUT
    for field in ('id', 'createdAt', 'createdBy', 'modifiedAt', 'modifiedBy', 'systemDefined'):
        payload.pop(field, None)

    payload['name'] = role_name
    payload['description'] = (
        f"Auto-generated role for partition '{partition['name']}' "
        f"(tier={partition.get('analyticsTier', '')}, "
        f"type={partition.get('indexType', '')})"
    )
    payload['logAnalyticsFilter'] = log_analytics_filter
    payload['auditDataFilter'] = audit_data_filter
    payload['securityDataFilter'] = security_data_filter
    payload['selectionType'] = 'Allow'
    payload['selectedViews'] = [{'viewName': partition['name']}]
    payload['autofillDependencies'] = True
    if capabilities is not None:
        payload['capabilities'] = capabilities
    return payload


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def print_partition_summary(partitions, prefix):
    print(f"\n{'='*60}")
    print(f"Matching partitions ({len(partitions)})")
    print(f"{'='*60}")
    if not partitions:
        print("  (none)")
        return
    col = 30
    print(f"  {'Name':<{col}} {'Tier':<15} {'Type':<15} {'Active'}")
    print(f"  {'-'*col} {'-'*14} {'-'*14} {'-'*6}")
    for p in partitions:
        print(
            f"  {p.get('name',''):<{col}} "
            f"{p.get('analyticsTier',''):<15} "
            f"{p.get('indexType',''):<15} "
            f"{str(p.get('isActive',''))}"
        )
    print()
    print(f"  Role name pattern: <prefix>-<name>-<tier>-<type>")
    print(f"  Prefix in use:     {prefix}")
    print(f"  Example:           {role_name_for(partitions[0], prefix)}")


def print_role_summary(partitions, existing_roles_by_name, prefix):
    expected = {role_name_for(p, prefix) for p in partitions}
    matched  = expected & set(existing_roles_by_name.keys())
    missing  = expected - matched

    print(f"\n{'='*60}")
    print(f"Role coverage summary")
    print(f"{'='*60}")
    print(f"  Partitions matched : {len(partitions)}")
    print(f"  Roles already exist: {len(matched)}")
    print(f"  Roles to be created: {len(missing)}")

    if matched:
        print(f"\n  Existing matching roles:")
        for n in sorted(matched):
            print(f"    [exists]  {n}")
    if missing:
        print(f"\n  Roles that will be created in execute mode:")
        for n in sorted(missing):
            print(f"    [missing] {n}")
    print()


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def mode_list(client, partitions, prefix, role_opts=None):
    print("Fetching roles …")
    all_roles = client.list_roles_all()
    roles_by_name = {r['name']: r for r in all_roles}

    print_partition_summary(partitions, prefix)
    print_role_summary(partitions, roles_by_name, prefix)

    print(f"Total roles in instance: {len(all_roles)}")
    print("Run with --mode execute to create/update roles.")


def mode_execute(client, partitions, prefix, dry_run=False, role_opts=None):
    role_opts = role_opts or {}
    print("Fetching roles …")
    all_roles = client.list_roles_all()
    roles_by_name = {r['name']: r for r in all_roles}

    print_partition_summary(partitions, prefix)
    print_role_summary(partitions, roles_by_name, prefix)

    created = []
    updated = []
    skipped = []

    for partition in partitions:
        rname = role_name_for(partition, prefix)

        if rname in roles_by_name:
            existing = roles_by_name[rname]
            payload  = merge_update_payload(existing, partition, rname, **role_opts)
            action   = 'UPDATE'
            role_id  = existing['id']
        else:
            payload = build_role_payload(rname, partition, **role_opts)
            action  = 'CREATE'
            role_id = None

        if dry_run:
            skipped.append(rname)
            print(f"  [dry-run] would {action}: {rname}")
            continue

        print(f"  {action}: {rname} … ", end='', flush=True)
        try:
            if action == 'CREATE':
                result = client.create_role(payload)
                created.append(rname)
            else:
                result = client.update_role(role_id, payload)
                updated.append(rname)
            print(f"ok (id={result.get('id', '?')})")
        except SystemExit:
            print("FAILED")
            raise

    print(f"\n{'='*60}")
    print(f"Execute summary")
    print(f"{'='*60}")
    if dry_run:
        print(f"  Dry-run — no changes made. Would process {len(skipped)} roles.")
    else:
        print(f"  Created : {len(created)}")
        print(f"  Updated : {len(updated)}")
        if created:
            for n in created: print(f"    + {n}")
        if updated:
            for n in updated: print(f"    ~ {n}")
    print()


# ---------------------------------------------------------------------------
# Terraform mode
# ---------------------------------------------------------------------------

def tf_label(name):
    """Convert a partition name to a valid Terraform resource label."""
    label = name.lower()
    label = re.sub(r'[^a-z0-9_]', '_', label)
    if label and label[0].isdigit():
        label = 'p_' + label
    return label


def tf_string(value):
    """Render a Python string as a quoted HCL string literal."""
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def tf_bool(value):
    return 'true' if value else 'false'


def partition_to_hcl(partition):
    """
    Return an HCL resource block string for a single partition.
    Only settable attributes are emitted; read-only fields (id, isActive,
    indexType, totalBytes, dataForwardingId) are omitted.
    """
    label = tf_label(partition.get('name', ''))
    lines = [f'resource "sumologic_partition" {tf_string(label)} {{']

    lines.append(f'  name = {tf_string(partition["name"])}')

    routing = partition.get('routingExpression', '')
    if routing:
        lines.append(f'  routing_expression = {tf_string(routing)}')

    tier = partition.get('analyticsTier', '')
    if tier:
        lines.append(f'  analytics_tier = {tf_string(tier.lower())}')

    retention = partition.get('retentionPeriod')
    if retention is not None and retention != -1:
        lines.append(f'  retention_period = {int(retention)}')

    if partition.get('isCompliant', False):
        lines.append(f'  is_compliant = true')

    is_included = partition.get('isIncludedInDefaultSearch')
    if is_included is not None:
        lines.append(f'  is_included_in_default_search = {tf_bool(is_included)}')

    lines.append('}')
    return '\n'.join(lines)


def mode_terraform(partitions, output_dir='terraform'):
    """Write terraform/partitions.tf with one resource block per partition."""
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, 'partitions.tf')

    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    header = (
        f'# Auto-generated by partition_roles.py on {timestamp}\n'
        f'# {len(partitions)} partition(s) exported\n'
        f'# Provider: registry.terraform.io/SumoLogic/sumologic\n\n'
    )

    blocks = [partition_to_hcl(p) for p in partitions]
    content = header + '\n\n'.join(blocks) + '\n'

    with open(out_path, 'w') as fh:
        fh.write(content)

    print_partition_summary(partitions, prefix='(n/a — terraform mode)')
    print(f"{'='*60}")
    print(f"Terraform output")
    print(f"{'='*60}")
    print(f"  Written : {out_path}")
    print(f"  Resources: {len(partitions)} sumologic_partition block(s)")
    print()
    print("  Next steps:")
    print("    cd terraform/")
    print("    terraform init")
    print("    terraform plan")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_bool(v):
    return v.lower() in ('true', '1', 'yes', 'on')


def main():
    parser = argparse.ArgumentParser(
        description='Create/update Sumo Logic v2 roles scoped to matching partitions.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List matching partitions and role coverage (no changes):
  %(prog)s --region us1 --access-id ID --access-key KEY

  # Same but only infrequent-tier partitions:
  %(prog)s --region us1 --access-id ID --access-key KEY --analytics-tier-filter Infrequent

  # Create/update roles for all active Partitions and DefaultIndex:
  %(prog)s --region us1 --access-id ID --access-key KEY --mode execute

  # Dry-run execute (shows what would happen):
  %(prog)s --region us1 --access-id ID --access-key KEY --mode execute --dry-run

  # Custom role prefix:
  %(prog)s --region us1 --access-id ID --access-key KEY --mode execute --role-prefix MyOrg

  # Write terraform/partitions.tf for all matching partitions:
  %(prog)s --region us1 --access-id ID --access-key KEY --mode terraform

  # Write to a custom directory:
  %(prog)s --region us1 --access-id ID --access-key KEY --mode terraform --terraform-dir infra/sumo

Available regions: us1, us2, eu, au, de, jp, ca, in
        """,
    )

    ep = parser.add_mutually_exclusive_group(required=True)
    ep.add_argument('--region',   choices=list(SumoLogicClient.REGIONS), help='Sumo Logic region code')
    ep.add_argument('--endpoint', help='Full API endpoint URL')

    parser.add_argument('--access-id',  default=os.environ.get('SUMO_ACCESS_ID'),
                        help='Sumo Logic access ID (default: $SUMO_ACCESS_ID)')
    parser.add_argument('--access-key', default=os.environ.get('SUMO_ACCESS_KEY'),
                        help='Sumo Logic access key (default: $SUMO_ACCESS_KEY)')

    parser.add_argument('--mode', choices=['list', 'execute', 'terraform'], default='list',
                        help='list: report only (default). execute: create/update roles. '
                             'terraform: write partitions.tf for matched partitions.')
    parser.add_argument('--dry-run', action='store_true',
                        help='In execute mode, print what would happen without making API calls.')
    parser.add_argument('--role-prefix', default='Sumo',
                        help='Prefix for generated role names (default: Sumo)')
    parser.add_argument('--terraform-dir', default='terraform',
                        metavar='DIR',
                        help='Output directory for terraform mode (default: terraform)')

    # Partition filters
    parser.add_argument('--name-filter', default='.*',
                        help='Regex to filter partitions by name (default: .*)')
    parser.add_argument('--routing-expression-filter', default='.*',
                        help='Regex to filter partitions by routingExpression (default: .*)')
    parser.add_argument('--analytics-tier-filter', default='.*',
                        help='Regex to filter partitions by analyticsTier (default: .*)')
    parser.add_argument('--index-type-filter', default='Partition|DefaultIndex',
                        help='Regex to filter partitions by indexType (default: Partition|DefaultIndex)')
    parser.add_argument('--is-active-filter', type=parse_bool, default=True,
                        metavar='true|false',
                        help='Filter partitions by isActive status (default: true)')

    # Role field overrides
    parser.add_argument('--log-analytics-filter', default='*',
                        help='logAnalyticsFilter value for created/updated roles (default: *)')
    parser.add_argument('--audit-data-filter', default='*',
                        help='auditDataFilter value for created/updated roles (default: *)')
    parser.add_argument('--security-data-filter', default='*',
                        help='securityDataFilter value for created/updated roles (default: *)')
    parser.add_argument('--capabilities', default='',
                        metavar='cap1,cap2,...',
                        help='Comma-separated capabilities to assign to roles (default: none). '
                             'e.g. manageContent,manageDataVolumeFeed')

    args = parser.parse_args()

    if not args.access_id:
        parser.error('--access-id is required (or set $SUMO_ACCESS_ID)')
    if not args.access_key:
        parser.error('--access-key is required (or set $SUMO_ACCESS_KEY)')

    # Compile filters
    try:
        name_re    = re.compile(args.name_filter)
        routing_re = re.compile(args.routing_expression_filter)
        tier_re    = re.compile(args.analytics_tier_filter)
        itype_re   = re.compile(args.index_type_filter)
    except re.error as e:
        parser.error(f"Invalid regex: {e}")

    endpoint = args.region if args.region else args.endpoint
    client   = SumoLogicClient(endpoint, args.access_id, args.access_key)

    print("Fetching partitions …")
    all_partitions = client.list_partitions_all()
    partitions     = filter_partitions(
        all_partitions, name_re, routing_re, tier_re, itype_re, args.is_active_filter
    )

    if not partitions:
        print("No partitions matched the given filters.")
        sys.exit(0)

    capabilities = [c.strip() for c in args.capabilities.split(',') if c.strip()] or None
    role_opts = {
        'log_analytics_filter':  args.log_analytics_filter,
        'audit_data_filter':     args.audit_data_filter,
        'security_data_filter':  args.security_data_filter,
        'capabilities':          capabilities,
    }

    try:
        if args.mode == 'list':
            mode_list(client, partitions, args.role_prefix, role_opts=role_opts)
        elif args.mode == 'execute':
            mode_execute(client, partitions, args.role_prefix, dry_run=args.dry_run, role_opts=role_opts)
        else:
            mode_terraform(partitions, output_dir=args.terraform_dir)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
