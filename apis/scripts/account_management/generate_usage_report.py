#!/usr/bin/env python3
"""
Sumo Logic Executive Usage Report Generator

This script generates a comprehensive HTML report combining:
- Account status (plan details, expiration, total credits)
- Usage forecasts (7-day, 30-day, term-to-date)
- Detailed usage export with charts (daily credits trend, credit breakdown by type)

Generates an executive-ready HTML report with visualizations.
"""

import argparse
import base64
import csv
import json
import os
import sys
import time
from datetime import datetime
from io import BytesIO, StringIO
from urllib.parse import urljoin
from urllib.request import Request, urlopen, urlretrieve
from urllib.error import HTTPError, URLError

# Import visualization libraries
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np


class SumoLogicClient:
    """Client for interacting with Sumo Logic API"""

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
        self.endpoint = self._resolve_endpoint(endpoint)
        self.access_id = access_id
        self.access_key = access_key
        self.auth_header = self._create_auth_header()

    def _resolve_endpoint(self, endpoint):
        if endpoint.lower() in self.REGIONS:
            return self.REGIONS[endpoint.lower()]
        elif endpoint.startswith('http'):
            return endpoint.rstrip('/')
        else:
            raise ValueError(f"Invalid endpoint. Use a region code ({', '.join(self.REGIONS.keys())}) or full URL")

    def _create_auth_header(self):
        credentials = f"{self.access_id}:{self.access_key}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded_credentials}"

    def _make_request(self, path, method='GET', params=None, data=None):
        url = urljoin(self.endpoint, path)
        if params:
            from urllib.parse import urlencode
            url += '?' + urlencode(params)

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

    def get_account_status(self):
        return self._make_request('/api/v1/account/status')

    def get_usage_forecast(self, number_of_days=None):
        params = {'numberOfDays': number_of_days} if number_of_days else {}
        return self._make_request('/api/v1/account/usageForecast', params=params)

    def start_usage_export(self, start_date=None, end_date=None, group_by='day',
                          report_type='standard', include_deployment_charge=False):
        data = {
            'groupBy': group_by,
            'reportType': report_type,
            'includeDeploymentCharge': include_deployment_charge
        }
        if start_date:
            data['startDate'] = start_date
        if end_date:
            data['endDate'] = end_date
        return self._make_request('/api/v1/account/usage/report', method='POST', data=data)

    def get_export_status(self, job_id):
        return self._make_request(f'/api/v1/account/usage/report/{job_id}/status')

    def poll_until_complete(self, job_id, poll_interval=5, timeout=300):
        start_time = time.time()
        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

            status_response = self.get_export_status(job_id)
            status = status_response.get('status', 'Unknown')

            if status == 'Success':
                return status_response
            elif status in ['Failed', 'Cancelled']:
                raise RuntimeError(f"Job {job_id} failed with status: {status}")

            time.sleep(poll_interval)

    def download_csv_to_string(self, download_url):
        """Download CSV from URL and return as string"""
        with urlopen(download_url) as response:
            return response.read().decode('utf-8')


def generate_charts(csv_data, output_dir):
    """Generate charts from CSV data and return as base64 encoded images"""
    # Parse CSV
    df = pd.read_csv(StringIO(csv_data))
    df['Date'] = pd.to_datetime(df['Date'])

    charts = {}

    # Chart 1: Total Credits per Day with 7-day trend line
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(df['Date'], df['Total Credits'], marker='o', linewidth=1, markersize=3, label='Daily Credits', alpha=0.7)

    # Calculate 7-day rolling average
    df['7d_avg'] = df['Total Credits'].rolling(window=7, min_periods=1).mean()
    ax.plot(df['Date'], df['7d_avg'], linewidth=2, color='red', label='7-Day Trend', alpha=0.8)

    ax.set_xlabel('Date')
    ax.set_ylabel('Total Credits')
    ax.set_title('Daily Credit Usage with 7-Day Trend')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    # Save to base64
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
    buffer.seek(0)
    charts['total_credits'] = base64.b64encode(buffer.read()).decode()
    plt.close()

    # Chart 2: Stacked area chart of credit types (excluding Total Credits)
    credit_columns = [col for col in df.columns if 'Credits' in col and col != 'Total Credits']

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.stackplot(df['Date'], *[df[col] for col in credit_columns],
                 labels=credit_columns, alpha=0.8)

    ax.set_xlabel('Date')
    ax.set_ylabel('Credits')
    ax.set_title('Credit Usage by Type (Stacked)')
    ax.legend(loc='upper left', bbox_to_anchor=(1, 1))
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
    buffer.seek(0)
    charts['stacked_credits'] = base64.b64encode(buffer.read()).decode()
    plt.close()

    return charts


