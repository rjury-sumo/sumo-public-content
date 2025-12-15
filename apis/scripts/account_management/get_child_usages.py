#!/usr/bin/env python3
"""
Sumo Logic Child Organizations Usage API Client

This script fetches child organization usage data from the Sumo Logic API.
This endpoint is only available for parent organizations in a hierarchical contract model.

API Reference: https://api.us2.sumologic.com/docs/#operation/getChildUsages
Endpoint: POST /api/v1/organizations/usages

Returns usage data for all child organizations including:
- Organization ID and name
- Data ingestion volumes
- Storage usage
- Metrics usage
- Other usage metrics per child organization

Note: This endpoint requires a parent organization account with child organizations.
Returns 403 Forbidden if the account does not have child organizations.
"""

import argparse
import base64
import json
import os
import sys
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class SumoLogicClient:
    """Client for interacting with Sumo Logic API"""

    # Regional API endpoints
    REGIONS = {
        'us1': 'https://api.sumologic.com',
        'us2': 'https://api.us2.sumologic.com',
        'eu': 'https://api.eu.sumologic.com',
        'au': 'https://api.au.sumologic.com',
        'de': 'https://api.de.sumologic.com',
        'jp': 'https://api.jp.sumologic.com',
        'ca': 'https://api.ca.sumologic.com',
        'in': 'https://api.in.sumologic.com'
    }

    def __init__(self, endpoint, access_id, access_key):
        """
        Initialize the client

        Args:
            endpoint (str): API endpoint URL or region code
            access_id (str): Sumo Logic access ID
            access_key (str): Sumo Logic access key
        """
        self.endpoint = self._resolve_endpoint(endpoint)
        self.access_id = access_id
        self.access_key = access_key
        self.auth_header = self._create_auth_header()

    def _resolve_endpoint(self, endpoint):
        """Resolve endpoint from region code or use as-is if it's a URL"""
        if endpoint.lower() in self.REGIONS:
            return self.REGIONS[endpoint.lower()]
        elif endpoint.startswith('http'):
            return endpoint.rstrip('/')
        else:
            raise ValueError(f"Invalid endpoint. Use a region code ({', '.join(self.REGIONS.keys())}) or full URL")

    def _create_auth_header(self):
        """Create Basic Auth header from access ID and key"""
        credentials = f"{self.access_id}:{self.access_key}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded_credentials}"

    def _make_request(self, path, method='GET', params=None, data=None):
        """Make HTTP request to Sumo Logic API"""
        url = urljoin(self.endpoint, path)

        if params:
            from urllib.parse import urlencode
            url += '?' + urlencode(params)

        # Prepare request body for POST
        request_data = None
        if data is not None:
            request_data = json.dumps(data).encode('utf-8')

        request = Request(url, data=request_data, method=method)
        request.add_header('Authorization', self.auth_header)
        request.add_header('Content-Type', 'application/json')
        request.add_header('Accept', 'application/json')

        try:
            with urlopen(request) as response:
                return json.loads(response.read().decode())
        except HTTPError as e:
            error_body = e.read().decode() if e.fp else 'No error details'
            if e.code == 403:
                print(f"HTTP Error 403: Forbidden", file=sys.stderr)
                print(f"This endpoint is only available for parent organizations with child organizations.", file=sys.stderr)
                print(f"Error details: {error_body}", file=sys.stderr)
            else:
                print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
                print(f"Error details: {error_body}", file=sys.stderr)
            sys.exit(1)
        except URLError as e:
            print(f"URL Error: {e.reason}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            sys.exit(1)

    def get_child_usages(self):
        """
        Get usage data for all child organizations

        Returns:
            dict: Array of child organization usage data

        Raises:
            HTTPError: 403 if account does not have child organizations
        """
        # POST request with empty body
        return self._make_request('/api/v1/organizations/usages', method='POST', data={})


def format_table_output(data):
    """Format child usages data as a readable table"""
    lines = []
    lines.append("=" * 80)
    lines.append("CHILD ORGANIZATIONS USAGE")
    lines.append("=" * 80)

    if 'data' in data and isinstance(data['data'], list):
        child_orgs = data['data']

        if not child_orgs:
            lines.append("\nNo child organizations found.")
        else:
            lines.append(f"\nTotal Child Organizations: {len(child_orgs)}\n")

            for idx, child in enumerate(child_orgs, 1):
                lines.append("-" * 80)
                lines.append(f"Child Organization #{idx}")
                lines.append("-" * 80)

                # Display organization info - check for both field name formats
                org_id = child.get('organizationId') or child.get('orgId')
                org_name = child.get('organizationName') or child.get('orgName')

                if org_id:
                    lines.append(f"Organization ID: {org_id}")
                if org_name:
                    lines.append(f"Organization Name: {org_name}")
                if 'status' in child:
                    lines.append(f"Status: {child['status']}")
                if 'allocatedCredits' in child:
                    allocated = child['allocatedCredits']
                    if isinstance(allocated, (int, float)) and allocated > 1000:
                        formatted_allocated = f"{allocated:,.2f}"
                    else:
                        formatted_allocated = allocated
                    lines.append(f"Allocated Credits: {formatted_allocated}")

                # Handle nested usages object
                if 'usages' in child and isinstance(child['usages'], dict):
                    lines.append("\nUsage Metrics:")
                    for key, value in child['usages'].items():
                        # Format key from camelCase to Title Case
                        formatted_key = ''.join([' ' + c if c.isupper() else c for c in key]).strip()
                        formatted_key = formatted_key.title()

                        # Format large numbers with commas, handle None values
                        if value is None:
                            formatted_value = "N/A"
                        elif isinstance(value, (int, float)) and value > 1000:
                            formatted_value = f"{value:,.2f}"
                        else:
                            formatted_value = value
                        lines.append(f"  {formatted_key}: {formatted_value}")
                else:
                    # Fallback to flat structure for other metrics
                    lines.append("\nUsage Metrics:")
                    excluded_keys = ['organizationId', 'organizationName', 'orgId', 'orgName', 'status', 'allocatedCredits', 'usages']
                    for key, value in child.items():
                        if key not in excluded_keys:
                            # Format key from camelCase to Title Case
                            formatted_key = ''.join([' ' + c if c.isupper() else c for c in key]).strip()
                            formatted_key = formatted_key.title()

                            # Format large numbers with commas
                            if isinstance(value, (int, float)) and value > 1000:
                                formatted_value = f"{value:,.2f}"
                            else:
                                formatted_value = value
                            lines.append(f"  {formatted_key}: {formatted_value}")

                lines.append("")
    else:
        lines.append("\nNo child usage data available.")

    lines.append("=" * 80)
    return '\n'.join(lines)


def format_csv_output(data):
    """Format child usages data as CSV, flattening nested usages object"""
    lines = []

    if 'data' in data and isinstance(data['data'], list):
        child_orgs = data['data']

        if child_orgs:
            # Flatten the data structure to handle nested usages
            flattened_data = []
            all_keys = set()

            for child in child_orgs:
                flattened_row = {}

                # Add top-level fields
                for key, value in child.items():
                    if key != 'usages':
                        flattened_row[key] = value
                        all_keys.add(key)

                # Add nested usages fields with prefix
                if 'usages' in child and isinstance(child['usages'], dict):
                    for usage_key, usage_value in child['usages'].items():
                        flattened_key = f"usage_{usage_key}"
                        flattened_row[flattened_key] = usage_value
                        all_keys.add(flattened_key)

                flattened_data.append(flattened_row)

            # Sort keys with org info first, usages last
            org_keys = [k for k in ['organizationId', 'organizationName', 'orgId', 'orgName', 'status', 'allocatedCredits'] if k in all_keys]
            usage_keys = sorted([k for k in all_keys if k.startswith('usage_')])
            other_keys = sorted([k for k in all_keys if k not in org_keys and not k.startswith('usage_')])
            headers = org_keys + other_keys + usage_keys

            # Write header
            lines.append(','.join(headers))

            # Write data rows
            for row_data in flattened_data:
                row = []
                for key in headers:
                    value = row_data.get(key, '')
                    # Handle None values
                    if value is None:
                        row.append('N/A')
                    # Quote values that might contain commas
                    elif isinstance(value, str) and ',' in value:
                        row.append(f'"{value}"')
                    else:
                        row.append(str(value))
                lines.append(','.join(row))

    return '\n'.join(lines)


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Get child organizations usage from Sumo Logic API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY
  %(prog)s --endpoint https://api.sumologic.com --access-id YOUR_ID --access-key YOUR_KEY
  %(prog)s --region us2 --access-id YOUR_ID --access-key YOUR_KEY --output table
  %(prog)s --region au --access-id YOUR_ID --access-key YOUR_KEY --output csv

Available regions: us1, us2, eu, au, de, jp, ca, in

Note: This endpoint is only available for parent organizations with child organizations.
      You will receive a 403 Forbidden error if your account does not have child organizations.

API Reference: https://api.us2.sumologic.com/docs/#operation/getChildUsages
        """
    )

    endpoint_group = parser.add_mutually_exclusive_group(required=True)
    endpoint_group.add_argument(
        '--region',
        choices=['us1', 'us2', 'eu', 'au', 'de', 'jp', 'ca', 'in'],
        help='Sumo Logic region code'
    )
    endpoint_group.add_argument(
        '--endpoint',
        help='Full API endpoint URL'
    )

    parser.add_argument(
        '--access-id',
        default=os.environ.get('SUMO_ACCESS_ID'),
        help='Sumo Logic access ID (default: SUMO_ACCESS_ID environment variable)'
    )
    parser.add_argument(
        '--access-key',
        default=os.environ.get('SUMO_ACCESS_KEY'),
        help='Sumo Logic access key (default: SUMO_ACCESS_KEY environment variable)'
    )
    parser.add_argument(
        '--output',
        choices=['json', 'table', 'csv'],
        default='json',
        help='Output format (default: json)'
    )

    args = parser.parse_args()

    # Validate required credentials
    if not args.access_id:
        parser.error("--access-id is required (or set SUMO_ACCESS_ID environment variable)")
    if not args.access_key:
        parser.error("--access-key is required (or set SUMO_ACCESS_KEY environment variable)")

    # Determine endpoint
    endpoint = args.region if args.region else args.endpoint

    # Create client and fetch child usages
    client = SumoLogicClient(endpoint, args.access_id, args.access_key)

    try:
        child_usages = client.get_child_usages()

        if args.output == 'json':
            print(json.dumps(child_usages, indent=2))
        elif args.output == 'table':
            print(format_table_output(child_usages))
        elif args.output == 'csv':
            print(format_csv_output(child_usages))

    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
