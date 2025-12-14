#!/usr/bin/env python3
"""
Sumo Logic Usage Forecast API Client

This script fetches usage forecast information from the Sumo Logic API.
Retrieves projected data usage for the specified number of days.

API Reference: https://api.us2.sumologic.com/docs/#operation/getUsageForecast
Endpoint: GET /api/v1/account/usage/forecast

Query Parameters:
- numberOfDays (required): Number of days for which to get the usage forecast (1-365)

Returns forecasted usage including:
- Data ingestion forecast
- Storage forecast
- Metrics forecast
"""

import argparse
import base64
import json
import os
import sys
from urllib.parse import urljoin, urlencode
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

    def get_usage_forecast(self, number_of_days):
        """
        Get usage forecast for the specified number of days

        Args:
            number_of_days (int): Number of days for the forecast (1-365)

        Returns:
            dict: Usage forecast data
        """
        if not 1 <= number_of_days <= 365:
            raise ValueError("Number of days must be between 1 and 365")

        params = {'numberOfDays': number_of_days}
        return self._make_request('/api/v1/account/usage/forecast', params=params)


def format_table_output(data, number_of_days):
    """Format usage forecast data as a readable table"""
    lines = []
    lines.append("=" * 60)
    lines.append(f"USAGE FORECAST - {number_of_days} DAY(S)")
    lines.append("=" * 60)

    if 'data' in data:
        forecast_data = data['data']

        # Display daily forecast data
        if isinstance(forecast_data, list):
            lines.append("\nDaily Forecast:")
            lines.append("-" * 60)
            for idx, day_data in enumerate(forecast_data, 1):
                lines.append(f"\nDay {idx}:")
                for key, value in day_data.items():
                    # Format key from camelCase to Title Case
                    formatted_key = ''.join([' ' + c if c.isupper() else c for c in key]).strip()
                    formatted_key = formatted_key.title()

                    # Format large numbers with commas
                    if isinstance(value, (int, float)) and value > 1000:
                        formatted_value = f"{value:,.2f}"
                    else:
                        formatted_value = value
                    lines.append(f"  {formatted_key}: {formatted_value}")
        else:
            # Display summary data
            for key, value in forecast_data.items():
                formatted_key = ''.join([' ' + c if c.isupper() else c for c in key]).strip()
                formatted_key = formatted_key.title()

                if isinstance(value, (int, float)) and value > 1000:
                    formatted_value = f"{value:,.2f}"
                else:
                    formatted_value = value
                lines.append(f"{formatted_key}: {formatted_value}")

    lines.append("=" * 60)
    return '\n'.join(lines)


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Get usage forecast from Sumo Logic API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY --days 30
  %(prog)s --endpoint https://api.sumologic.com --access-id YOUR_ID --access-key YOUR_KEY --days 7
  %(prog)s --region us2 --access-id YOUR_ID --access-key YOUR_KEY --days 90 --output table
  %(prog)s --region au --access-id YOUR_ID --access-key YOUR_KEY --days 180 --output json

Available regions: us1, us2, eu, au, de, jp, ca, in

API Reference: https://api.us2.sumologic.com/docs/#operation/getUsageForecast
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
        '--days',
        type=int,
        required=True,
        help='Number of days for usage forecast (1-365)'
    )
    parser.add_argument(
        '--output',
        choices=['json', 'table'],
        default='json',
        help='Output format (default: json)'
    )

    args = parser.parse_args()

    # Validate required credentials
    if not args.access_id:
        parser.error("--access-id is required (or set SUMO_ACCESS_ID environment variable)")
    if not args.access_key:
        parser.error("--access-key is required (or set SUMO_ACCESS_KEY environment variable)")

    # Validate days parameter
    if not 1 <= args.days <= 365:
        parser.error("Days must be between 1 and 365")

    # Determine endpoint
    endpoint = args.region if args.region else args.endpoint

    # Create client and fetch usage forecast
    client = SumoLogicClient(endpoint, args.access_id, args.access_key)

    try:
        forecast = client.get_usage_forecast(args.days)

        if args.output == 'json':
            print(json.dumps(forecast, indent=2))
        elif args.output == 'table':
            print(format_table_output(forecast, args.days))

    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
