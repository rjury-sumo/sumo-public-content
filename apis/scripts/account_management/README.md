# Sumo Logic Account Management API Scripts

Python scripts for interacting with Sumo Logic Account Management APIs to retrieve account status, usage forecasts, and child organization usage data.

## Features

- **Account Status**: Get current account subscription, plan type, and usage information
- **Usage Forecast**: Retrieve projected usage for a specified number of days
- **Child Organization Usage**: Get usage data for all child organizations (parent orgs only)

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
# Install dependencies
uv sync

# Or run scripts directly with uv
uv run python get_account_status.py --help
```

## Configuration

Set environment variables for your Sumo Logic credentials:

```bash
export SUMO_ACCESS_ID="your_access_id"
export SUMO_ACCESS_KEY="your_access_key"
```

## Usage

### Get Account Status

```bash
# Using environment variables
uv run python get_account_status.py --region au --output table

# With explicit credentials
uv run python get_account_status.py --region us2 --access-id YOUR_ID --access-key YOUR_KEY --output json
```

### Get Usage Forecast

```bash
# 30-day forecast
uv run python get_usage_forecast.py --region us2 --days 30 --output table

# 90-day forecast as JSON
uv run python get_usage_forecast.py --region au --days 90 --output json
```

### Get Child Organization Usage

```bash
# Table format
uv run python get_child_usages.py --region us1 --output table

# CSV export
uv run python get_child_usages.py --region us2 --output csv > child_usage.csv
```

## Available Regions

- `us1` - https://api.sumologic.com
- `us2` - https://api.us2.sumologic.com
- `eu` - https://api.eu.sumologic.com
- `au` - https://api.au.sumologic.com
- `de` - https://api.de.sumologic.com
- `jp` - https://api.jp.sumologic.com
- `ca` - https://api.ca.sumologic.com
- `in` - https://api.in.sumologic.com

## Output Formats

- **JSON**: Machine-readable format with complete data
- **Table**: Human-readable formatted output
- **CSV**: Comma-separated values (child usages only)

## API References

- [Account Status](https://api.us2.sumologic.com/docs/#operation/getStatus)
- [Usage Forecast](https://api.us2.sumologic.com/docs/#operation/getUsageForecast)
- [Child Usages](https://api.us2.sumologic.com/docs/#operation/getChildUsages)

## Requirements

- Python >= 3.9
- No external dependencies (uses stdlib only)
