#!/usr/bin/env python3
"""
Sumo Logic Child Organizations Usage API Client

This script fetches child organization usage data from the Sumo Logic API.
This endpoint is only available for parent organizations in a hierarchical contract model.

API Reference: https://api.us2.sumologic.com/docs/#operation/getChildUsages
Endpoint: GET /api/v1/account/usage/childUsages

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

    def _make_request(self, path, method='GET', params=None):
        """Make HTTP request to Sumo Logic API"""
        url = urljoin(self.endpoint, path)

        if params:
            from urllib.parse import urlencode
            url += '?' + urlencode(params)

        request = Request(url, method=method)
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
        return self._make_request('/api/v1/account/usage/childUsages')


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

                # Display organization info
                if 'organizationId' in child:
                    lines.append(f"Organization ID: {child['organizationId']}")
                if 'organizationName' in child:
                    lines.append(f"Organization Name: {child['organizationName']}")

                # Display usage metrics
                lines.append("\nUsage Metrics:")
                for key, value in child.items():
                    if key not in ['organizationId', 'organizationName']:
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
    """Format child usages data as CSV"""
    lines = []

    if 'data' in data and isinstance(data['data'], list):
        child_orgs = data['data']

        if child_orgs:
            # Get all unique keys from all child orgs
            all_keys = set()
            for child in child_orgs:
                all_keys.update(child.keys())

            # Sort keys with org info first
            priority_keys = ['organizationId', 'organizationName']
            other_keys = sorted([k for k in all_keys if k not in priority_keys])
            headers = priority_keys + other_keys

            # Write header
            lines.append(','.join(headers))

            # Write data rows
            for child in child_orgs:
                row = []
                for key in headers:
                    value = child.get(key, '')
                    # Quote values that might contain commas
                    if isinstance(value, str) and ',' in value:
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
