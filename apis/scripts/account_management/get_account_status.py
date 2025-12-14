#!/usr/bin/env python3
"""
Sumo Logic Account Status API Client

This script fetches account status information from the Sumo Logic API.
Retrieves current account usage status including plan type and data usage.

API Reference: https://api.us2.sumologic.com/docs/#operation/getStatus
Endpoint: GET /api/v1/account/status

Returns information about:
- Can update subscription: Whether account can update subscription
- Subscription: Current plan (Free, Trial, Essentials, Enterprise Operations, Enterprise Security, Enterprise Suite)
- Application use: Usage breakdowns including dashboards, scheduled searches, users, etc.
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
            print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
            print(f"Error details: {error_body}", file=sys.stderr)
            sys.exit(1)
        except URLError as e:
            print(f"URL Error: {e.reason}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            sys.exit(1)

    def get_account_status(self):
        """
        Get account status information

        Returns:
            dict: Account status including subscription details and usage information
        """
        return self._make_request('/api/v1/account/status')


def format_table_output(data):
    """Format account status data as a readable table"""
    lines = []
    lines.append("=" * 60)
    lines.append("ACCOUNT STATUS")
    lines.append("=" * 60)

    # Define order for common fields
    field_order = [
        'pricingModel', 'planType', 'planExpirationDays', 'accountActivated',
        'totalCredits', 'logModel', 'canUpdatePlan', 'canUpdateSubscription',
        'subscription', 'applicationUse'
    ]

    # Display fields in order
    for field in field_order:
        if field in data:
            value = data[field]
            # Format key from camelCase to Title Case
            formatted_key = ''.join([' ' + c if c.isupper() else c for c in field]).strip()
            formatted_key = formatted_key.title()

            # Handle applicationUse specially
            if field == 'applicationUse':
                if isinstance(value, dict) and value:
                    lines.append(f"\n{formatted_key}:")
                    for key, val in value.items():
                        formatted_subkey = ''.join([' ' + c if c.isupper() else c for c in key]).strip()
                        formatted_subkey = formatted_subkey.title()
                        lines.append(f"  {formatted_subkey}: {val}")
                elif value:  # Only show if not empty
                    lines.append(f"{formatted_key}: {value}")
            else:
                lines.append(f"{formatted_key}: {value}")

    # Display any remaining fields not in the predefined order
    for key, value in data.items():
        if key not in field_order:
            formatted_key = ''.join([' ' + c if c.isupper() else c for c in key]).strip()
            formatted_key = formatted_key.title()
            lines.append(f"{formatted_key}: {value}")

    lines.append("=" * 60)
    return '\n'.join(lines)


def format_csv_output(data):
    """Format account status data as CSV"""
    lines = []

    # Get all keys
    keys = list(data.keys())

    # Write header
    lines.append(','.join(keys))

    # Write data row
    row = []
    for key in keys:
        value = data.get(key, '')
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
        description='Get account status from Sumo Logic API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY
  %(prog)s --endpoint https://api.sumologic.com --access-id YOUR_ID --access-key YOUR_KEY
  %(prog)s --region us2 --access-id YOUR_ID --access-key YOUR_KEY --output table
  %(prog)s --region au --access-id YOUR_ID --access-key YOUR_KEY --output json

Available regions: us1, us2, eu, au, de, jp, ca, in

API Reference: https://api.us2.sumologic.com/docs/#operation/getStatus
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

    # Create client and fetch account status
    client = SumoLogicClient(endpoint, args.access_id, args.access_key)

    try:
        status = client.get_account_status()

        if args.output == 'json':
            print(json.dumps(status, indent=2))
        elif args.output == 'table':
            print(format_table_output(status))
        elif args.output == 'csv':
            print(format_csv_output(status))

    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
