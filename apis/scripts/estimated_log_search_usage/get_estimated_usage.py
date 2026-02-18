#!/usr/bin/env python3
"""
Sumo Logic Log Search Estimated Usage Query

This script queries the estimated data volume that would be scanned for a given
log search in the Infrequent Data Tier and Flex, over a particular time range.

Usage example:
    python3 get_estimated_usage.py \\
        --region us2 \\
        --access-id YOUR_ACCESS_ID \\
        --access-key YOUR_ACCESS_KEY \\
        --query '_sourceCategory=prod/app' \\
        --from '-1h' \\
        --to 'now' \\
        --timezone 'UTC'
"""

import argparse
import base64
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

try:
    import yaml
except ImportError:
    yaml = None

# Set up logger
logger = logging.getLogger(__name__)


def setup_logging(log_level='INFO'):
    """Configure logging with appropriate level and format"""
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')

    formatter = logging.Formatter(
        fmt='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)

    logger.setLevel(numeric_level)
    logger.addHandler(console_handler)
    logger.propagate = False


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

        request = Request(url, method=method)
        request.add_header('Authorization', self.auth_header)
        request.add_header('Content-Type', 'application/json')
        request.add_header('Accept', 'application/json')

        if data:
            json_data = json.dumps(data, indent=2)
            logger.debug(f"Request body: {json_data}")
            request.data = json_data.encode()

        try:
            response = urlopen(request)
            return json.loads(response.read().decode())
        except HTTPError as e:
            error_body = e.read().decode() if e.fp else 'No error details'
            logger.error(f"HTTP Error {e.code}: {e.reason}")
            logger.error(f"Error details: {error_body}")
            sys.exit(1)
        except URLError as e:
            logger.error(f"URL Error: {e.reason}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            sys.exit(1)

    def get_estimated_usage(self, query, from_time, to_time, time_zone='UTC', by_view=False):
        """
        Get estimated data volume for a log search query

        Args:
            query (str): Log search query
            from_time (str): Start time (ISO format or epoch ms)
            to_time (str): End time (ISO format or epoch ms)
            time_zone (str): Time zone for the search (default: UTC)
            by_view (bool): If True, use estimatedUsageByView endpoint for partition/view breakdown

        Returns:
            dict: Estimated usage response
        """
        request_data = {
            'queryString': query,
            'timeRange': {
                'type': 'BeginBoundedTimeRange',
                'from': {
                    'type': 'EpochTimeRangeBoundary',
                    'epochMillis': from_time
                },
                'to': {
                    'type': 'EpochTimeRangeBoundary',
                    'epochMillis': to_time
                }
            },
            'timezone': time_zone
        }

        # Choose endpoint based on by_view parameter
        endpoint = '/api/v1/logSearches/estimatedUsageByView' if by_view else '/api/v1/logSearches/estimatedUsage'

        return self._make_request(
            endpoint,
            method='POST',
            data=request_data
        )


def parse_time_value(time_value):
    """
    Parse time value and convert to epoch milliseconds

    Supports:
    - ISO format strings: "2024-01-01T00:00:00Z"
    - Epoch milliseconds: 1704067200000
    - Relative times: "-1h", "-30m", "-2d", "-1w", "now"

    Args:
        time_value: Time specification as string or int

    Returns:
        int: Epoch milliseconds
    """
    # If it's already an integer (epoch milliseconds), return as-is
    if isinstance(time_value, int):
        return time_value

    # Convert to string for processing
    time_str = str(time_value).strip()

    # Handle "now"
    if time_str.lower() == "now":
        return int(datetime.now().timestamp() * 1000)

    # Handle relative time formats like "-1h", "-30m", "-2d", "-1w"
    relative_pattern = r'^([+-]?)(\d+)([smhdw])$'
    match = re.match(relative_pattern, time_str.lower())

    if match:
        sign, amount, unit = match.groups()
        amount = int(amount)

        # Default to negative if no sign specified (going back in time)
        if sign != '+':
            amount = -amount

        # Convert unit to timedelta
        unit_map = {
            's': 'seconds',
            'm': 'minutes',
            'h': 'hours',
            'd': 'days',
            'w': 'weeks'
        }

        if unit in unit_map:
            delta_kwargs = {unit_map[unit]: amount}
            target_time = datetime.now() + timedelta(**delta_kwargs)
            return int(target_time.timestamp() * 1000)

    # Try to parse as ISO format
    try:
        # Handle various ISO formats
        for fmt in [
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d'
        ]:
            try:
                dt = datetime.strptime(time_str, fmt)
                return int(dt.timestamp() * 1000)
            except ValueError:
                continue

        # If none of the formats worked, try parsing as epoch milliseconds
        return int(float(time_str))

    except (ValueError, TypeError):
        raise ValueError(f"Invalid time format: {time_value}. Supported formats: ISO datetime, epoch milliseconds, or relative time (e.g., '-1h', '-30m', '-2d', 'now')")


def format_bytes(bytes_value):
    """
    Format bytes value to human-readable format

    Args:
        bytes_value (int): Number of bytes

    Returns:
        str: Formatted string (e.g., "1.5 GB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"


def load_yaml_config(yaml_file):
    """Load batch configuration from YAML file"""
    if yaml is None:
        logger.error("PyYAML is required for batch mode but not installed")
        logger.error("Install it with: pip install PyYAML")
        sys.exit(1)

    try:
        with open(yaml_file, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"YAML file '{yaml_file}' not found")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file: {e}")
        sys.exit(1)


def validate_batch_config(config):
    """Validate batch configuration"""
    if not isinstance(config, dict):
        logger.error("YAML config must be a dictionary")
        sys.exit(1)

    if 'queries' not in config:
        logger.error("YAML config must have a 'queries' list")
        sys.exit(1)

    if not isinstance(config['queries'], list) or len(config['queries']) == 0:
        logger.error("'queries' must be a non-empty list")
        sys.exit(1)

    # Validate each query
    for idx, query_config in enumerate(config['queries']):
        if 'name' not in query_config:
            logger.error(f"Query {idx} missing required field 'name'")
            sys.exit(1)
        if 'query' not in query_config:
            logger.error(f"Query {idx} missing required field 'query'")
            sys.exit(1)
        if 'from' not in query_config:
            logger.error(f"Query {idx} missing required field 'from'")
            sys.exit(1)
        if 'to' not in query_config:
            logger.error(f"Query {idx} missing required field 'to'")
            sys.exit(1)


def generate_html_report(batch_results, config):
    """Generate HTML webview report from batch results"""
    # Calculate summary statistics first
    total_bytes = 0
    for result in batch_results:
        total_bytes += result.get('total_bytes', 0)

    total_queries = len(batch_results)
    avg_bytes = total_bytes // total_queries if total_queries > 0 else 0

    # Generate query cards HTML
    query_cards_html = []
    for idx, result in enumerate(batch_results):
        query_name = result.get('name', f'Query {idx+1}')
        query_text = result.get('query', '')
        time_range = result.get('time_range', '')
        timezone = result.get('timezone', 'UTC')
        by_view = result.get('by_view', False)
        total_bytes_query = result.get('total_bytes', 0)

        # Build breakdown table if available
        breakdown_html = ""
        if 'breakdown' in result and result['breakdown']:
            breakdown_html = """
            <table class="breakdown-table">
                <thead>
                    <tr>
                        <th>View/Partition</th>
                        <th>Tier</th>
                        <th>Metering Type</th>
                        <th>Data Scanned</th>
                    </tr>
                </thead>
                <tbody>"""

            for view in result['breakdown']:
                tier_class = f"tier-{view.get('tier', 'unknown').lower()}"
                breakdown_html += f"""
                    <tr>
                        <td><strong>{view.get('view_name', 'Unknown')}</strong></td>
                        <td><span class="tier-badge {tier_class}">{view.get('tier', 'Unknown')}</span></td>
                        <td>{view.get('metering_type', 'Unknown')}</td>
                        <td><strong>{view.get('bytes_formatted', '0 B')}</strong></td>
                    </tr>"""

            breakdown_html += """
                </tbody>
            </table>"""

        query_card_html = f"""
        <div class="query-card">
            <h2>
                {query_name}
                <span class="query-badge">{'With Breakdown' if by_view else 'Standard'}</span>
            </h2>

            <div class="query-text">{query_text}</div>

            <div class="query-meta">
                <div class="meta-item">
                    <div class="label">Time Range</div>
                    <div class="value">{time_range}</div>
                </div>
                <div class="meta-item">
                    <div class="label">Timezone</div>
                    <div class="value">{timezone}</div>
                </div>
                <div class="meta-item">
                    <div class="label">Estimated Data Scan</div>
                    <div class="value">{format_bytes(total_bytes_query)}</div>
                </div>
            </div>

            {breakdown_html}
        </div>"""

        query_cards_html.append(query_card_html)

    # Build the complete HTML using string concatenation instead of format()
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sumo Logic Estimated Usage Report</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        .header {
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 30px;
        }

        .header h1 {
            color: #333;
            font-size: 32px;
            margin-bottom: 10px;
        }

        .header .meta {
            color: #666;
            font-size: 14px;
        }

        .summary-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .card {
            background: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }

        .card-title {
            font-size: 14px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
        }

        .card-value {
            font-size: 32px;
            font-weight: bold;
            color: #333;
        }

        .card-value.large {
            color: #667eea;
        }

        .query-card {
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 20px;
        }

        .query-card h2 {
            color: #333;
            font-size: 24px;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .query-badge {
            background: #667eea;
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: normal;
        }

        .query-text {
            background: #f5f5f5;
            padding: 15px;
            border-radius: 5px;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            color: #333;
            margin-bottom: 20px;
            overflow-x: auto;
        }

        .query-meta {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }

        .meta-item {
            padding: 10px 15px;
            background: #f9f9f9;
            border-radius: 5px;
        }

        .meta-item .label {
            font-size: 12px;
            color: #666;
            margin-bottom: 5px;
        }

        .meta-item .value {
            font-size: 16px;
            color: #333;
            font-weight: 600;
        }

        .breakdown-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }

        .breakdown-table th {
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }

        .breakdown-table td {
            padding: 12px;
            border-bottom: 1px solid #eee;
        }

        .breakdown-table tr:hover {
            background: #f9f9f9;
        }

        .footer {
            text-align: center;
            color: white;
            margin-top: 30px;
            padding: 20px;
            opacity: 0.9;
        }

        .tier-badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }

        .tier-continuous {
            background: #10b981;
            color: white;
        }

        .tier-frequent {
            background: #f59e0b;
            color: white;
        }

        .tier-infrequent {
            background: #6366f1;
            color: white;
        }
    </style>
</head>
<body>"""

    # Add dynamically generated content
    html += f"""
    <div class="container">
        <div class="header">
            <h1>📊 Sumo Logic Estimated Usage Report</h1>
            <div class="meta">Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>

        <div class="summary-cards">
            <div class="card">
                <div class="card-title">Total Queries</div>
                <div class="card-value">{total_queries}</div>
            </div>
            <div class="card">
                <div class="card-title">Total Estimated Scan</div>
                <div class="card-value large">{format_bytes(total_bytes)}</div>
            </div>
            <div class="card">
                <div class="card-title">Average Per Query</div>
                <div class="card-value">{format_bytes(avg_bytes)}</div>
            </div>
        </div>"""

    # Add query cards
    html += ''.join(query_cards_html)

    # Close HTML
    html += """
        <div class="footer">
            <p>Generated with Sumo Logic Estimated Usage Tool</p>
            <p style="font-size: 12px; margin-top: 10px;">🤖 Powered by Claude Code</p>
        </div>
    </div>
</body>
</html>"""

    return html


def execute_single_estimation(client, query, from_time_ms, to_time_ms, timezone, by_view, query_name=None):
    """Execute a single estimation query and return structured result"""
    try:
        result = client.get_estimated_usage(
            query=query,
            from_time=from_time_ms,
            to_time=to_time_ms,
            time_zone=timezone,
            by_view=by_view
        )

        # Extract and structure the data
        usage_details = result.get('estimatedUsageDetails', {})
        total_bytes = 0
        breakdown = []

        if isinstance(usage_details, list):
            # By-view endpoint
            for view in usage_details:
                view_name = view.get('viewName', 'Unknown')
                if not view_name or view_name.strip() == '':
                    view_name = 'sumologic_default'
                view_usage_details = view.get('usageDetails', [])
                for detail in view_usage_details:
                    view_bytes = detail.get('dataScannedInBytes', 0)
                    total_bytes += view_bytes
                    breakdown.append({
                        'view_name': view_name,
                        'tier': detail.get('tier', 'Unknown'),
                        'metering_type': detail.get('meteringType', 'Unknown'),
                        'bytes': view_bytes,
                        'bytes_formatted': format_bytes(view_bytes)
                    })
        else:
            # Standard endpoint
            total_bytes = usage_details.get('dataScannedInBytes', 0)

        return {
            'success': True,
            'name': query_name,
            'query': query,
            'time_range': f"{datetime.fromtimestamp(from_time_ms/1000)} to {datetime.fromtimestamp(to_time_ms/1000)}",
            'timezone': timezone,
            'by_view': by_view,
            'total_bytes': total_bytes,
            'breakdown': breakdown,
            'raw_result': result
        }
    except Exception as e:
        logger.error(f"Error executing query '{query_name}': {e}")
        return {
            'success': False,
            'name': query_name,
            'query': query,
            'error': str(e)
        }


def execute_batch(client, config, args):
    """Execute batch queries from YAML config"""
    queries = config.get('queries', [])
    batch_results = []

    logger.info(f"Executing {len(queries)} queries in batch mode")

    for idx, query_config in enumerate(queries):
        query_name = query_config.get('name', f'Query {idx+1}')
        query = query_config['query']
        from_time_str = query_config['from']
        to_time_str = query_config['to']
        timezone = query_config.get('timezone', args.timezone)
        by_view = query_config.get('byView', args.by_view)

        logger.info(f"Executing query {idx+1}/{len(queries)}: {query_name}")

        # Parse time values
        try:
            from_time_ms = parse_time_value(from_time_str)
            to_time_ms = parse_time_value(to_time_str)
        except ValueError as e:
            logger.error(f"Error parsing time for query '{query_name}': {e}")
            batch_results.append({
                'success': False,
                'name': query_name,
                'query': query,
                'error': str(e)
            })
            continue

        # Execute the query
        result = execute_single_estimation(
            client, query, from_time_ms, to_time_ms, timezone, by_view, query_name
        )
        batch_results.append(result)

    return batch_results


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Query estimated data volume for Sumo Logic log searches',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Time Format Options:
  - Relative times: "-1h", "-30m", "-2d", "-1w", "now"
  - ISO format: "2024-01-01T00:00:00Z"
  - Epoch milliseconds: 1704067200000

Examples:
  %(prog)s --region us2 --access-id YOUR_ID --access-key YOUR_KEY \\
      --query '_sourceCategory=prod/app' --from-time '-1h' --to-time 'now'

  %(prog)s --region us2 --access-id YOUR_ID --access-key YOUR_KEY \\
      --query '_sourceCategory=prod/app | count by _sourceHost' \\
      --from-time '2024-01-01T00:00:00Z' --to-time '2024-01-01T01:00:00Z' \\
      --timezone 'America/Los_Angeles' --output json

  %(prog)s --endpoint https://api.au.sumologic.com \\
      --access-id YOUR_ID --access-key YOUR_KEY \\
      --query '_sourceCategory=*' --from-time '-24h' --to-time 'now' \\
      --output table

  # Get breakdown by view/partition
  %(prog)s --region us2 --access-id YOUR_ID --access-key YOUR_KEY \\
      --query '_view=my_view' --from-time '-7d' --to-time 'now' \\
      --by-view --output table

Environment Variables:
  SUMO_ACCESS_ID    : Access ID (alternative to --access-id)
  SUMO_ACCESS_KEY   : Access key (alternative to --access-key)
  SUMO_ENDPOINT     : Region or endpoint URL (alternative to --region/--endpoint)

Available regions: us1, us2, eu, au, de, jp, ca, in
        """
    )

    # Endpoint configuration
    endpoint_group = parser.add_mutually_exclusive_group(required=False)
    endpoint_group.add_argument(
        '--region',
        choices=['us1', 'us2', 'eu', 'au', 'de', 'jp', 'ca', 'in'],
        help='Sumo Logic region code'
    )
    endpoint_group.add_argument(
        '--endpoint',
        help='Full API endpoint URL'
    )

    # Authentication
    parser.add_argument(
        '--access-id',
        help='Sumo Logic access ID (or set SUMO_ACCESS_ID env var)'
    )
    parser.add_argument(
        '--access-key',
        help='Sumo Logic access key (or set SUMO_ACCESS_KEY env var)'
    )

    # Batch mode
    parser.add_argument(
        '--batch-file',
        help='Path to YAML file containing batch queries (enables batch mode)'
    )

    # Query parameters (not required in batch mode)
    parser.add_argument(
        '--query',
        help='Log search query (not required with --batch-file)'
    )
    parser.add_argument(
        '--from-time',
        '--from',
        dest='from_time',
        help='Start time (relative like "-1h", ISO format, or epoch ms)'
    )
    parser.add_argument(
        '--to-time',
        '--to',
        dest='to_time',
        help='End time (relative like "now", ISO format, or epoch ms)'
    )
    parser.add_argument(
        '--timezone',
        default='UTC',
        help='Time zone for the query (default: UTC)'
    )
    parser.add_argument(
        '--by-view',
        action='store_true',
        help='Use estimatedUsageByView endpoint for partition/view breakdown'
    )

    # Output options
    parser.add_argument(
        '--output',
        choices=['json', 'table', 'summary', 'webview'],
        default='summary',
        help='Output format (default: summary). webview generates HTML report.'
    )
    parser.add_argument(
        '--output-file',
        help='Output file path (for webview or batch results)'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='INFO',
        help='Set the logging level (default: INFO)'
    )

    args = parser.parse_args()

    # Set up logging
    setup_logging(args.log_level)

    # Resolve authentication from args or environment
    access_id = args.access_id or os.environ.get('SUMO_ACCESS_ID')
    access_key = args.access_key or os.environ.get('SUMO_ACCESS_KEY')
    endpoint = args.region or args.endpoint or os.environ.get('SUMO_ENDPOINT')

    if not access_id:
        logger.error("Access ID is required. Use --access-id or set SUMO_ACCESS_ID environment variable")
        sys.exit(1)
    if not access_key:
        logger.error("Access key is required. Use --access-key or set SUMO_ACCESS_KEY environment variable")
        sys.exit(1)
    if not endpoint:
        logger.error("Endpoint is required. Use --region, --endpoint, or set SUMO_ENDPOINT environment variable")
        sys.exit(1)

    # Create client
    client = SumoLogicClient(endpoint, access_id, access_key)

    # Check if batch mode
    if args.batch_file:
        # Batch mode
        config = load_yaml_config(args.batch_file)
        validate_batch_config(config)

        batch_results = execute_batch(client, config, args)

        # Output batch results
        if args.output == 'webview':
            html = generate_html_report(batch_results, config)
            if args.output_file:
                with open(args.output_file, 'w') as f:
                    f.write(html)
                print(f"HTML report generated: {args.output_file}")
            else:
                print(html)
        elif args.output == 'json':
            output = json.dumps(batch_results, indent=2)
            if args.output_file:
                with open(args.output_file, 'w') as f:
                    f.write(output)
                print(f"JSON output written to: {args.output_file}")
            else:
                print(output)
        else:
            # Table/summary format for batch
            print(f"\n=== Batch Estimated Usage Report ===")
            print(f"Total queries: {len(batch_results)}")

            total_bytes = sum(r.get('total_bytes', 0) for r in batch_results if r.get('success'))
            print(f"Total estimated scan: {format_bytes(total_bytes)}\n")

            for idx, result in enumerate(batch_results):
                if result.get('success'):
                    print(f"{idx+1}. {result['name']}: {format_bytes(result['total_bytes'])}")
                    if args.output == 'table' and result.get('breakdown'):
                        for view in result['breakdown']:
                            print(f"   - {view['view_name']} ({view['tier']}): {view['bytes_formatted']}")
                else:
                    print(f"{idx+1}. {result['name']}: ERROR - {result.get('error', 'Unknown error')}")

    else:
        # Single query mode
        if not args.query or not args.from_time or not args.to_time:
            logger.error("--query, --from-time, and --to-time are required (or use --batch-file)")
            sys.exit(1)

        # Parse time values
        try:
            from_time_ms = parse_time_value(args.from_time)
            to_time_ms = parse_time_value(args.to_time)
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)

        logger.debug(f"Query: {args.query}")
        logger.debug(f"From: {datetime.fromtimestamp(from_time_ms/1000)} ({from_time_ms})")
        logger.debug(f"To: {datetime.fromtimestamp(to_time_ms/1000)} ({to_time_ms})")
        logger.debug(f"Timezone: {args.timezone}")

        try:
            result = client.get_estimated_usage(
                query=args.query,
                from_time=from_time_ms,
                to_time=to_time_ms,
                time_zone=args.timezone,
                by_view=args.by_view
            )

            # Output results
            if args.output == 'json':
                print(json.dumps(result, indent=2))
            elif args.output == 'webview':
                # Convert single query result to batch format for webview
                single_result = execute_single_estimation(
                    client=client,
                    query=args.query,
                    from_time_ms=from_time_ms,
                    to_time_ms=to_time_ms,
                    timezone=args.timezone,
                    by_view=args.by_view,
                    query_name=args.query
                )

                # Create minimal config for HTML report
                batch_config = {
                    'description': 'Single Query Estimation',
                    'queries': []
                }

                html_content = generate_html_report([single_result], batch_config)

                output_path = args.output_file if args.output_file else 'usage_report.html'
                with open(output_path, 'w') as f:
                    f.write(html_content)

                print(f"HTML report generated: {output_path}")
                print(f"Total estimated data to scan: {format_bytes(single_result['total_bytes'])}")
            elif args.output == 'table':
                print("\n=== Estimated Usage ===")
                print(f"Query: {args.query}")
                print(f"Time Range: {datetime.fromtimestamp(from_time_ms/1000)} to {datetime.fromtimestamp(to_time_ms/1000)}")
                print(f"Time Zone: {args.timezone}")
                print(f"Breakdown By View: {'Yes' if args.by_view else 'No'}")
                print("\nResults:")

                # Extract estimated usage details - handle both response structures
                usage_details = result.get('estimatedUsageDetails', {})

                if isinstance(usage_details, list):
                    # By-view endpoint returns a list of views
                    total_bytes = 0
                    for view in usage_details:
                        view_name = view.get('viewName', 'Unknown')
                        view_usage_details = view.get('usageDetails', [])
                        for detail in view_usage_details:
                            total_bytes += detail.get('dataScannedInBytes', 0)

                    print(f"  Total Estimated Data to Scan: {format_bytes(total_bytes)} ({total_bytes:,} bytes)")
                    print(f"  Run by Receipt Time: {result.get('runByReceiptTime', 'N/A')}")
                    print(f"  Interval Time Type: {result.get('intervalTimeType', 'N/A')}")

                    print("\n  Breakdown by View/Partition:")
                    for view in usage_details:
                        view_name = view.get('viewName', 'Unknown')
                        # Default partition is often reported as empty string
                        if not view_name or view_name.strip() == '':
                            view_name = 'sumologic_default'
                        view_usage_details = view.get('usageDetails', [])
                        for detail in view_usage_details:
                            view_bytes = detail.get('dataScannedInBytes', 0)
                            tier = detail.get('tier', 'Unknown')
                            metering_type = detail.get('meteringType', 'Unknown')
                            print(f"    - {view_name} ({tier}/{metering_type}): {format_bytes(view_bytes)} ({view_bytes:,} bytes)")
                else:
                    # Standard endpoint returns a dict
                    data_scanned_bytes = usage_details.get('dataScannedInBytes', 0)
                    print(f"  Estimated Data to Scan: {format_bytes(data_scanned_bytes)} ({data_scanned_bytes:,} bytes)")
                    print(f"  Run by Receipt Time: {result.get('runByReceiptTime', 'N/A')}")
                    print(f"  Parsing Mode: {result.get('parsingMode', 'N/A')}")
                    print(f"  Interval Time Type: {result.get('intervalTimeType', 'N/A')}")
            else:  # summary
                # Extract key metrics from estimatedUsageDetails - handle both structures
                usage_details = result.get('estimatedUsageDetails', {})

                if isinstance(usage_details, list):
                    # By-view endpoint
                    total_bytes = 0
                    for view in usage_details:
                        view_usage_details = view.get('usageDetails', [])
                        for detail in view_usage_details:
                            total_bytes += detail.get('dataScannedInBytes', 0)

                    print(f"Estimated data to scan: {format_bytes(total_bytes)}")

                    if len(usage_details) > 0:
                        print("\nBreakdown by view/partition:")
                        for view in usage_details:
                            view_name = view.get('viewName', 'Unknown')
                            # Default partition is often reported as empty string
                            if not view_name or view_name.strip() == '':
                                view_name = 'sumologic_default'
                            view_total = 0
                            for detail in view.get('usageDetails', []):
                                view_total += detail.get('dataScannedInBytes', 0)
                            print(f"  {view_name}: {format_bytes(view_total)}")
                else:
                    # Standard endpoint
                    data_scanned_bytes = usage_details.get('dataScannedInBytes', 0)
                    print(f"Estimated data to scan: {format_bytes(data_scanned_bytes)}")

        except KeyboardInterrupt:
            logger.info("\nOperation cancelled by user")
            sys.exit(1)


if __name__ == '__main__':
    main()