def generate_html_report(account_status, forecast_7d, forecast_30d, forecast_term,
                        csv_data, csv_filename, charts):
    """Generate HTML report"""

    # Extract key metrics
    total_credits = account_status.get('totalCredits', 'N/A')
    plan_type = account_status.get('planType', 'N/A')
    expiration_days = account_status.get('planExpirationDays', 'N/A')
    pricing_model = account_status.get('pricingModel', 'N/A')

    # Calculate summary stats from CSV
    df = pd.read_csv(StringIO(csv_data))
    df['Date'] = pd.to_datetime(df['Date'])
    total_used = df['Total Credits'].sum()
    avg_daily = df['Total Credits'].mean()
    max_daily = df['Total Credits'].max()

    # Calculate monthly breakdown
    df['Month'] = df['Date'].dt.to_period('M')
    monthly_summary = df.groupby('Month').agg({
        'Total Credits': ['sum', 'mean', 'count']
    }).round(4)
    monthly_summary.columns = ['Total Credits', 'Daily Average', 'Days']
    monthly_summary = monthly_summary.reset_index()
    monthly_summary['Month'] = monthly_summary['Month'].astype(str)

    report_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Sumo Logic Usage Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            margin: 0;
            font-size: 2.5em;
        }}
        .header .subtitle {{
            margin-top: 10px;
            opacity: 0.9;
        }}
        .section {{
            background: white;
            padding: 25px;
            margin-bottom: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .section h2 {{
            color: #667eea;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
            margin-top: 0;
        }}
        .metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}
        .metric-label {{
            font-size: 0.9em;
            color: #666;
            margin-bottom: 5px;
        }}
        .metric-value {{
            font-size: 2em;
            font-weight: bold;
            color: #333;
        }}
        .metric-unit {{
            font-size: 0.8em;
            color: #888;
        }}
        .forecast-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .forecast-card {{
            background: white;
            border: 2px solid #667eea;
            padding: 20px;
            border-radius: 8px;
        }}
        .forecast-card h3 {{
            margin-top: 0;
            color: #667eea;
        }}
        .forecast-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }}
        .forecast-item:last-child {{
            border-bottom: none;
        }}
        .chart {{
            margin: 20px 0;
            text-align: center;
        }}
        .chart img {{
            max-width: 100%;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .status-good {{
            color: #10b981;
            font-weight: bold;
        }}
        .status-warning {{
            color: #f59e0b;
            font-weight: bold;
        }}
        .status-critical {{
            color: #ef4444;
            font-weight: bold;
        }}
        .download-link {{
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 12px 24px;
            border-radius: 6px;
            text-decoration: none;
            margin: 10px 0;
            transition: background 0.3s;
        }}
        .download-link:hover {{
            background: #5568d3;
        }}
        .monthly-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        .monthly-table th {{
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        .monthly-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid #e5e7eb;
        }}
        .monthly-table tr:hover {{
            background: #f9fafb;
        }}
        .monthly-table td:nth-child(2),
        .monthly-table td:nth-child(3),
        .monthly-table td:nth-child(4) {{
            text-align: right;
            font-family: 'Courier New', monospace;
        }}
        .footer {{
            text-align: center;
            color: #888;
            margin-top: 40px;
            padding: 20px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Sumo Logic Usage Report</h1>
        <div class="subtitle">Executive Summary - Generated {report_date}</div>
    </div>

    <div class="section">
        <h2>Account Overview</h2>
        <div class="metrics">
            <div class="metric-card">
                <div class="metric-label">Plan Type</div>
                <div class="metric-value">{plan_type}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Pricing Model</div>
                <div class="metric-value">{pricing_model.title()}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Credits (Term)</div>
                <div class="metric-value">{total_credits:,}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Days Until Expiration</div>
                <div class="metric-value {'status-good' if expiration_days > 30 else 'status-warning' if expiration_days > 7 else 'status-critical'}">{expiration_days}</div>
                <div class="metric-unit">days</div>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>Usage Summary</h2>
        <div class="metrics">
            <div class="metric-card">
                <div class="metric-label">Total Used (Period)</div>
                <div class="metric-value">{total_used:.2f}</div>
                <div class="metric-unit">credits</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Average Daily Usage</div>
                <div class="metric-value">{avg_daily:.2f}</div>
                <div class="metric-unit">credits/day</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Peak Daily Usage</div>
                <div class="metric-value">{max_daily:.2f}</div>
                <div class="metric-unit">credits</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Utilization Rate</div>
                <div class="metric-value">{(total_used/total_credits*100):.1f}%</div>
                <div class="metric-unit">of term allocation</div>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>Usage Forecasts</h2>
        <div class="forecast-grid">
            <div class="forecast-card">
                <h3>7-Day Forecast</h3>
                <div class="forecast-item">
                    <span>Average Usage:</span>
                    <strong>{forecast_7d.get('averageUsage', 0):.4f}</strong>
                </div>
                <div class="forecast-item">
                    <span>Current %:</span>
                    <strong>{forecast_7d.get('usagePercentage', 0)*100:.2f}%</strong>
                </div>
                <div class="forecast-item">
                    <span>Forecasted Usage:</span>
                    <strong>{forecast_7d.get('forecastedUsage', 0):.2f}</strong>
                </div>
                <div class="forecast-item">
                    <span>Forecasted %:</span>
                    <strong>{forecast_7d.get('forecastedUsagePercentage', 0)*100:.2f}%</strong>
                </div>
            </div>

            <div class="forecast-card">
                <h3>30-Day Forecast</h3>
                <div class="forecast-item">
                    <span>Average Usage:</span>
                    <strong>{forecast_30d.get('averageUsage', 0):.4f}</strong>
                </div>
                <div class="forecast-item">
                    <span>Current %:</span>
                    <strong>{forecast_30d.get('usagePercentage', 0)*100:.2f}%</strong>
                </div>
                <div class="forecast-item">
                    <span>Forecasted Usage:</span>
                    <strong>{forecast_30d.get('forecastedUsage', 0):.2f}</strong>
                </div>
                <div class="forecast-item">
                    <span>Forecasted %:</span>
                    <strong>{forecast_30d.get('forecastedUsagePercentage', 0)*100:.2f}%</strong>
                </div>
            </div>

            <div class="forecast-card">
                <h3>Term-to-Date Forecast</h3>
                <div class="forecast-item">
                    <span>Average Usage:</span>
                    <strong>{forecast_term.get('averageUsage', 0):.4f}</strong>
                </div>
                <div class="forecast-item">
                    <span>Current %:</span>
                    <strong>{forecast_term.get('usagePercentage', 0)*100:.2f}%</strong>
                </div>
                <div class="forecast-item">
                    <span>Forecasted Usage:</span>
                    <strong>{forecast_term.get('forecastedUsage', 0):.2f}</strong>
                </div>
                <div class="forecast-item">
                    <span>Forecasted %:</span>
                    <strong class="{'status-good' if forecast_term.get('forecastedUsagePercentage', 0) < 0.8 else 'status-warning' if forecast_term.get('forecastedUsagePercentage', 0) < 0.95 else 'status-critical'}">{forecast_term.get('forecastedUsagePercentage', 0)*100:.2f}%</strong>
                </div>
                <div class="forecast-item">
                    <span>Remaining Days:</span>
                    <strong>{forecast_term.get('remainingDays', 0):.0f}</strong>
                </div>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>Credit Usage Trends</h2>
        <div class="chart">
            <h3>Daily Total Credits with 7-Day Trend</h3>
            <img src="data:image/png;base64,{charts['total_credits']}" alt="Total Credits Chart">
        </div>

        <div class="chart">
            <h3>Credit Breakdown by Type</h3>
            <img src="data:image/png;base64,{charts['stacked_credits']}" alt="Stacked Credits Chart">
        </div>
    </div>

    <div class="section">
        <h2>Monthly Usage Breakdown</h2>
        <table class="monthly-table">
            <thead>
                <tr>
                    <th>Month</th>
                    <th>Total Credits</th>
                    <th>Daily Average</th>
                    <th>Days</th>
                </tr>
            </thead>
            <tbody>
{''.join(f"""                <tr>
                    <td>{row['Month']}</td>
                    <td>{row['Total Credits']:.4f}</td>
                    <td>{row['Daily Average']:.4f}</td>
                    <td>{int(row['Days'])}</td>
                </tr>
""" for _, row in monthly_summary.iterrows())}            </tbody>
        </table>
    </div>

    <div class="section">
        <h2>Detailed Usage Data</h2>
        <p>For detailed daily usage breakdown and further analysis:</p>
        <a href="{csv_filename}" class="download-link">📥 Download Detailed Usage CSV</a>
        <p style="margin-top: 10px; color: #666; font-size: 0.9em;">
            The CSV file contains daily usage data across all credit types for graphing and detailed analysis.
        </p>
    </div>

    <div class="footer">
        <p>Generated by Sumo Logic Usage Report Generator</p>
        <p>Report Date: {report_date}</p>
    </div>
</body>
</html>
"""

    return html


def main():
    parser = argparse.ArgumentParser(
        description='Generate comprehensive Sumo Logic usage report',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --region au
  %(prog)s --region us2 --output my_report.html
  %(prog)s --endpoint https://api.sumologic.com --access-id ID --access-key KEY

This script:
  1. Fetches account status (plan details, credits, expiration)
  2. Gets usage forecasts (7-day, 30-day, term-to-date)
  3. Exports detailed usage CSV
  4. Generates HTML report with charts and metrics

Output includes:
  - HTML report with charts and executive summary
  - Detailed usage CSV file for further analysis
        """
    )

    endpoint_group = parser.add_mutually_exclusive_group(required=True)
    endpoint_group.add_argument('--region', choices=['us1', 'us2', 'eu', 'au', 'de', 'jp', 'ca', 'in'])
    endpoint_group.add_argument('--endpoint')

    parser.add_argument('--access-id', default=os.environ.get('SUMO_ACCESS_ID'))
    parser.add_argument('--access-key', default=os.environ.get('SUMO_ACCESS_KEY'))
    parser.add_argument('--output', default=None,
                       help='Output HTML file (default: reports/usage_report_YYYYMMDD_HHMMSS.html)')

    args = parser.parse_args()

    if not args.access_id or not args.access_key:
        parser.error("Access ID and key required (use --access-id/--access-key or set env vars)")

    # Create reports directory if it doesn't exist
    reports_dir = 'reports'
    os.makedirs(reports_dir, exist_ok=True)

    # Generate default output filename if not provided
    if not args.output:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        args.output = os.path.join(reports_dir, f'usage_report_{timestamp}.html')
    elif not os.path.dirname(args.output):
        # If user provided filename without path, put it in reports directory
        args.output = os.path.join(reports_dir, args.output)

    endpoint = args.region if args.region else args.endpoint
    client = SumoLogicClient(endpoint, args.access_id, args.access_key)

    print("=" * 60)
    print("SUMO LOGIC USAGE REPORT GENERATOR")
    print("=" * 60)

    try:
        # Step 1: Get account status
        print("\n[1/5] Fetching account status...")
        account_status = client.get_account_status()
        print(f"  ✓ Plan: {account_status.get('planType')}, Expires in: {account_status.get('planExpirationDays')} days")

        # Step 2: Get forecasts
        print("\n[2/5] Fetching usage forecasts...")
        print("  - 7-day forecast...")
        forecast_7d = client.get_usage_forecast(7)
        print("  - 30-day forecast...")
        forecast_30d = client.get_usage_forecast(30)
        print("  - Term-to-date forecast...")
        forecast_term = client.get_usage_forecast()
        print(f"  ✓ Forecast usage percentage: {forecast_term.get('forecastedUsagePercentage', 0)*100:.1f}%")

        # Step 3: Export detailed usage
        print("\n[3/5] Exporting detailed usage data...")
        export_response = client.start_usage_export()
        job_id = export_response.get('jobId')
        print(f"  ✓ Export job started: {job_id}")

        print("  - Waiting for export to complete...")
        final_status = client.poll_until_complete(job_id)
        download_url = final_status.get('reportDownloadURL')

        print("  - Downloading CSV...")
        csv_data = client.download_csv_to_string(download_url)

        # Save CSV file
        csv_filename = args.output.replace('.html', '.csv')
        with open(csv_filename, 'w') as f:
            f.write(csv_data)
        print(f"  ✓ CSV saved: {csv_filename}")

        # Step 4: Generate charts
        print("\n[4/5] Generating charts...")
        charts = generate_charts(csv_data, os.path.dirname(args.output) or '.')
        print("  ✓ Charts generated")

        # Step 5: Generate HTML report
        print("\n[5/5] Generating HTML report...")
        html_content = generate_html_report(
            account_status, forecast_7d, forecast_30d, forecast_term,
            csv_data, csv_filename, charts
        )

        with open(args.output, 'w') as f:
            f.write(html_content)
        print(f"  ✓ HTML report saved: {args.output}")

        print("\n" + "=" * 60)
        print("✅ REPORT GENERATION COMPLETE")
        print("=" * 60)
        print(f"\nHTML Report: {args.output}")
        print(f"CSV Data:    {csv_filename}")
        print("\nOpen the HTML file in your browser to view the executive report.")

    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
