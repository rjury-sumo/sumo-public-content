#!/usr/bin/env python3
"""
Sumo Logic Partitions API Client

This script fetches partitions from the Sumo Logic API.
Allows specifying the API endpoint region and authentication credentials.
"""

import argparse
import base64
import json
import re
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

    def list_partitions(self, analytics_tier_filter='.*', index_type_filter='Partition', is_active_filter=True,
                       is_included_in_default_search_filter=None, name_filter='.*', routing_expression_filter='.*'):
        """
        List partitions with optional filtering

        Args:
            analytics_tier_filter (str): Regex pattern for analyticsTier filtering
            index_type_filter (str): Filter by indexType
            is_active_filter (bool): Filter by isActive status
            is_included_in_default_search_filter (bool, optional): Filter by isIncludedInDefaultSearch status
            name_filter (str): Regex pattern for name filtering
            routing_expression_filter (str): Regex pattern for routingExpression filtering
        """
        all_partitions = []
        next_token = None

        # Paginate through all results
        while True:
            params = {}
            if next_token:
                params['token'] = next_token

            response = self._make_request('/api/v1/partitions', params=params)

            if 'data' not in response:
                break

            all_partitions.extend(response['data'])

            # Check if there's a next page
            next_token = response.get('next')
            if not next_token:
                break

        # Apply filtering to all collected partitions
        filtered_partitions = []
        analytics_tier_regex = re.compile(analytics_tier_filter)
        name_regex = re.compile(name_filter)
        routing_expression_regex = re.compile(routing_expression_filter)

        for partition in all_partitions:
            # Filter by analyticsTier using regex
            analytics_tier = partition.get('analyticsTier', '')
            if not analytics_tier_regex.match(analytics_tier):
                continue

            # Filter by indexType
            if partition.get('indexType') != index_type_filter:
                continue

            # Filter by isActive
            if partition.get('isActive') != is_active_filter:
                continue

            # Filter by isIncludedInDefaultSearch (optional)
            if is_included_in_default_search_filter is not None:
                if partition.get('isIncludedInDefaultSearch') != is_included_in_default_search_filter:
                    continue

            # Filter by name using regex
            name = partition.get('name', '')
            if not name_regex.match(name):
                continue

            # Filter by routingExpression using regex
            routing_expression = partition.get('routingExpression', '')
            if not routing_expression_regex.match(routing_expression):
                continue

            filtered_partitions.append(partition)

        # Return response in same format as API
        return {
            'data': filtered_partitions
        }


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='List partitions from Sumo Logic API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY
  %(prog)s --endpoint https://api.sumologic.com --access-id YOUR_ID --access-key YOUR_KEY
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY --analytics-tier-filter "Infrequent|Continuous"
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY --index-type-filter "View" --is-active-filter false
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY --name-filter "prod.*" --is-included-in-default-search-filter true
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY --routing-expression-filter ".*error.*"
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY --output table --output-properties name isActive analyticsTier
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY --output list --output-properties name
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY --output list

Available regions: us1, us2, eu, au, de, jp, ca, in
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
        required=True,
        help='Sumo Logic access ID'
    )
    parser.add_argument(
        '--access-key',
        required=True,
        help='Sumo Logic access key'
    )
    parser.add_argument(
        '--output',
        choices=['json', 'table', 'list'],
        default='json',
        help='Output format (default: json)'
    )
    parser.add_argument(
        '--output-properties',
        nargs='+',
        help='Space-separated list of properties to include in output (e.g., name id isActive). If not specified, all properties are included.'
    )
    parser.add_argument(
        '--analytics-tier-filter',
        default='.*',
        help='Regex pattern to filter partitions by analyticsTier (default: .*)'
    )
    parser.add_argument(
        '--index-type-filter',
        default='Partition',
        help='Filter partitions by indexType (default: Partition)'
    )
    parser.add_argument(
        '--is-active-filter',
        type=lambda x: x.lower() in ['true', '1', 'yes', 'on'],
        default=True,
        help='Filter partitions by isActive status (true/false, default: true)'
    )
    parser.add_argument(
        '--is-included-in-default-search-filter',
        type=lambda x: x.lower() in ['true', '1', 'yes', 'on'],
        default=None,
        help='Filter partitions by isIncludedInDefaultSearch status (true/false, no default - no filtering if not provided)'
    )
    parser.add_argument(
        '--name-filter',
        default='.*',
        help='Regex pattern to filter partitions by name (default: .*)'
    )
    parser.add_argument(
        '--routing-expression-filter',
        default='.*',
        help='Regex pattern to filter partitions by routingExpression (default: .*)'
    )

    args = parser.parse_args()

    # Determine endpoint
    endpoint = args.region if args.region else args.endpoint

    # Create client and fetch partitions
    client = SumoLogicClient(endpoint, args.access_id, args.access_key)

    try:
        partitions = client.list_partitions(
            analytics_tier_filter=args.analytics_tier_filter,
            index_type_filter=args.index_type_filter,
            is_active_filter=args.is_active_filter,
            is_included_in_default_search_filter=args.is_included_in_default_search_filter,
            name_filter=args.name_filter,
            routing_expression_filter=args.routing_expression_filter
        )

        # Filter output properties if specified
        output_data = partitions
        if args.output_properties and 'data' in partitions:
            filtered_partitions = []
            for partition in partitions['data']:
                filtered_partition = {prop: partition.get(prop, 'N/A') for prop in args.output_properties}
                filtered_partitions.append(filtered_partition)
            output_data = {'data': filtered_partitions}

        if args.output == 'json':
            print(json.dumps(output_data, indent=2))
        elif args.output == 'table':
            if 'data' in output_data and output_data['data']:
                # Determine which properties to show
                if args.output_properties:
                    properties = args.output_properties
                else:
                    # Use common properties if no specific ones requested
                    properties = ['name', 'isActive', 'indexType', 'analyticsTier', 'routingExpression']

                # Create header
                header_widths = []
                for prop in properties:
                    if prop == 'name':
                        header_widths.append(30)
                    elif prop == 'routingExpression':
                        header_widths.append(40)
                    elif prop in ['isActive', 'indexType']:
                        header_widths.append(12)
                    elif prop == 'analyticsTier':
                        header_widths.append(15)
                    else:
                        header_widths.append(20)

                # Print header
                header_line = ""
                separator_line = ""
                for i, prop in enumerate(properties):
                    width = header_widths[i]
                    header_line += f"{prop.capitalize():<{width}} "
                    separator_line += "-" * width + " "

                print(header_line.rstrip())
                print(separator_line.rstrip())

                # Print data rows
                for partition in output_data['data']:
                    row_line = ""
                    for i, prop in enumerate(properties):
                        width = header_widths[i]
                        value = str(partition.get(prop, 'N/A'))
                        # Truncate if too long
                        if len(value) > width - 1:
                            value = value[:width-4] + "..."
                        row_line += f"{value:<{width}} "
                    print(row_line.rstrip())
            else:
                print("No partitions found")
        elif args.output == 'list':
            if 'data' in output_data and output_data['data']:
                for partition in output_data['data']:
                    if args.output_properties:
                        # Show only requested properties
                        values = [str(partition.get(prop, 'N/A')) for prop in args.output_properties]
                        print(" | ".join(values))
                    else:
                        # Show name by default for list format
                        print(partition.get('name', 'N/A'))
            else:
                print("No partitions found")

    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()