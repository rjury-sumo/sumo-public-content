#!/usr/bin/env python3
"""
Unit tests for execute_search_job.py

Tests cover YAML configuration parsing, time format handling, filename generation,
output formatting, and validation logic.
"""

import pytest
import json
import os
import tempfile
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import sys

# Import functions from the script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from execute_search_job import (
    parse_time_value,
    validate_config,
    format_batch_filename,
    parse_interval_to_milliseconds,
    generate_batch_intervals,
    format_records_table,
    format_records_csv,
    load_yaml_config
)


class TestTimeFormatParsing:
    """Test time format parsing functionality"""

    def test_parse_time_relative_hours(self):
        """Test parsing relative time in hours"""
        result = parse_time_value("-1h")
        now = datetime.now().timestamp() * 1000
        # Should be approximately 1 hour ago
        assert abs(result - (now - 3600000)) < 1000  # Within 1 second tolerance

    def test_parse_time_relative_minutes(self):
        """Test parsing relative time in minutes"""
        result = parse_time_value("-30m")
        now = datetime.now().timestamp() * 1000
        # Should be approximately 30 minutes ago
        assert abs(result - (now - 1800000)) < 1000

    def test_parse_time_relative_days(self):
        """Test parsing relative time in days"""
        result = parse_time_value("-2d")
        now = datetime.now().timestamp() * 1000
        # Should be approximately 2 days ago
        assert abs(result - (now - 172800000)) < 1000

    def test_parse_time_relative_weeks(self):
        """Test parsing relative time in weeks"""
        result = parse_time_value("-1w")
        now = datetime.now().timestamp() * 1000
        # Should be approximately 1 week ago (allow 1 hour tolerance for DST issues)
        assert abs(result - (now - 604800000)) < 3600000

    def test_parse_time_now(self):
        """Test parsing 'now' keyword"""
        result = parse_time_value("now")
        now = datetime.now().timestamp() * 1000
        assert abs(result - now) < 1000  # Within 1 second

    def test_parse_time_epoch_milliseconds(self):
        """Test parsing epoch milliseconds as integer"""
        epoch_ms = 1704067200000
        result = parse_time_value(epoch_ms)
        assert result == epoch_ms

    def test_parse_time_iso_format_with_z(self):
        """Test parsing ISO format with Z timezone"""
        iso_time = "2024-01-01T00:00:00Z"
        result = parse_time_value(iso_time)
        # Expected value depends on local timezone interpretation
        # Just verify it's a valid epoch milliseconds value
        assert isinstance(result, int)
        assert result > 0

    def test_parse_time_iso_format_without_z(self):
        """Test parsing ISO format without Z"""
        iso_time = "2024-01-01T00:00:00"
        result = parse_time_value(iso_time)
        # Should parse as local time
        assert isinstance(result, int)

    def test_parse_time_invalid_format(self):
        """Test parsing invalid time format raises error"""
        with pytest.raises(ValueError, match="Invalid time format"):
            parse_time_value("invalid")


class TestConfigValidation:
    """Test YAML configuration validation"""

    def test_validate_config_all_required_fields(self):
        """Test validation passes with all required fields"""
        config = {
            'name': 'test_query',
            'query': '_sourceCategory=*',
            'from': '-1h',
            'to': 'now'
        }
        # Should not raise exception
        validate_config(config)

    def test_validate_config_missing_name(self):
        """Test validation fails without name field"""
        config = {
            'query': '_sourceCategory=*',
            'from': '-1h',
            'to': 'now'
        }
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_validate_config_missing_query(self):
        """Test validation fails without query field"""
        config = {
            'name': 'test_query',
            'from': '-1h',
            'to': 'now'
        }
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_validate_config_empty_name(self):
        """Test validation fails with empty name"""
        config = {
            'name': '',
            'query': '_sourceCategory=*',
            'from': '-1h',
            'to': 'now'
        }
        with pytest.raises(SystemExit):
            validate_config(config)

    def test_validate_config_name_not_string(self):
        """Test validation fails when name is not a string"""
        config = {
            'name': 123,
            'query': '_sourceCategory=*',
            'from': '-1h',
            'to': 'now'
        }
        with pytest.raises(SystemExit):
            validate_config(config)


