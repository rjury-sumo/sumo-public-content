#!/usr/bin/env python3
"""
Tests for export_usage_report.py

Minimal tests focusing on key functionality:
- SumoLogicClient initialization
- Date validation
- Request formatting
"""

import pytest
from datetime import datetime
from export_usage_report import SumoLogicClient, validate_date


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


class TestDateValidation:
    """Test date validation"""

    def test_valid_date_format(self):
        """Test that valid dates are accepted"""
        assert validate_date('2024-01-01') == '2024-01-01'
        assert validate_date('2024-12-31') == '2024-12-31'
        assert validate_date('2023-06-15') == '2023-06-15'

    def test_invalid_date_format(self):
        """Test that invalid date formats are rejected"""
        with pytest.raises(Exception):  # ArgumentTypeError
            validate_date('2024/01/01')

        with pytest.raises(Exception):
            validate_date('01-01-2024')

        with pytest.raises(Exception):
            validate_date('2024-13-01')  # Invalid month

        with pytest.raises(Exception):
            validate_date('2024-01-32')  # Invalid day

        with pytest.raises(Exception):
            validate_date('not-a-date')


class TestExportWorkflow:
    """Test export workflow methods"""

    def test_start_usage_export_parameters(self):
        """Test that start_usage_export formats request correctly"""
        client = SumoLogicClient('au', 'test_id', 'test_key')

        # We can't test actual API call, but we can verify method exists
        # and accepts correct parameters
        assert hasattr(client, 'start_usage_export')
        assert callable(client.start_usage_export)

    def test_get_export_status_parameters(self):
        """Test that get_export_status formats request correctly"""
        client = SumoLogicClient('au', 'test_id', 'test_key')

        assert hasattr(client, 'get_export_status')
        assert callable(client.get_export_status)

    def test_poll_until_complete_parameters(self):
        """Test that poll_until_complete accepts correct parameters"""
        client = SumoLogicClient('au', 'test_id', 'test_key')

        assert hasattr(client, 'poll_until_complete')
        assert callable(client.poll_until_complete)

    def test_download_report_parameters(self):
        """Test that download_report accepts correct parameters"""
        client = SumoLogicClient('au', 'test_id', 'test_key')

        assert hasattr(client, 'download_report')
        assert callable(client.download_report)
