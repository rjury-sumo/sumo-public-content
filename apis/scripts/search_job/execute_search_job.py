#!/usr/bin/env python3
"""
Sumo Logic Search Job Executor

This script executes search jobs using YAML configuration files.
Supports creating search jobs and optionally polling for completion
with different output modes for messages or records.
"""

import argparse
import base64
import csv
import io
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlencode
from urllib.request import Request, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError, URLError

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required but not installed.", file=sys.stderr)
    print("Please install it with: pip install PyYAML", file=sys.stderr)
    sys.exit(1)

# Set up logger
logger = logging.getLogger(__name__)


def setup_logging(log_level='INFO'):
    """Configure logging with appropriate level and format"""
    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')

    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Set up console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)

    # Configure logger
    logger.setLevel(numeric_level)
    logger.addHandler(console_handler)

    # Prevent duplicate logs
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

        # Set up cookie handling for search job API
        self.cookie_jar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookie_jar))

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
        """Make HTTP request to Sumo Logic API with cookie support"""
        url = urljoin(self.endpoint, path)

        if params and method == 'GET':
            url += '?' + urlencode(params)

        request = Request(url, method=method)
        request.add_header('Authorization', self.auth_header)
        request.add_header('Content-Type', 'application/json')
        request.add_header('Accept', 'application/json')

        if data:
            json_data = json.dumps(data, indent=2)
            logger.debug(f"Request body: {json_data}")
            request.data = json_data.encode()

        try:
            # Use the opener with cookie support for all requests
            response = self.opener.open(request)
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

    def create_search_job(self, query, from_time, to_time, time_zone='UTC', by_receipt_time=False, requires_raw_messages=False):
        """
        Create a search job

        Args:
            query (str): Search query
            from_time (str): Start time (ISO format or epoch ms)
            to_time (str): End time (ISO format or epoch ms)
            time_zone (str): Time zone for the search
            by_receipt_time (bool): Whether to search by receipt time
            requires_raw_messages (bool): Whether to require raw messages (defaults to False for better performance)

        Returns:
            dict: Search job response containing job ID
        """
        search_job_data = {
            'query': query,
            'from': from_time,
            'to': to_time,
            'timeZone': time_zone,
            'byReceiptTime': by_receipt_time,
            'requiresRawMessages': requires_raw_messages
        }

        return self._make_request('/api/v1/search/jobs', method='POST', data=search_job_data)

    def get_search_job_status(self, job_id):
        """
        Get search job status

        Args:
            job_id (str): Search job ID

        Returns:
            dict: Job status information
        """
        return self._make_request(f'/api/v1/search/jobs/{job_id}')

    def get_search_job_messages(self, job_id, offset=0, limit=10000):
        """
        Get messages from a completed search job

        Args:
            job_id (str): Search job ID
            offset (int): Starting offset for results
            limit (int): Maximum number of results to return (max 10000 or 100MB)

        Returns:
            dict: Messages from the search job
        """
        params = {
            'offset': offset,
            'limit': limit
        }
        return self._make_request(f'/api/v1/search/jobs/{job_id}/messages', params=params)

    def get_all_messages_paginated(self, job_id, page_size=10000):
        """
        Get all messages from a completed search job with pagination

        Args:
            job_id (str): Search job ID
            page_size (int): Number of messages per page (max 10000)

        Yields:
            dict: Each message from the search job
        """
        offset = 0
        while True:
            response = self.get_search_job_messages(job_id, offset=offset, limit=page_size)
            messages = response.get('messages', [])

            if not messages:
                break

            for message in messages:
                yield message

            # Check if we've reached the end
            total_count = response.get('totalCount', 0)
            offset += len(messages)

            if offset >= total_count:
                break

    def get_search_job_records(self, job_id, offset=0, limit=10000):
        """
        Get aggregate records from a completed search job

        Args:
            job_id (str): Search job ID
            offset (int): Starting offset for results
            limit (int): Maximum number of results to return

        Returns:
            dict: Records from the search job
        """
        params = {
            'offset': offset,
            'limit': limit
        }
        return self._make_request(f'/api/v1/search/jobs/{job_id}/records', params=params)

    def poll_search_job(self, job_id, poll_interval=5, max_wait=300):
        """
        Poll search job until completion

        Args:
            job_id (str): Search job ID
            poll_interval (int): Seconds between polls
            max_wait (int): Maximum seconds to wait

        Returns:
            dict: Final job status
        """
        start_time = time.time()

        while True:
            status = self.get_search_job_status(job_id)
            state = status.get('state', 'UNKNOWN')

            logger.debug(f"Job {job_id} status: {state}")

            if state in ['DONE GATHERING RESULTS', 'CANCELLED', 'FORCE PAUSED']:
                return status

            if time.time() - start_time > max_wait:
                logger.warning(f"Timeout waiting for job {job_id} to complete")
                return status

            time.sleep(poll_interval)


def load_yaml_config(yaml_file):
    """Load search job configuration from YAML file"""
    try:
        with open(yaml_file, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"YAML file '{yaml_file}' not found")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file: {e}")
        sys.exit(1)


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


def validate_config(config):
    """Validate required fields in configuration"""
    required_fields = ['name', 'query', 'from', 'to']
    missing_fields = [field for field in required_fields if field not in config]

    if missing_fields:
        logger.error(f"Missing required fields in YAML config: {', '.join(missing_fields)}")
        sys.exit(1)

    # Validate name is a valid string for use in filenames
    name = config['name']
    if not isinstance(name, str) or not name.strip():
        logger.error("Config 'name' must be a non-empty string")
        sys.exit(1)


