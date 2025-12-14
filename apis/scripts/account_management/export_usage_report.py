#!/usr/bin/env python3
"""
Sumo Logic Usage Report Export API Client

This script exports usage report data from the Sumo Logic API.
It starts an export job, polls for completion, and downloads the CSV result.

API Reference: https://api.us2.sumologic.com/docs/#operation/exportUsageReport
Export Endpoint: POST /api/v1/account/usage/report
Status Endpoint: GET /api/v1/account/usage/report/{jobId}/status

The process:
1. POST to start export with startDate and endDate
2. Poll job status until complete
3. Download CSV from S3 presigned URL (valid for 10 minutes)

Returns:
- CSV file with usage report data
"""

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime
from urllib.parse import urljoin
from urllib.request import Request, urlopen, urlretrieve
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
            print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
            print(f"Error details: {error_body}", file=sys.stderr)
            sys.exit(1)
        except URLError as e:
            print(f"URL Error: {e.reason}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            sys.exit(1)

    def start_usage_export(self, start_date=None, end_date=None, group_by='day',
                          report_type='standard', include_deployment_charge=False):
        """
        Start usage report export job

        Args:
            start_date (str, optional): Start date in ISO format (YYYY-MM-DD).
                                       Defaults to start of subscription if not provided.
            end_date (str, optional): End date in ISO format (YYYY-MM-DD).
                                     Defaults to end of subscription if not provided.
            group_by (str): Grouping period - 'day', 'week', or 'month' (default: 'day')
            report_type (str): Report type - 'standard', 'detailed', or 'childDetailed' (default: 'standard')
            include_deployment_charge (bool): Include deployment charges for child orgs (default: False)

        Returns:
            dict: Response containing jobId
        """
        data = {
            'groupBy': group_by,
            'reportType': report_type,
            'includeDeploymentCharge': include_deployment_charge
        }

        # Only include dates if provided
        if start_date is not None:
            data['startDate'] = start_date
        if end_date is not None:
            data['endDate'] = end_date

        return self._make_request('/api/v1/account/usage/report', method='POST', data=data)

    def get_export_status(self, job_id):
        """
        Get status of usage report export job

        Args:
            job_id (str): Job ID from start_usage_export

        Returns:
            dict: Response containing status and download URL when complete
        """
        path = f'/api/v1/account/usage/report/{job_id}/status'
        return self._make_request(path)

    def poll_until_complete(self, job_id, poll_interval=5, timeout=300):
        """
        Poll export job until complete or timeout

        Args:
            job_id (str): Job ID to poll
            poll_interval (int): Seconds between polls (default: 5)
            timeout (int): Maximum seconds to wait (default: 300)

        Returns:
            dict: Final status response with download URL
        """
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                print(f"Timeout waiting for job {job_id} to complete", file=sys.stderr)
                sys.exit(1)

            status_response = self.get_export_status(job_id)
            status = status_response.get('status', 'Unknown')

            print(f"Job {job_id} status: {status} (elapsed: {elapsed:.1f}s)", file=sys.stderr)

            if status == 'Success':
                return status_response
            elif status in ['Failed', 'Cancelled']:
                print(f"Job {job_id} failed with status: {status}", file=sys.stderr)
                print(f"Response: {json.dumps(status_response, indent=2)}", file=sys.stderr)
                sys.exit(1)

            time.sleep(poll_interval)

    def download_report(self, download_url, output_file):
        """
        Download usage report from S3 presigned URL

        Args:
            download_url (str): S3 presigned URL (valid for 10 minutes)
            output_file (str): Local file path to save the report

        Returns:
            str: Path to downloaded file
        """
        try:
            print(f"Downloading report to {output_file}...", file=sys.stderr)
            urlretrieve(download_url, output_file)
            print(f"Report downloaded successfully to {output_file}", file=sys.stderr)
            return output_file
        except Exception as e:
            print(f"Error downloading report: {e}", file=sys.stderr)
            sys.exit(1)


def validate_date(date_string):
    """Validate date is in YYYY-MM-DD format"""
    try:
        datetime.strptime(date_string, '%Y-%m-%d')
        return date_string
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format: {date_string}. Use YYYY-MM-DD")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Export usage report from Sumo Logic API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export with specific date range
  %(prog)s --region us1 --start-date 2024-01-01 --end-date 2024-01-31

  # Export entire subscription period (no dates)
  %(prog)s --region au

  # Export with custom grouping and report type
  %(prog)s --region us2 --start-date 2024-01-01 --end-date 2024-01-31 --group-by week --report-type detailed

  # Export for child org with deployment charges
  %(prog)s --region au --report-type childDetailed --include-deployment-charge

Available regions: us1, us2, eu, au, de, jp, ca, in

Report Types:
  - standard: Standard usage report
  - detailed: Detailed report with raw consumption and credits breakdown
  - childDetailed: Available for Sumo Orgs parents only

Grouping Options:
  - day: Aggregate by day (default)
  - week: Aggregate by week (Monday to Sunday)
  - month: Aggregate by calendar month

Note: The export process:
  1. Starts export job with parameters
  2. Polls for completion (default: check every 5 seconds, timeout after 5 minutes)
  3. Downloads CSV report from S3 URL (valid for 10 minutes)
  4. Dates default to subscription start/end if not provided

API Reference: https://api.us2.sumologic.com/docs/#operation/exportUsageReport
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
        '--start-date',
        type=validate_date,
        help='Start date for report in YYYY-MM-DD format (default: start of subscription)'
    )
    parser.add_argument(
        '--end-date',
        type=validate_date,
        help='End date for report in YYYY-MM-DD format (default: end of subscription)'
    )
    parser.add_argument(
        '--group-by',
        choices=['day', 'week', 'month'],
        default='day',
        help='Group usage data by period (default: day)'
    )
    parser.add_argument(
        '--report-type',
        choices=['standard', 'detailed', 'childDetailed'],
        default='standard',
        help='Report type: standard, detailed, or childDetailed (default: standard)'
    )
    parser.add_argument(
        '--include-deployment-charge',
        action='store_true',
        help='Include deployment charges for child organizations'
    )
    parser.add_argument(
        '--output',
        default=None,
        help='Output CSV file path (default: usage_report_YYYYMMDD_HHMMSS.csv)'
    )
    parser.add_argument(
        '--poll-interval',
        type=int,
        default=5,
        help='Seconds between status checks (default: 5)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=300,
        help='Maximum seconds to wait for completion (default: 300)'
    )

    args = parser.parse_args()

    # Validate required credentials
    if not args.access_id:
        parser.error("--access-id is required (or set SUMO_ACCESS_ID environment variable)")
    if not args.access_key:
        parser.error("--access-key is required (or set SUMO_ACCESS_KEY environment variable)")

    # Validate date range if both provided
    if args.start_date and args.end_date:
        start = datetime.strptime(args.start_date, '%Y-%m-%d')
        end = datetime.strptime(args.end_date, '%Y-%m-%d')
        if start > end:
            parser.error("Start date must be before or equal to end date")

    # Generate default output filename with timestamp if not provided
    if not args.output:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        args.output = f'usage_report_{timestamp}.csv'

    # Determine endpoint
    endpoint = args.region if args.region else args.endpoint

    # Create client
    client = SumoLogicClient(endpoint, args.access_id, args.access_key)

    try:
        # Step 1: Start export
        date_range = f"{args.start_date or 'subscription start'} to {args.end_date or 'subscription end'}"
        print(f"Starting usage report export for {date_range}...", file=sys.stderr)
        print(f"  Group by: {args.group_by}", file=sys.stderr)
        print(f"  Report type: {args.report_type}", file=sys.stderr)
        if args.include_deployment_charge:
            print(f"  Include deployment charges: Yes", file=sys.stderr)

        export_response = client.start_usage_export(
            start_date=args.start_date,
            end_date=args.end_date,
            group_by=args.group_by,
            report_type=args.report_type,
            include_deployment_charge=args.include_deployment_charge
        )
        job_id = export_response.get('jobId')

        if not job_id:
            print(f"Failed to get job ID from response: {json.dumps(export_response, indent=2)}", file=sys.stderr)
            sys.exit(1)

        print(f"Export job started with ID: {job_id}", file=sys.stderr)

        # Step 2: Poll for completion
        print(f"Polling for job completion (interval: {args.poll_interval}s, timeout: {args.timeout}s)...", file=sys.stderr)
        final_status = client.poll_until_complete(job_id, args.poll_interval, args.timeout)

        download_url = final_status.get('reportDownloadURL')
        if not download_url:
            print(f"No download URL in response: {json.dumps(final_status, indent=2)}", file=sys.stderr)
            sys.exit(1)

        # Step 3: Download report
        client.download_report(download_url, args.output)

        print(f"\nSuccess! Usage report saved to: {args.output}", file=sys.stderr)

    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
