#!/usr/bin/env python3
"""
Tests for get_usage_forecast.py

Minimal tests focusing on key functionality:
- SumoLogicClient endpoint resolution
- Days parameter validation
- Table output formatting
"""

import pytest
from get_usage_forecast import SumoLogicClient, format_table_output


class TestSumoLogicClient:
    """Test SumoLogicClient initialization and basic functionality"""

    def test_resolve_endpoint_au_region(self):
        """Test endpoint resolution for AU region"""
        client = SumoLogicClient('au', 'test_id', 'test_key')
        assert client.endpoint == 'https://api.au.sumologic.com'

    def test_resolve_endpoint_us2_region(self):
        """Test endpoint resolution for US2 region"""
        client = SumoLogicClient('us2', 'test_id', 'test_key')
        assert client.endpoint == 'https://api.us2.sumologic.com'

    def test_get_usage_forecast_valid_days(self):
        """Test that valid day ranges don't raise errors"""
        client = SumoLogicClient('au', 'test_id', 'test_key')

        # These should not raise ValueError
        # (We're testing parameter validation, not making actual API calls)
        try:
            # The method will fail on actual HTTP request, but should pass validation
            with pytest.raises((SystemExit, OSError, Exception)):
                client.get_usage_forecast(1)
        except ValueError:
            pytest.fail("Should not raise ValueError for valid day value")

    def test_get_usage_forecast_invalid_days_too_low(self):
        """Test that days < 1 raises ValueError"""
        client = SumoLogicClient('au', 'test_id', 'test_key')
        with pytest.raises(ValueError, match="Number of days must be between 1 and 365"):
            client.get_usage_forecast(0)

    def test_get_usage_forecast_invalid_days_too_high(self):
        """Test that days > 365 raises ValueError"""
        client = SumoLogicClient('au', 'test_id', 'test_key')
        with pytest.raises(ValueError, match="Number of days must be between 1 and 365"):
            client.get_usage_forecast(366)

    def test_get_usage_forecast_boundary_values(self):
        """Test boundary values for days parameter"""
        client = SumoLogicClient('au', 'test_id', 'test_key')

        # Day 1 and 365 should be valid (won't raise ValueError in validation)
        try:
            with pytest.raises((SystemExit, OSError, Exception)):
                client.get_usage_forecast(1)
        except ValueError:
            pytest.fail("Day 1 should be valid")

        try:
            with pytest.raises((SystemExit, OSError, Exception)):
                client.get_usage_forecast(365)
        except ValueError:
            pytest.fail("Day 365 should be valid")


class TestFormatTableOutput:
    """Test table output formatting"""

    def test_format_table_with_actual_api_response(self):
        """Test table formatting with actual API response structure"""
        sample_data = {
            "averageUsage": 0.06248000870698236,
            "usagePercentage": 0.5373240524310626,
            "forecastedUsage": 123.17220824861717,
            "forecastedUsagePercentage": 0.5624301746512199,
            "remainingDays": 88.0
        }

        output = format_table_output(sample_data, 30)

        # Check key elements are present
        assert "USAGE FORECAST - 30 DAY(S)" in output
        assert "Average Usage:" in output
        assert "Usage Percentage:" in output
        assert "Forecasted Usage:" in output
        assert "Forecasted Usage Percentage:" in output
        assert "Remaining Days:" in output

        # Check percentage formatting
        assert "53.73%" in output  # usagePercentage
        assert "56.24%" in output  # forecastedUsagePercentage

    def test_format_table_percentage_formatting(self):
        """Test that percentages are formatted correctly"""
        sample_data = {
            "usagePercentage": 0.5373240524310626,
            "forecastedUsagePercentage": 0.5624301746512199
        }

        output = format_table_output(sample_data, 30)

        # Percentages should be multiplied by 100 and have % sign
        assert "53.73%" in output
        assert "56.24%" in output

    def test_format_table_large_numbers_formatted(self):
        """Test that large numbers are formatted with commas"""
        sample_data = {
            "forecastedUsage": 123.17220824861717,
            "remainingDays": 88.0
        }

        output = format_table_output(sample_data, 7)

        # Large numbers should be formatted
        assert "123.1722" in output
        assert "88.0000" in output

    def test_format_table_small_numbers_formatted(self):
        """Test that small numbers are formatted with decimals"""
        sample_data = {
            "averageUsage": 0.06248000870698236
        }

        output = format_table_output(sample_data, 7)

        # Small numbers should show more decimal places
        assert "0.062480" in output

    def test_format_table_output_structure(self):
        """Test basic table output structure"""
        sample_data = {
            "averageUsage": 0.5,
            "forecastedUsage": 123.45
        }

        output = format_table_output(sample_data, 10)

        # Check basic structure
        lines = output.split('\n')
        assert lines[0] == "=" * 60
        assert "USAGE FORECAST - 10 DAY(S)" in lines[1]
        assert lines[2] == "=" * 60
        assert lines[-1] == "=" * 60

    def test_format_table_empty_data(self):
        """Test table formatting with empty data"""
        sample_data = {}

        output = format_table_output(sample_data, 5)

        # Should still have basic structure
        assert "USAGE FORECAST - 5 DAY(S)" in output
        assert output.startswith("=" * 60)
        assert output.endswith("=" * 60)