def format_records_table(results):
    """Format records as a table"""
    if 'records' not in results or not results['records']:
        return "No records found"

    # Extract field names from the fields array
    fields_info = results.get('fields', [])
    if fields_info:
        # Use the order from fields array
        field_names = [field['name'] for field in fields_info]
    else:
        # Fallback: extract from first record
        first_record = results['records'][0]
        field_names = list(first_record.get('map', {}).keys())

    if not field_names:
        return "No fields found in records"

    # Calculate column widths
    col_widths = {}
    for field_name in field_names:
        col_widths[field_name] = len(field_name)  # Start with header width

    # Check all record values to determine max width
    for record in results['records']:
        record_map = record.get('map', {})
        for field_name in field_names:
            value = str(record_map.get(field_name, ''))
            col_widths[field_name] = max(col_widths[field_name], len(value))

    # Create header line
    header_parts = []
    separator_parts = []
    for field_name in field_names:
        width = col_widths[field_name]
        header_parts.append(f"{field_name:<{width}}")
        separator_parts.append("-" * width)

    output_lines = []
    output_lines.append(" | ".join(header_parts))
    output_lines.append("-+-".join(separator_parts))

    # Add data rows
    for record in results['records']:
        record_map = record.get('map', {})
        row_parts = []
        for field_name in field_names:
            value = str(record_map.get(field_name, ''))
            width = col_widths[field_name]
            row_parts.append(f"{value:<{width}}")
        output_lines.append(" | ".join(row_parts))

    return "\n".join(output_lines)


def format_records_csv(results):
    """Format records as CSV"""
    if 'records' not in results or not results['records']:
        return ""

    # Extract field names from the fields array
    fields_info = results.get('fields', [])
    if fields_info:
        # Use the order from fields array
        field_names = [field['name'] for field in fields_info]
    else:
        # Fallback: extract from first record
        first_record = results['records'][0]
        field_names = list(first_record.get('map', {}).keys())

    if not field_names:
        return ""

    # Create CSV output
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow(field_names)

    # Write data rows
    for record in results['records']:
        record_map = record.get('map', {})
        row = [record_map.get(field_name, '') for field_name in field_names]
        writer.writerow(row)

    return output.getvalue().strip()


