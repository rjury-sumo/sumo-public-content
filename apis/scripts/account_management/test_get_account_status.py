#!/usr/bin/env python3
"""
Tests for get_account_status.py

Minimal tests focusing on key functionality:
- SumoLogicClient initialization and endpoint resolution
- API response formatting
- Table output formatting
"""

import pytest
from get_account_status import SumoLogicClient, format_table_output


class TestSumoLogicClient:
    """Test SumoLogicClient initialization and basic functionality"""

    def test_resolve_endpoint_region_code(self):
        """Test endpoint resolution with region codes"""
        client = SumoLogicClient('au', 'test_id', 'test_key')
        assert client.endpoint == 'https://api.au.sumologic.com'

        client = SumoLogicClient('us1', 'test_id', 'test_key')
        assert client.endpoint == 'https://api.sumologic.com'

        client = SumoLogicClient('us2', 'test_id', 'test_key')
        assert client.endpoint == 'https://api.us2.sumologic.com'

    def test_resolve_endpoint_full_url(self):
        """Test endpoint resolution with full URL"""
        client = SumoLogicClient('https://api.custom.sumologic.com', 'test_id', 'test_key')
        assert client.endpoint == 'https://api.custom.sumologic.com'

    def test_resolve_endpoint_invalid(self):
        """Test endpoint resolution with invalid input"""
        with pytest.raises(ValueError, match="Invalid endpoint"):
            SumoLogicClient('invalid', 'test_id', 'test_key')

    def test_auth_header_creation(self):
        """Test Basic Auth header is created correctly"""
        client = SumoLogicClient('us2', 'myid', 'mykey')
        assert client.auth_header.startswith('Basic ')
        # Verify base64 encoding is used
        import base64
        expected = base64.b64encode(b'myid:mykey').decode()
        assert client.auth_header == f'Basic {expected}'


class TestFormatTableOutput:
    """Test table output formatting"""

    def test_format_table_with_sample_data(self):
        """Test table formatting with actual API response structure"""
        sample_data = {
            "pricingModel": "credits",
            "canUpdatePlan": False,
            "planType": "Paid",
            "planExpirationDays": 88,
            "applicationUse": "",
            "accountActivated": True,
            "totalCredits": 21900,
            "logModel": "Tiered"
        }

        output = format_table_output(sample_data)

        # Check key elements are present
        assert "ACCOUNT STATUS" in output
        assert "Pricing Model: credits" in output
        assert "Plan Type: Paid" in output
        assert "Plan Expiration Days: 88" in output
        assert "Account Activated: True" in output
        assert "Total Credits: 21900" in output
        assert "Log Model: Tiered" in output
        assert "Can Update Plan: False" in output

    def test_format_table_with_dict_application_use(self):
        """Test table formatting when applicationUse is a dict"""
        sample_data = {
            "pricingModel": "credits",
            "planType": "Trial",
            "applicationUse": {
                "dashboards": 10,
                "scheduledSearches": 5,
                "users": 3
            }
        }

        output = format_table_output(sample_data)

        assert "ACCOUNT STATUS" in output
        assert "Dashboards: 10" in output
        assert "Scheduled Searches: 5" in output
        assert "Users: 3" in output

    def test_format_table_with_empty_application_use(self):
        """Test table formatting when applicationUse is empty string"""
        sample_data = {
            "pricingModel": "credits",
            "planType": "Paid",
            "applicationUse": ""
        }

        output = format_table_output(sample_data)

        # Empty applicationUse should not appear in output
        assert "ACCOUNT STATUS" in output
        assert "Pricing Model: credits" in output
        # Should not have "Application Use:" section for empty string
        assert output.count("Application Use") == 0

    def test_format_table_output_structure(self):
        """Test basic table output structure"""
        sample_data = {
            "pricingModel": "credits",
            "planType": "Paid"
        }

        output = format_table_output(sample_data)

        # Check basic structure
        lines = output.split('\n')
        assert lines[0] == "=" * 60
        assert lines[1] == "ACCOUNT STATUS"
        assert lines[2] == "=" * 60
        assert lines[-1] == "=" * 60