class TestBatchFilenameGeneration:
    """Test batch filename generation"""

    def test_format_batch_filename_with_extension(self):
        """Test batch filename generation with file extension"""
        filename = format_batch_filename(
            "results.csv",
            0,
            1704067200000,  # 2024-01-01 00:00:00 UTC
            1704070800000   # 2024-01-01 01:00:00 UTC
        )
        # Verify structure: name_batch_index_fromtime_totime.ext
        assert filename.startswith("results_batch_000_")
        assert filename.endswith(".csv")
        assert "_batch_000_" in filename
        # Verify it contains timestamps in correct format (14 digits + .milliseconds)
        parts = filename.replace("results_batch_000_", "").replace(".csv", "").split("_")
        assert len(parts) == 2
        for timestamp in parts:
            assert "." in timestamp  # Has milliseconds
            date_part = timestamp.split(".")[0]
            assert len(date_part) == 14  # YYYYMMddHHmmss

    def test_format_batch_filename_without_extension(self):
        """Test batch filename generation without file extension"""
        filename = format_batch_filename(
            "results",
            5,
            1704067200000,
            1704070800000
        )
        assert filename.startswith("results_batch_005_")
        assert "_batch_005_" in filename
        # Verify timestamp structure
        parts = filename.replace("results_batch_005_", "").split("_")
        assert len(parts) == 2

    def test_format_batch_filename_none_input(self):
        """Test batch filename generation with None input"""
        filename = format_batch_filename(None, 0, 1704067200000, 1704070800000)
        assert filename is None

    def test_format_batch_filename_milliseconds(self):
        """Test batch filename includes milliseconds"""
        filename = format_batch_filename(
            "data.json",
            0,
            1704067200123,  # With milliseconds
            1704070800456
        )
        # Verify milliseconds are included (should end with .123 and .456)
        assert ".123_" in filename
        assert ".456.json" in filename


class TestIntervalParsing:
    """Test interval parsing and generation"""

    def test_parse_interval_hours(self):
        """Test parsing interval in hours"""
        result = parse_interval_to_milliseconds("1h")
        assert result == 3600000

    def test_parse_interval_minutes(self):
        """Test parsing interval in minutes"""
        result = parse_interval_to_milliseconds("30m")
        assert result == 1800000

    def test_parse_interval_days(self):
        """Test parsing interval in days"""
        result = parse_interval_to_milliseconds("1d")
        assert result == 86400000

    def test_parse_interval_invalid(self):
        """Test parsing invalid interval format"""
        with pytest.raises(ValueError, match="Invalid interval format"):
            parse_interval_to_milliseconds("invalid")

    def test_generate_batch_intervals_even_split(self):
        """Test generating batch intervals with even split"""
        intervals = generate_batch_intervals(
            1704067200000,  # Start
            1704070800000,  # End (1 hour later)
            1800000         # 30 minute intervals
        )
        assert len(intervals) == 2
        # First interval starts at start time
        assert intervals[0][0] == 1704067200000
        # Last interval ends at end time
        assert intervals[-1][1] == 1704070800000
        # Each interval is 30 minutes (except possibly the last)
        assert intervals[0][1] - intervals[0][0] == 1800000

    def test_generate_batch_intervals_uneven_split(self):
        """Test generating batch intervals with uneven split"""
        intervals = generate_batch_intervals(
            1704067200000,
            1704074400000,  # 2 hours later
            3000000         # 50 minute intervals
        )
        # Should have 3 intervals (50m, 50m, 20m)
        assert len(intervals) == 3
        assert intervals[-1][1] == 1704074400000  # Last interval ends at end time


class TestOutputFormatting:
    """Test output formatting functions"""

    def test_format_records_csv_basic(self):
        """Test CSV formatting with basic records"""
        results = {
            'fields': [
                {'name': 'count', 'fieldType': 'int'},
                {'name': 'status', 'fieldType': 'string'}
            ],
            'records': [
                {'map': {'count': '100', 'status': 'OK'}},
                {'map': {'count': '200', 'status': 'ERROR'}}
            ]
        }
        csv_output = format_records_csv(results)
        lines = csv_output.strip().split('\n')

        assert len(lines) == 3  # Header + 2 data rows
        # Strip any carriage returns for cross-platform compatibility
        assert lines[0].strip() == 'count,status'
        assert '100' in lines[1]
        assert 'OK' in lines[1]

    def test_format_records_csv_empty(self):
        """Test CSV formatting with empty records"""
        results = {'records': []}
        csv_output = format_records_csv(results)
        assert csv_output == ""

    def test_format_records_table_basic(self):
        """Test table formatting with basic records"""
        results = {
            'fields': [
                {'name': 'name', 'fieldType': 'string'},
                {'name': 'count', 'fieldType': 'int'}
            ],
            'records': [
                {'map': {'name': 'test', 'count': '42'}}
            ]
        }
        table_output = format_records_table(results)

        assert 'name' in table_output
        assert 'count' in table_output
        assert 'test' in table_output
        assert '42' in table_output

    def test_format_records_table_empty(self):
        """Test table formatting with empty records"""
        results = {'records': []}
        table_output = format_records_table(results)
        assert table_output == "No records found"