def write_output(content, output_file=None, output_directory=None):
    """Write content to file or STDOUT"""
    if output_file:
        # If output_file is just a filename (no path), use output_directory
        if output_directory and not os.path.dirname(output_file):
            # Join output_directory with filename
            full_path = os.path.join(output_directory, output_file)
        elif output_directory and not os.path.isabs(output_file):
            # If output_file is relative and output_directory is specified, join them
            full_path = os.path.join(output_directory, output_file)
        else:
            # Use output_file as-is (absolute path or no output_directory)
            full_path = output_file

        try:
            # Create directory if it doesn't exist
            output_dir = os.path.dirname(full_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
                logger.debug(f"Created directory: {output_dir}")

            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Output written to: {full_path}")
        except IOError as e:
            logger.error(f"Error writing to file {full_path}: {e}")
            sys.exit(1)
    else:
        print(content)


def parse_interval_to_milliseconds(interval_str):
    """
    Parse interval string to milliseconds

    Args:
        interval_str (str): Interval like "1h", "30m", "2d"

    Returns:
        int: Interval in milliseconds
    """
    interval_pattern = r'^(\d+)([smhdw])$'
    match = re.match(interval_pattern, interval_str.lower())

    if not match:
        raise ValueError(f"Invalid interval format: {interval_str}. Use format like '1h', '30m', '2d'")

    amount, unit = match.groups()
    amount = int(amount)

    unit_to_ms = {
        's': 1000,
        'm': 60 * 1000,
        'h': 60 * 60 * 1000,
        'd': 24 * 60 * 60 * 1000,
        'w': 7 * 24 * 60 * 60 * 1000
    }

    return amount * unit_to_ms[unit]


def generate_batch_intervals(start_time_ms, end_time_ms, interval_ms):
    """
    Generate time intervals for batch processing

    Args:
        start_time_ms (int): Start time in epoch milliseconds
        end_time_ms (int): End time in epoch milliseconds
        interval_ms (int): Interval in milliseconds

    Returns:
        list: List of (from_time, to_time) tuples
    """
    intervals = []
    current_start = start_time_ms

    while current_start < end_time_ms:
        current_end = min(current_start + interval_ms, end_time_ms)
        intervals.append((current_start, current_end))
        current_start = current_end

    return intervals


def analyze_time_buckets(client, query, start_time_ms, end_time_ms, time_zone, by_receipt_time,
                         initial_bucket_size_ms, max_events_per_bucket=100000):
    """
    Analyze time range and generate optimal buckets where each has < max_events_per_bucket events

    This function runs a timeslice query to count events in each time bucket, then recursively
    subdivides buckets that exceed the max_events_per_bucket threshold.

    Args:
        client: SumoLogicClient instance
        query (str): Base query scope (without aggregation operators)
        start_time_ms (int): Start time in epoch milliseconds
        end_time_ms (int): End time in epoch milliseconds
        time_zone (str): Time zone for the search
        by_receipt_time (bool): Whether to search by receipt time
        initial_bucket_size_ms (int): Initial bucket size in milliseconds
        max_events_per_bucket (int): Maximum events per bucket (default 100000)

    Returns:
        list: List of (from_time, to_time, estimated_count) tuples representing optimal buckets
              estimated_count may be None for gap-filling buckets or subdivided buckets
    """
    logger.info(f"Analyzing time range for adaptive bucketing (target: <{max_events_per_bucket} events/bucket)")

    # Build timeslice query to count events
    bucket_size_seconds = initial_bucket_size_ms // 1000
    count_query = f"{query} | timeslice {bucket_size_seconds}s | count by _timeslice"

    logger.debug(f"Running count query: {count_query}")

    # Create and execute count query job
    job_response = client.create_search_job(
        query=count_query,
        from_time=start_time_ms,
        to_time=end_time_ms,
        time_zone=time_zone,
        by_receipt_time=by_receipt_time,
        requires_raw_messages=False
    )

    job_id = job_response.get('id')
    if not job_id:
        raise RuntimeError("Failed to create count query job")

    logger.debug(f"Count query job created: {job_id}")

    # Poll for completion
    final_status = client.poll_search_job(job_id, poll_interval=2, max_wait=300)

    if final_status.get('state') != 'DONE GATHERING RESULTS':
        raise RuntimeError(f"Count query failed with state: {final_status.get('state')}")

    # Get results
    results = client.get_search_job_records(job_id)
    records = results.get('records', [])

    logger.info(f"Count query returned {len(records)} time buckets")

    # Build list of buckets with their event counts
    bucket_counts = []
    for record in records:
        record_map = record.get('map', {})
        timeslice = record_map.get('_timeslice')
        count = int(record_map.get('_count', 0))

        if timeslice:
            # Parse timeslice timestamp
            try:
                # Timeslice format is typically ISO-8601
                bucket_start = parse_time_value(timeslice)
                bucket_end = bucket_start + initial_bucket_size_ms
                bucket_counts.append((bucket_start, bucket_end, count))
            except Exception as e:
                logger.warning(f"Failed to parse timeslice '{timeslice}': {e}")

    # Sort by start time
    bucket_counts.sort(key=lambda x: x[0])

    # Recursively subdivide buckets that exceed the threshold
    final_buckets = []

    for bucket_start, bucket_end, count in bucket_counts:
        if count <= max_events_per_bucket:
            # Bucket is within limits
            final_buckets.append((bucket_start, bucket_end, count))
            logger.debug(f"Bucket {datetime.fromtimestamp(bucket_start/1000)} - {datetime.fromtimestamp(bucket_end/1000)}: {count} events (OK)")
        else:
            # Bucket needs subdivision
            logger.debug(f"Bucket {datetime.fromtimestamp(bucket_start/1000)} - {datetime.fromtimestamp(bucket_end/1000)}: {count} events (exceeds limit, subdividing)")

            # Calculate subdivision size (half the original bucket)
            subdivision_size_ms = (bucket_end - bucket_start) // 2

            # Recursively subdivide
            sub_buckets = analyze_time_buckets(
                client, query, bucket_start, bucket_end, time_zone, by_receipt_time,
                subdivision_size_ms, max_events_per_bucket
            )
            final_buckets.extend(sub_buckets)

    # Handle any gaps in coverage
    if not final_buckets:
        # No data found, return single bucket for entire range
        logger.warning(f"No events found in time range, returning single bucket")
        return [(start_time_ms, end_time_ms, None)]

    # Fill gaps at beginning and end (with None for estimated count)
    if final_buckets[0][0] > start_time_ms:
        final_buckets.insert(0, (start_time_ms, final_buckets[0][0], None))

    if final_buckets[-1][1] < end_time_ms:
        final_buckets.append((final_buckets[-1][1], end_time_ms, None))

    logger.info(f"Adaptive bucketing complete: {len(final_buckets)} optimal buckets generated")
    return final_buckets


def format_batch_filename(base_filename, batch_index, from_time_ms, to_time_ms):
    """
    Generate filename for batch output

    Args:
        base_filename (str): Base filename or None for STDOUT
        batch_index (int): Index of the batch (0-based)
        from_time_ms (int): Start time in milliseconds
        to_time_ms (int): End time in milliseconds

    Returns:
        str or None: Formatted filename or None for STDOUT
    """
    if not base_filename:
        return None

    # Convert epoch milliseconds to formatted timestamp strings
    from_dt = datetime.fromtimestamp(from_time_ms / 1000)
    to_dt = datetime.fromtimestamp(to_time_ms / 1000)

    # Format as YYYYMMddHHmmss.SSS
    from_str = from_dt.strftime('%Y%m%d%H%M%S') + f".{from_time_ms % 1000:03d}"
    to_str = to_dt.strftime('%Y%m%d%H%M%S') + f".{to_time_ms % 1000:03d}"

    # Extract file extension if present
    if '.' in base_filename:
        name, ext = base_filename.rsplit('.', 1)
        return f"{name}_batch_{batch_index:03d}_{from_str}_{to_str}.{ext}"
    else:
        return f"{base_filename}_batch_{batch_index:03d}_{from_str}_{to_str}"


def execute_single_query(client, query, from_time, to_time, time_zone, by_receipt_time, args, query_name=None):
    """Execute a single search query"""
    # Set requiresRawMessages to True only when messages mode is used
    # This defaults to False for better performance with aggregate queries
    requires_raw_messages = args.mode == 'messages'

    # Create search job
    query_label = f"[{query_name}] " if query_name else ""
    logger.debug(f"{query_label}Creating search job with query: \n{query}")
    logger.debug(f"requiresRawMessages set to: {requires_raw_messages} (mode: {args.mode})")
    job_response = client.create_search_job(
        query=query,
        from_time=from_time,
        to_time=to_time,
        time_zone=time_zone,
        by_receipt_time=by_receipt_time,
        requires_raw_messages=requires_raw_messages
    )

    job_id = job_response.get('id')
    if not job_id:
        logger.error(f"{query_label}No job ID returned from search job creation")
        sys.exit(1)

    logger.debug(f"{query_label}Search job created with ID: {job_id}")

    if args.mode == 'create-only':
        # Just return the job creation response
        if args.output == 'jsonl':
            write_output(job_id, args.output_file, args.output_directory)
        else:
            write_output(json.dumps(job_response, indent=2), args.output_file, args.output_directory)

    elif args.mode in ['messages', 'records']:
        # Poll until completion
        logger.debug(f"{query_label}Polling job {job_id} for completion...")
        final_status = client.poll_search_job(job_id, args.poll_interval, args.max_wait)

        if final_status.get('state') == 'DONE GATHERING RESULTS':
            logger.info(f"{query_label}Job {job_id} completed successfully")

            if args.mode == 'messages':
                results = client.get_search_job_messages(job_id)
            else:  # records
                results = client.get_search_job_records(job_id)

            format_and_write_output(results, args)
        else:
            logger.error(f"{query_label}Job {job_id} did not complete successfully. Final state: {final_status.get('state')}")
            if args.output == 'json':
                write_output(json.dumps(final_status, indent=2), args.output_file, args.output_directory)
            sys.exit(1)


def format_time_estimate(seconds):
    """
    Format time estimate in human-readable format

    Args:
        seconds (float): Time in seconds

    Returns:
        str: Formatted time string
    """
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def print_progress_bar(current, total, start_time, bar_width=40):
    """
    Print a progress bar with time estimation

    Args:
        current (int): Current batch number (1-based)
        total (int): Total number of batches
        start_time (float): Start time from time.time()
        bar_width (int): Width of the progress bar in characters
    """
    # Calculate progress percentage
    progress = current / total
    filled_width = int(bar_width * progress)

    # Create progress bar
    bar = '█' * filled_width + '░' * (bar_width - filled_width)
    percentage = progress * 100

    # Calculate time estimates
    elapsed_time = time.time() - start_time
    if current > 0:
        avg_time_per_batch = elapsed_time / current
        remaining_batches = total - current
        estimated_remaining = avg_time_per_batch * remaining_batches
    else:
        estimated_remaining = 0

    # Format output
    elapsed_str = format_time_estimate(elapsed_time)
    remaining_str = format_time_estimate(estimated_remaining)

    # Print progress bar to stderr (so it doesn't interfere with stdout output)
    progress_msg = f"[{bar}] {percentage:.1f}% | Batch {current}/{total} | Elapsed: {elapsed_str} | ETA: {remaining_str} | Remaining: {total - current}\n"
    sys.stderr.write(progress_msg)
    sys.stderr.flush()


def execute_batch(client, query, intervals, time_zone, by_receipt_time, args, query_name=None):
    """Execute batch search queries"""
    total_intervals = len(intervals)
    query_label = f"[{query_name}] " if query_name else ""
    logger.info(f"{query_label}Starting batch execution of {total_intervals} intervals")

    # Track start time for progress estimation
    batch_start_time = time.time()

    # Set default output file if not specified and not using sumo-https
    output_file = args.output_file
    output_directory = args.output_directory

    if not output_file and args.output != 'sumo-https':
        # Generate default filename based on output format and query name
        extension_map = {
            'csv': 'csv',
            'json': 'json',
            'jsonl': 'jsonl',
            'table': 'txt'
        }
        extension = extension_map.get(args.output, 'jsonl')  # Default to jsonl if not found
        # Use query name and mode in filename if available
        base_name = query_name if query_name else "batch_results"
        output_file = f"{base_name}_{args.mode}.{extension}"
        # Note: output_directory is already set (either by user or default './output/')
        logger.debug(f"{query_label}No output file specified, using default: {output_file} in {output_directory}")

    for batch_index, interval in enumerate(intervals):
        # Unpack interval (may be 2-tuple or 3-tuple depending on caller)
        if len(interval) == 3:
            from_time, to_time, _ = interval  # Ignore count for execution
        else:
            from_time, to_time = interval

        logger.debug(f"{query_label}=== Batch {batch_index + 1}/{total_intervals} ===")
        logger.debug(f"{query_label}Time range: {datetime.fromtimestamp(from_time/1000)} to {datetime.fromtimestamp(to_time/1000)}")

        # Generate batch-specific filename
        batch_output_file = format_batch_filename(output_file, batch_index, from_time, to_time)

        # Create a copy of args with the batch-specific output file
        batch_args = argparse.Namespace(**vars(args))
        batch_args.output_file = batch_output_file
        batch_args.output_directory = output_directory

        try:
            # Execute the query for this time interval
            execute_single_query(client, query, from_time, to_time, time_zone, by_receipt_time, batch_args, query_name)
            logger.debug(f"{query_label}Batch {batch_index + 1} completed successfully")
        except Exception as e:
            logger.error(f"Batch {batch_index + 1} failed: {e}")
            # Continue with next batch instead of stopping

        # Update progress bar after each batch
        print_progress_bar(batch_index + 1, total_intervals, batch_start_time)

    logger.info(f"Batch processing completed. {total_intervals} intervals processed.")


def prompt_export_confirmation(intervals, query_name=None):
    """
    Display planned export time ranges and prompt for user confirmation

    Args:
        intervals (list): List of (from_time, to_time, estimated_count) tuples
                         estimated_count may be None for gap-filling buckets
        query_name (str): Optional query name

    Returns:
        bool: True if user confirms, False otherwise
    """
    query_label = f"[{query_name}] " if query_name else ""

    # Calculate total estimated messages
    total_estimated = sum(count if count else 0 for _, _, count in intervals)

    print(f"\n{query_label}=== Planned Export Time Ranges ===")
    print(f"Total buckets: {len(intervals)}")
    print(f"Estimated total messages: {total_estimated:,}\n")

    # Show first 10, last 10, or all if less than 20
    if len(intervals) <= 20:
        display_intervals = intervals
    else:
        display_intervals = intervals[:10] + [None] + intervals[-10:]

    for i, interval in enumerate(display_intervals):
        if interval is None:
            print(f"  ... ({len(intervals) - 20} more buckets) ...")
            continue

        from_time, to_time, count = interval
        from_dt = datetime.fromtimestamp(from_time / 1000)
        to_dt = datetime.fromtimestamp(to_time / 1000)
        duration = (to_time - from_time) / 1000 / 60  # minutes

        if i < 10 or len(intervals) <= 20:
            bucket_num = i
        else:
            bucket_num = len(intervals) - 20 + i

        # Format count display
        if count is not None:
            count_str = f"~{count:,} messages"
        else:
            count_str = "no data (gap)"

        print(f"  Bucket {bucket_num:3d}: {from_dt} to {to_dt} ({duration:6.1f}m) - {count_str}")

    print(f"\nTotal time range: {datetime.fromtimestamp(intervals[0][0]/1000)} to {datetime.fromtimestamp(intervals[-1][1]/1000)}")
    print(f"Total buckets: {len(intervals)}")
    print(f"Estimated total messages: {total_estimated:,}")

    response = input(f"\n{query_label}Proceed with export? (yes/no): ").strip().lower()
    return response in ['yes', 'y']


def generate_export_summary(total_intervals, total_messages, start_time, output_directory):
    """
    Generate a summary report of the export operation

    Args:
        total_intervals (int): Number of time intervals processed
        total_messages (int): Total messages exported
        start_time (float): Start time from time.time()
        output_directory (str): Output directory path

    Returns:
        str: Formatted summary report
    """
    elapsed_time = time.time() - start_time
    elapsed_str = format_time_estimate(elapsed_time)

    summary = []
    summary.append("\n" + "=" * 60)
    summary.append("BATCHED MESSAGES EXPORT SUMMARY")
    summary.append("=" * 60)
    summary.append(f"Total time buckets processed: {total_intervals}")
    summary.append(f"Total messages exported: {total_messages:,}")
    summary.append(f"Total execution time: {elapsed_str}")
    summary.append(f"Average messages per bucket: {total_messages // total_intervals if total_intervals > 0 else 0:,}")
    summary.append(f"Output directory: {output_directory}")

    if total_intervals > 0:
        avg_time_per_bucket = elapsed_time / total_intervals
        summary.append(f"Average time per bucket: {format_time_estimate(avg_time_per_bucket)}")

    summary.append("=" * 60 + "\n")

    return "\n".join(summary)


def execute_batched_messages_export(client, query, intervals, time_zone, by_receipt_time, args, query_name=None):
    """
    Execute batched raw messages export with pagination for each time bucket

    This function processes each time interval sequentially to avoid API concurrency limits,
    and paginates through messages within each interval to handle the 10k/page limit.

    Args:
        client: SumoLogicClient instance
        query (str): Search query
        intervals (list): List of (from_time, to_time) tuples
        time_zone (str): Time zone
        by_receipt_time (bool): Whether to use receipt time
        args: Command line arguments
        query_name (str): Optional query name for logging
    """
    total_intervals = len(intervals)
    query_label = f"[{query_name}] " if query_name else ""
    logger.info(f"{query_label}Starting batched messages export of {total_intervals} intervals")

    # Track start time for progress estimation
    batch_start_time = time.time()

    # Set default output file
    output_file = args.output_file
    output_directory = args.output_directory

    if not output_file:
        extension = 'json' if args.output == 'json' else 'jsonl'
        base_name = query_name if query_name else "batched_messages"
        output_file = f"{base_name}_messages.{extension}"
        logger.debug(f"{query_label}No output file specified, using default: {output_file} in {output_directory}")

    total_messages_exported = 0

    for batch_index, interval in enumerate(intervals):
        # Unpack interval (supports both 2-tuple and 3-tuple formats)
        if len(interval) == 3:
            from_time, to_time, estimated_count = interval
        else:
            from_time, to_time = interval
            estimated_count = None

        logger.info(f"{query_label}=== Batch {batch_index + 1}/{total_intervals} ===")
        logger.info(f"{query_label}Time range: {datetime.fromtimestamp(from_time/1000)} to {datetime.fromtimestamp(to_time/1000)}")
        if estimated_count:
            logger.info(f"{query_label}Estimated messages: {estimated_count:,}")

        try:
            # Create search job for this interval
            job_response = client.create_search_job(
                query=query,
                from_time=from_time,
                to_time=to_time,
                time_zone=time_zone,
                by_receipt_time=by_receipt_time,
                requires_raw_messages=True
            )

            job_id = job_response.get('id')
            if not job_id:
                logger.error(f"{query_label}No job ID returned for batch {batch_index + 1}")
                continue

            logger.debug(f"{query_label}Search job created: {job_id}")

            # Poll until completion
            final_status = client.poll_search_job(job_id, poll_interval=2, max_wait=300)

            if final_status.get('state') != 'DONE GATHERING RESULTS':
                logger.error(f"{query_label}Job {job_id} did not complete. State: {final_status.get('state')}")
                continue

            # Get message count
            message_count = final_status.get('messageCount', 0)
            logger.info(f"{query_label}Job completed with {message_count} messages")

            # Generate batch-specific filename
            batch_output_file = format_batch_filename(output_file, batch_index, from_time, to_time)

            # Paginate through messages and write to file
            batch_messages = 0
            output_lines = []

            for message in client.get_all_messages_paginated(job_id, page_size=10000):
                batch_messages += 1
                total_messages_exported += 1

                if args.output == 'jsonl':
                    output_lines.append(json.dumps(message))
                else:  # json
                    output_lines.append(message)

            # Write batch output
            if output_lines:
                if args.output == 'jsonl':
                    content = '\n'.join(output_lines)
                else:  # json
                    content = json.dumps({'messages': output_lines, 'count': len(output_lines)}, indent=2)

                write_output(content, batch_output_file, output_directory)
                logger.info(f"{query_label}Exported {batch_messages} messages to batch file")
            else:
                logger.warning(f"{query_label}No messages found in batch {batch_index + 1}")

        except Exception as e:
            logger.error(f"{query_label}Batch {batch_index + 1} failed: {e}")
            # Continue with next batch

        # Update progress bar
        print_progress_bar(batch_index + 1, total_intervals, batch_start_time)

    # Generate and print summary report
    summary_report = generate_export_summary(total_intervals, total_messages_exported, batch_start_time, output_directory)
    print(summary_report)
    logger.info(f"{query_label}Batched messages export completed. {total_messages_exported} total messages exported across {total_intervals} intervals.")


def post_to_sumo_https(records, sumo_url, add_timestamp=False):
    """Post records to Sumo Logic HTTPS endpoint"""
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError

    total_records = len(records)
    successful_posts = 0

    logger.info(f"Posting {total_records} records to Sumo Logic HTTPS endpoint")
    if add_timestamp:
        logger.debug("Adding timestamp to each record")

    for i, record in enumerate(records):
        try:
            # Extract the record data from the 'map' field
            record_data = record.get('map', {}).copy()  # Make a copy to avoid modifying original

            # Add timestamp if requested
            if add_timestamp:
                current_timestamp = int(time.time() * 1000)  # 13-digit epoch milliseconds
                record_data['timestamp'] = current_timestamp
                logger.debug(f"Added timestamp {current_timestamp} to record {i+1}")

            # Convert to JSON string for posting
            json_data = json.dumps(record_data)

            # Create the request
            request = Request(sumo_url, data=json_data.encode('utf-8'))
            request.add_header('Content-Type', 'application/json')

            # Post to Sumo Logic
            with urlopen(request) as response:
                if response.status == 200:
                    successful_posts += 1
                    logger.debug(f"Successfully posted record {i+1}/{total_records}")
                else:
                    logger.warning(f"Unexpected response code {response.status} for record {i+1}")

        except HTTPError as e:
            logger.error(f"HTTP error posting record {i+1}: {e.code} {e.reason}")
        except URLError as e:
            logger.error(f"URL error posting record {i+1}: {e.reason}")
        except Exception as e:
            logger.error(f"Unexpected error posting record {i+1}: {e}")

    logger.info(f"Posted {successful_posts}/{total_records} records successfully")
    return successful_posts


def format_and_write_output(results, args):
    """Format and write output based on args configuration"""
    # Handle different output formats
    if args.output == 'jsonl':
        # Output JSON Lines format - one JSON object per line
        output_lines = []
        if 'messages' in results:
            for message in results['messages']:
                output_lines.append(json.dumps(message))
        elif 'records' in results:
            for record in results['records']:
                output_lines.append(json.dumps(record))
        write_output('\n'.join(output_lines), args.output_file, args.output_directory)
    elif args.output == 'table':
        if args.mode == 'records' and 'records' in results:
            write_output(format_records_table(results), args.output_file, args.output_directory)
        else:
            logger.warning("Table format is only supported for records mode")
            write_output(json.dumps(results, indent=2), args.output_file, args.output_directory)
    elif args.output == 'csv':
        if args.mode == 'records' and 'records' in results:
            csv_output = format_records_csv(results)
            if csv_output:
                write_output(csv_output, args.output_file, args.output_directory)
            else:
                write_output("No records to format as CSV", args.output_file, args.output_directory)
        else:
            logger.warning("CSV format is only supported for records mode")
            write_output(json.dumps(results, indent=2), args.output_file, args.output_directory)
    elif args.output == 'sumo-https':
        if args.mode == 'records' and 'records' in results:
            records = results.get('records', [])
            if records:
                add_timestamp = args.sumo_timestamp == 'add'
                successful = post_to_sumo_https(records, args.sumo_https_url, add_timestamp)
                logger.info(f"Sumo HTTPS posting completed: {successful}/{len(records)} records posted")
            else:
                logger.warning("No records found to post to Sumo Logic")
        else:
            logger.error("sumo-https output is only supported with records mode")
    else:  # json format
        write_output(json.dumps(results, indent=2), args.output_file, args.output_directory)


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Execute search jobs from YAML configuration files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Execution Modes:
  create-only    : Create the search job and return job ID (requiresRawMessages=False)
  messages       : Create job, poll until complete, return messages (requiresRawMessages=True)
  records        : Create job, poll until complete, return records (requiresRawMessages=False)

Output Formats:
  json           : Standard JSON output
  jsonl          : JSON Lines format - one JSON object per line (no metadata)
  table          : Formatted table (records mode only)
  csv            : Comma-separated values (records mode only)
  sumo-https     : POST each record to Sumo Logic HTTPS endpoint (records mode only)

YAML Configuration Format:
  query: "_sourceCategory=prod/app | count by _sourceHost"
  from: "-1h"  # or "2024-01-01T00:00:00Z" or 1704067200000
  to: "now"   # or "2024-01-01T01:00:00Z" or 1704070800000
  timeZone: "UTC"  # optional, defaults to UTC
  byReceiptTime: false  # optional, defaults to false

Time Format Options:
  - Relative times: "-1h", "-30m", "-2d", "-1w", "now"
  - ISO format: "2024-01-01T00:00:00Z"
  - Epoch milliseconds: 1704067200000

Examples:
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY --yaml-config search.yaml --mode create-only
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY --yaml-config search.yaml --mode records --output table
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY --yaml-config search.yaml --mode records --output csv --output-file results.csv
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY --yaml-config search.yaml --mode messages --output json --output-file messages.json --output-directory /tmp/logs/
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY --yaml-config search.yaml --mode records --output sumo-https --sumo-https-url https://endpoint1.collection.us1.sumologic.com/receiver/v1/http/YOUR_SOURCE_TOKEN --sumo-timestamp add

Batch Mode Examples:
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY --yaml-config search.yaml --batch-mode --batch-start "-24h" --batch-end "now" --batch-interval "1h" --mode records --output csv --output-file hourly_data.csv
  %(prog)s --region us1 --access-id YOUR_ID --access-key YOUR_KEY --yaml-config search.yaml --batch-mode --batch-start "2024-01-01T00:00:00Z" --batch-end "2024-01-02T00:00:00Z" --batch-interval "6h" --mode records --output table

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
        '--yaml-config',
        required=True,
        help='Path to YAML configuration file'
    )
    parser.add_argument(
        '--mode',
        choices=['create-only', 'messages', 'records'],
        default='create-only',
        help='Execution mode (default: create-only)'
    )
    parser.add_argument(
        '--poll-interval',
        type=int,
        default=5,
        help='Polling interval in seconds (default: 5)'
    )
    parser.add_argument(
        '--max-wait',
        type=int,
        default=300,
        help='Maximum wait time in seconds (default: 300)'
    )
    parser.add_argument(
        '--output',
        choices=['json', 'jsonl', 'table', 'csv', 'sumo-https'],
        default=None,
        help='Output format. Default: jsonl for records mode, json for messages/create-only modes. jsonl outputs JSON Lines format. table/csv formats work best with records mode. sumo-https posts records to Sumo Logic HTTPS endpoint.'
    )
    parser.add_argument(
        '--output-file',
        help='File path to write output to. If not specified, output goes to STDOUT.'
    )
    parser.add_argument(
        '--output-directory',
        default='./output/',
        help='Directory to write output files to when --output-file is used (default: ./output/)'
    )
    parser.add_argument(
        '--batch-mode',
        action='store_true',
        help='Enable batch mode to execute query across multiple time intervals'
    )
    parser.add_argument(
        '--batch-start',
        help='Start time for batch processing (overrides YAML from time). Supports same formats as from/to.'
    )
    parser.add_argument(
        '--batch-end',
        help='End time for batch processing (overrides YAML to time). Supports same formats as from/to.'
    )
    parser.add_argument(
        '--batch-interval',
        default='1h',
        help='Time interval for each batch query (e.g., "1h", "30m", "2d"). Default: 1h'
    )
    parser.add_argument(
        '--batch-messages-export',
        action='store_true',
        help='Enable adaptive batched messages export mode. Analyzes time range to create optimal buckets (<100k events each), then exports raw messages with pagination.'
    )
    parser.add_argument(
        '--max-events-per-bucket',
        type=int,
        default=100000,
        help='Maximum events per time bucket for batched messages export (default: 100000)'
    )
    parser.add_argument(
        '--confirm-export',
        action='store_true',
        help='Prompt for confirmation before starting batched export, showing planned time ranges'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='INFO',
        help='Set the logging level (default: INFO)'
    )
    parser.add_argument(
        '--sumo-https-url',
        help='Sumo Logic HTTPS collector endpoint URL (required when using --output sumo-https)'
    )
    parser.add_argument(
        '--sumo-timestamp',
        choices=['none', 'add'],
        default='none',
        help='Add timestamp to records when using sumo-https output. "add" adds current timestamp as 13-digit epoch milliseconds (default: none)'
    )

    args = parser.parse_args()

    # Set default output format based on mode
    if args.output is None:
        if args.mode == 'records':
            args.output = 'jsonl'
        else:
            args.output = 'json'

    # Set up logging
    setup_logging(args.log_level)

    # Load and validate YAML configuration
    config = load_yaml_config(args.yaml_config)
    validate_config(config)

    # Validate batch mode parameters
    if args.batch_mode:
        if not args.batch_start:
            logger.error("--batch-start is required when using --batch-mode")
            sys.exit(1)
        if not args.batch_end:
            logger.error("--batch-end is required when using --batch-mode")
            sys.exit(1)
        if args.mode == 'create-only':
            logger.error("--batch-mode is not compatible with --mode create-only")
            sys.exit(1)

    # Validate batched messages export parameters
    if args.batch_messages_export:
        if not args.batch_start:
            logger.error("--batch-start is required when using --batch-messages-export")
            sys.exit(1)
        if not args.batch_end:
            logger.error("--batch-end is required when using --batch-messages-export")
            sys.exit(1)
        if args.mode != 'messages':
            logger.warning("--batch-messages-export works best with --mode messages, forcing mode to messages")
            args.mode = 'messages'
        if args.output not in ['json', 'jsonl']:
            logger.error("--batch-messages-export only supports --output json or jsonl")
            sys.exit(1)

    # Validate messages mode output format
    if args.mode == 'messages':
        if args.output not in ['json', 'jsonl']:
            logger.error("--mode messages only supports --output json or jsonl")
            sys.exit(1)

    # Validate sumo-https output mode
    if args.output == 'sumo-https':
        if args.mode != 'records':
            logger.error("--output sumo-https is only supported with --mode records")
            sys.exit(1)
        if not args.sumo_https_url:
            logger.error("--sumo-https-url is required when using --output sumo-https")
            sys.exit(1)
        if not args.sumo_https_url.startswith('https://'):
            logger.error("--sumo-https-url must be a valid HTTPS URL")
            sys.exit(1)

    # Determine endpoint
    endpoint = args.region if args.region else args.endpoint

    # Create client
    client = SumoLogicClient(endpoint, args.access_id, args.access_key)

    try:
        # Extract search parameters from config
        query = config['query']
        query_name = config['name']
        time_zone = config.get('timeZone', 'UTC')
        by_receipt_time = config.get('byReceiptTime', False)

        if args.batch_messages_export:
            # Adaptive batched messages export mode
            batch_start_time = parse_time_value(args.batch_start)
            batch_end_time = parse_time_value(args.batch_end)
            interval_ms = parse_interval_to_milliseconds(args.batch_interval)

            logger.info(f"Batched messages export mode: {datetime.fromtimestamp(batch_start_time/1000)} to {datetime.fromtimestamp(batch_end_time/1000)}")
            logger.info(f"Initial bucket size: {args.batch_interval} ({interval_ms}ms)")
            logger.info(f"Max events per bucket: {args.max_events_per_bucket}")

            # Analyze time range and generate optimal buckets
            intervals = analyze_time_buckets(
                client, query, batch_start_time, batch_end_time, time_zone, by_receipt_time,
                interval_ms, args.max_events_per_bucket
            )

            # Prompt for confirmation if requested
            if args.confirm_export:
                if not prompt_export_confirmation(intervals, query_name):
                    logger.info("Export cancelled by user")
                    sys.exit(0)

            # Execute batched messages export
            execute_batched_messages_export(client, query, intervals, time_zone, by_receipt_time, args, query_name)

        elif args.batch_mode:
            # Use batch start/end times
            batch_start_time = parse_time_value(args.batch_start)
            batch_end_time = parse_time_value(args.batch_end)
            interval_ms = parse_interval_to_milliseconds(args.batch_interval)

            logger.info(f"Batch mode: {datetime.fromtimestamp(batch_start_time/1000)} to {datetime.fromtimestamp(batch_end_time/1000)}")
            logger.info(f"Batch interval: {args.batch_interval} ({interval_ms}ms)")

            # Generate batch intervals
            intervals = generate_batch_intervals(batch_start_time, batch_end_time, interval_ms)
            logger.info(f"Generated {len(intervals)} batch intervals")

            # Execute batch processing
            execute_batch(client, query, intervals, time_zone, by_receipt_time, args, query_name)

        else:
            # Single query mode
            from_time = parse_time_value(config['from'])
            to_time = parse_time_value(config['to'])

            logger.info(f"Single query: {datetime.fromtimestamp(from_time/1000)} to {datetime.fromtimestamp(to_time/1000)}")

            # Set default output file if not specified and not using sumo-https or create-only
            if not args.output_file and args.output != 'sumo-https' and args.mode != 'create-only':
                # Generate default filename based on output format, query name, and mode
                extension_map = {
                    'csv': 'csv',
                    'json': 'json',
                    'jsonl': 'jsonl',
                    'table': 'txt'
                }
                extension = extension_map.get(args.output, 'jsonl')  # Default to jsonl if not found
                args.output_file = f"{query_name}_{args.mode}.{extension}"
                # Note: args.output_directory is already set (either by user or default './output/')
                logger.debug(f"[{query_name}] No output file specified, using default: {args.output_file} in {args.output_directory}")

            # Execute single query
            execute_single_query(client, query, from_time, to_time, time_zone, by_receipt_time, args, query_name)

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(1)


if __name__ == '__main__':
    main()