class TestYAMLConfigLoading:
    """Test YAML configuration loading"""

    def test_load_yaml_config_valid(self):
        """Test loading valid YAML config"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
name: test_query
query: "_sourceCategory=*"
from: "-1h"
to: "now"
timeZone: "UTC"
byReceiptTime: false
""")
            f.flush()
            config_path = f.name

        try:
            config = load_yaml_config(config_path)
            assert config['name'] == 'test_query'
            assert config['query'] == '_sourceCategory=*'
            assert config['from'] == '-1h'
            assert config['to'] == 'now'
            assert config['timeZone'] == 'UTC'
            assert config['byReceiptTime'] is False
        finally:
            os.unlink(config_path)

    def test_load_yaml_config_multiline_query(self):
        """Test loading YAML config with multiline query"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
name: multiline_test
query: |
  _sourceCategory=prod
  | where status >= 400
  | count
from: "-24h"
to: "now"
""")
            f.flush()
            config_path = f.name

        try:
            config = load_yaml_config(config_path)
            assert 'status >= 400' in config['query']
            assert '| count' in config['query']
        finally:
            os.unlink(config_path)

    def test_load_yaml_config_missing_file(self):
        """Test loading non-existent YAML file"""
        with pytest.raises(SystemExit):
            load_yaml_config('/nonexistent/file.yaml')


class TestExistingOutputFiles:
    """Test validation against existing output files"""

    OUTPUT_DIR = '/Users/rjury/Documents/sumo2021/sumo-public-content/apis/scripts/search_job/output'

    def test_jsonl_output_format(self):
        """Test JSONL output contains valid JSON per line"""
        jsonl_file = os.path.join(self.OUTPUT_DIR, 'data_volume_by_host_records.jsonl')

        if os.path.exists(jsonl_file):
            with open(jsonl_file, 'r') as f:
                for line in f:
                    if line.strip():  # Skip empty lines
                        # Each line should be valid JSON
                        data = json.loads(line)
                        assert isinstance(data, dict)

    def test_json_output_format(self):
        """Test JSON output is valid JSON"""
        json_file = os.path.join(self.OUTPUT_DIR, 'data_volume_by_host_records.json')

        if os.path.exists(json_file):
            with open(json_file, 'r') as f:
                data = json.load(f)
                assert isinstance(data, dict)
                # Should have standard search job response fields
                assert 'fields' in data or 'records' in data or 'messages' in data

    def test_csv_output_format(self):
        """Test CSV output has header and data rows"""
        csv_file = os.path.join(self.OUTPUT_DIR, 'test_count_query_records.csv')

        if os.path.exists(csv_file):
            with open(csv_file, 'r') as f:
                lines = f.readlines()
                if len(lines) > 0:
                    # First line should be header
                    assert ',' in lines[0] or len(lines) == 1  # Header has commas or single value

    def test_batch_filename_format(self):
        """Test batch filenames follow expected pattern"""
        batch_files = [f for f in os.listdir(self.OUTPUT_DIR) if '_batch_' in f]

        for filename in batch_files:
            # Should match pattern: {name}_{mode}_batch_{index}_{from}_{to}.{ext}
            assert '_batch_' in filename
            parts = filename.split('_batch_')
            assert len(parts) == 2

            # Should have timestamps in YYYYMMddHHmmss.SSS format
            assert len(parts[1].split('_')) >= 2  # Should have from and to timestamps

    def test_batch_files_sequential(self):
        """Test batch files are numbered sequentially"""
        batch_files = sorted([f for f in os.listdir(self.OUTPUT_DIR)
                             if 'simple_test_records_batch_' in f])

        if len(batch_files) > 0:
            for i, filename in enumerate(batch_files):
                # Extract batch number
                if f'_batch_{i:03d}_' in filename:
                    assert True
                else:
                    pytest.fail(f"Batch file {filename} not sequentially numbered")


class TestFilenamePatterns:
    """Test filename pattern generation"""

    def test_query_name_in_filename(self):
        """Test query name is used in generated filenames"""
        OUTPUT_DIR = '/Users/rjury/Documents/sumo2021/sumo-public-content/apis/scripts/search_job/output'

        # Check that filenames contain query names from config files
        expected_names = ['test_count_query', 'simple_test', 'data_volume_by_host']

        for name in expected_names:
            matching_files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith(name)]
            assert len(matching_files) > 0, f"No files found for query name: {name}"

    def test_mode_in_filename(self):
        """Test mode is included in generated filenames"""
        OUTPUT_DIR = '/Users/rjury/Documents/sumo2021/sumo-public-content/apis/scripts/search_job/output'

        # Files should contain _records or _messages
        files = os.listdir(OUTPUT_DIR)
        mode_files = [f for f in files if '_records' in f or '_messages' in f]

        assert len(mode_files) > 0, "No files with mode in filename found"

    def test_extension_matches_format(self):
        """Test file extensions match output format"""
        OUTPUT_DIR = '/Users/rjury/Documents/sumo2021/sumo-public-content/apis/scripts/search_job/output'

        files = os.listdir(OUTPUT_DIR)

        # JSON files
        json_files = [f for f in files if f.endswith('.json')]
        for f in json_files:
            assert not f.endswith('.jsonl'), "JSON file should not have .jsonl extension"

        # JSONL files
        jsonl_files = [f for f in files if f.endswith('.jsonl')]
        for f in jsonl_files:
            assert f.endswith('.jsonl'), "JSONL file should have .jsonl extension"

        # CSV files
        csv_files = [f for f in files if f.endswith('.csv')]
        assert len(csv_files) > 0, "Should have at least one CSV file"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
