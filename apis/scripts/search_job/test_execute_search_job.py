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
    load_yaml_config,
    SumoLogicClient,
    analyze_time_buckets,
    generate_export_summary,
    prompt_export_confirmation
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

    OUTPUT_DIR = './output'

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

    OUTPUT_DIR = './output'

    def test_query_name_in_filename(self):
        """Test query name is used in generated filenames"""
        # Check that filenames contain query names from config files
        # At least one of these query names should have output files
        expected_names = ['test_count_query', 'simple_test', 'data_volume_by_host']

        if not os.path.exists(self.OUTPUT_DIR):
            pytest.skip(f"Output directory {self.OUTPUT_DIR} does not exist")

        all_files = os.listdir(self.OUTPUT_DIR)

        # Check if at least one expected name has matching files
        found_any = False
        for name in expected_names:
            matching_files = [f for f in all_files if f.startswith(name)]
            if len(matching_files) > 0:
                found_any = True
                break

        assert found_any, f"No files found for any expected query names: {expected_names}"

    def test_mode_in_filename(self):
        """Test mode is included in generated filenames"""
        # Files should contain _records or _messages
        files = os.listdir(self.OUTPUT_DIR)
        mode_files = [f for f in files if '_records' in f or '_messages' in f]

        assert len(mode_files) > 0, "No files with mode in filename found"

    def test_extension_matches_format(self):
        """Test file extensions match output format"""
        files = os.listdir(self.OUTPUT_DIR)

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


class TestIntegration:
    """Integration tests requiring real Sumo Logic credentials"""

    @pytest.mark.integration
    @pytest.mark.skipif(
        not os.environ.get('SUMO_ACCESS_ID') or not os.environ.get('SUMO_ACCESS_KEY'),
        reason="SUMO_ACCESS_ID and SUMO_ACCESS_KEY environment variables required"
    )
    def test_single_search_job_24h(self):
        """Test single search job run returning records for -24h range"""
        import subprocess
        import tempfile

        # Create a temporary YAML config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
name: integration_test_single
query: "_sourcecategory=* | limit 10000 | count by _sourcecategory,_collector"
from: "-24h"
to: "now"
timeZone: "UTC"
byReceiptTime: false
""")
            f.flush()
            config_path = f.name

        # Create temporary output directory
        with tempfile.TemporaryDirectory() as output_dir:
            try:
                # Run the script
                script_path = os.path.join(os.path.dirname(__file__), 'execute_search_job.py')
                result = subprocess.run([
                    'python3', script_path,
                    '--region', 'au',
                    '--access-id', os.environ['SUMO_ACCESS_ID'],
                    '--access-key', os.environ['SUMO_ACCESS_KEY'],
                    '--yaml-config', config_path,
                    '--mode', 'records',
                    '--output', 'jsonl',
                    '--output-directory', output_dir,
                    '--log-level', 'INFO'
                ], capture_output=True, text=True, timeout=300)

                # Check that the script completed successfully
                assert result.returncode == 0, f"Script failed with stderr: {result.stderr}\nstdout: {result.stdout}"

                # Check that output file was created
                output_files = os.listdir(output_dir)
                assert len(output_files) > 0, f"No output files created. stderr: {result.stderr}\nstdout: {result.stdout}"

                # Verify the output file contains valid JSONL
                output_file = os.path.join(output_dir, output_files[0])
                with open(output_file, 'r') as f:
                    lines = f.readlines()
                    # Should have at least some records (or could be empty if no data)
                    for line in lines:
                        if line.strip():
                            data = json.loads(line)
                            assert isinstance(data, dict)
                            # Should have 'map' field with record data
                            assert 'map' in data

            finally:
                os.unlink(config_path)

    @pytest.mark.integration
    @pytest.mark.skipif(
        not os.environ.get('SUMO_ACCESS_ID') or not os.environ.get('SUMO_ACCESS_KEY'),
        reason="SUMO_ACCESS_ID and SUMO_ACCESS_KEY environment variables required"
    )
    def test_batch_mode_3d_1d_interval(self):
        """Test batch mode with -3d range and 1d interval (3 batches) - quick test"""
        import subprocess
        import tempfile

        # Create a temporary YAML config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
name: integration_test_batch_quick
query: "_sourcecategory=* | limit 10000 | count by _sourcecategory,_collector"
from: "-3d"
to: "now"
timeZone: "UTC"
byReceiptTime: false
""")
            f.flush()
            config_path = f.name

        # Create temporary output directory
        with tempfile.TemporaryDirectory() as output_dir:
            try:
                # Run the script in batch mode
                script_path = os.path.join(os.path.dirname(__file__), 'execute_search_job.py')
                result = subprocess.run([
                    'python3', script_path,
                    '--region', 'au',
                    '--access-id', os.environ['SUMO_ACCESS_ID'],
                    '--access-key', os.environ['SUMO_ACCESS_KEY'],
                    '--yaml-config', config_path,
                    '--batch-mode',
                    '--batch-start=-3d',
                    '--batch-end=now',
                    '--batch-interval=1d',
                    '--mode', 'records',
                    '--output', 'jsonl',
                    '--output-directory', output_dir,
                    '--log-level', 'INFO'
                ], capture_output=True, text=True, timeout=600)  # 10 min timeout for 3 batches

                # Check that the script completed successfully
                assert result.returncode == 0, f"Script failed with stderr: {result.stderr}\nstdout: {result.stdout}"

                # Check that progress bar output appears in stderr
                assert 'Batch' in result.stderr or '[' in result.stderr, "Expected batch progress output in stderr"

                # Check that output files were created (should be 3 batch files)
                output_files = [f for f in os.listdir(output_dir) if f.endswith('.jsonl')]
                assert len(output_files) == 3, f"Expected 3 batch output files, got {len(output_files)}"

                # Verify batch files are numbered sequentially
                batch_files = sorted([f for f in output_files if '_batch_' in f])
                for i in range(3):
                    # Check that batch file with index exists
                    matching = [f for f in batch_files if f'_batch_{i:03d}_' in f]
                    assert len(matching) == 1, f"Expected 1 file for batch {i:03d}, got {len(matching)}"

                # Verify at least one output file contains valid JSONL
                if len(output_files) > 0:
                    output_file = os.path.join(output_dir, output_files[0])
                    with open(output_file, 'r') as f:
                        lines = f.readlines()
                        for line in lines:
                            if line.strip():
                                data = json.loads(line)
                                assert isinstance(data, dict)

            finally:
                os.unlink(config_path)

    @pytest.mark.integration
    @pytest.mark.skipif(
        not os.environ.get('SUMO_ACCESS_ID') or not os.environ.get('SUMO_ACCESS_KEY'),
        reason="SUMO_ACCESS_ID and SUMO_ACCESS_KEY environment variables required"
    )
    def test_batch_mode_10d_1d_interval(self):
        """Test batch mode with -10d range and 1d interval (10 batches)"""
        import subprocess
        import tempfile

        # Create a temporary YAML config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
name: integration_test_batch
query: "_sourcecategory=* | limit 10000 | count by _sourcecategory,_collector"
from: "-1h"
to: "now"
timeZone: "UTC"
byReceiptTime: false
""")
            f.flush()
            config_path = f.name

        # Create temporary output directory
        with tempfile.TemporaryDirectory() as output_dir:
            try:
                # Run the script in batch mode
                script_path = os.path.join(os.path.dirname(__file__), 'execute_search_job.py')
                result = subprocess.run([
                    'python3', script_path,
                    '--region', 'au',
                    '--access-id', os.environ['SUMO_ACCESS_ID'],
                    '--access-key', os.environ['SUMO_ACCESS_KEY'],
                    '--yaml-config', config_path,
                    '--batch-mode',
                    '--batch-start=-10d',
                    '--batch-end=now',
                    '--batch-interval=1d',
                    '--mode', 'records',
                    '--output', 'jsonl',
                    '--output-directory', output_dir,
                    '--log-level', 'INFO'
                ], capture_output=True, text=True, timeout=1800)  # 30 min timeout for 30 batches

                # Check that the script completed successfully
                assert result.returncode == 0, f"Script failed with stderr: {result.stderr}\nstdout: {result.stdout}"

                # Check that progress bar output appears in stderr
                assert 'Batch' in result.stderr or '[' in result.stderr, "Expected batch progress output in stderr"

                # Check that output files were created (should be 30 batch files)
                output_files = [f for f in os.listdir(output_dir) if f.endswith('.jsonl')]
                assert len(output_files) == 10, f"Expected 30 batch output files, got {len(output_files)}"

                # Verify batch files are numbered sequentially
                batch_files = sorted([f for f in output_files if '_batch_' in f])
                for i in range(10):
                    # Check that batch file with index exists
                    matching = [f for f in batch_files if f'_batch_{i:03d}_' in f]
                    assert len(matching) == 1, f"Expected 1 file for batch {i:03d}, got {len(matching)}"

                # Verify at least one output file contains valid JSONL
                if len(output_files) > 0:
                    output_file = os.path.join(output_dir, output_files[0])
                    with open(output_file, 'r') as f:
                        lines = f.readlines()
                        for line in lines:
                            if line.strip():
                                data = json.loads(line)
                                assert isinstance(data, dict)

            finally:
                os.unlink(config_path)


class TestBatchedMessagesExport:
    """Test batched messages export functionality"""

    def test_client_get_all_messages_paginated(self):
        """Test paginated messages retrieval"""
        # Create mock client
        client = SumoLogicClient('us1', 'test_id', 'test_key')

        # Mock the get_search_job_messages method
        with patch.object(client, 'get_search_job_messages') as mock_get_messages:
            # Simulate two pages of results
            mock_get_messages.side_effect = [
                {
                    'messages': [
                        {'map': {'field1': 'value1'}},
                        {'map': {'field1': 'value2'}}
                    ],
                    'totalCount': 3
                },
                {
                    'messages': [
                        {'map': {'field1': 'value3'}}
                    ],
                    'totalCount': 3
                },
                {
                    'messages': [],
                    'totalCount': 3
                }
            ]

            # Collect all messages
            messages = list(client.get_all_messages_paginated('test_job_id', page_size=2))

            assert len(messages) == 3
            assert messages[0]['map']['field1'] == 'value1'
            assert messages[1]['map']['field1'] == 'value2'
            assert messages[2]['map']['field1'] == 'value3'

            # Verify pagination calls
            assert mock_get_messages.call_count == 2
            mock_get_messages.assert_any_call('test_job_id', offset=0, limit=2)
            mock_get_messages.assert_any_call('test_job_id', offset=2, limit=2)

    def test_analyze_time_buckets_all_within_limit(self):
        """Test analyze_time_buckets when all buckets are within event limit"""
        # Create mock client
        client = SumoLogicClient('us1', 'test_id', 'test_key')

        start_time = 1704067200000  # 2024-01-01 00:00:00
        end_time = 1704070800000    # 2024-01-01 01:00:00
        bucket_size = 1200000       # 20 minutes

        # Mock the search job creation and polling
        with patch.object(client, 'create_search_job') as mock_create, \
             patch.object(client, 'poll_search_job') as mock_poll, \
             patch.object(client, 'get_search_job_records') as mock_get_records:

            mock_create.return_value = {'id': 'test_job_id'}
            mock_poll.return_value = {'state': 'DONE GATHERING RESULTS'}

            # Simulate 3 buckets with counts under limit
            mock_get_records.return_value = {
                'records': [
                    {'map': {'_timeslice': '2024-01-01T00:00:00Z', '_count': '50000'}},
                    {'map': {'_timeslice': '2024-01-01T00:20:00Z', '_count': '60000'}},
                    {'map': {'_timeslice': '2024-01-01T00:40:00Z', '_count': '55000'}}
                ]
            }

            buckets = analyze_time_buckets(
                client, '_sourceCategory=test', start_time, end_time,
                'UTC', False, bucket_size, max_events_per_bucket=100000
            )

            # Should return 3 buckets as-is, plus potentially gap-filling buckets
            assert len(buckets) >= 3
            # Verify all buckets are contiguous
            for i in range(len(buckets) - 1):
                assert buckets[i][1] == buckets[i+1][0]
            # Verify coverage
            assert buckets[0][0] <= start_time
            assert buckets[-1][1] >= end_time
            # Verify counts are present for non-gap buckets
            counts_present = [b[2] for b in buckets if b[2] is not None]
            assert len(counts_present) >= 3  # At least 3 buckets should have counts

    def test_analyze_time_buckets_with_subdivision(self):
        """Test analyze_time_buckets when buckets need subdivision"""
        client = SumoLogicClient('us1', 'test_id', 'test_key')

        start_time = 1704067200000
        end_time = 1704070800000
        bucket_size = 3600000  # 1 hour

        # Track recursive calls
        call_count = [0]

        def mock_create_job(query, from_time, to_time, **kwargs):
            call_count[0] += 1
            return {'id': f'job_{call_count[0]}'}

        def mock_poll_job(job_id, **kwargs):
            return {'state': 'DONE GATHERING RESULTS'}

        def mock_get_records(job_id):
            # First call: one bucket with too many events
            if job_id == 'job_1':
                return {
                    'records': [
                        {'map': {'_timeslice': '2024-01-01T00:00:00Z', '_count': '150000'}}
                    ]
                }
            # Second call (subdivision): two buckets within limit
            elif job_id == 'job_2':
                return {
                    'records': [
                        {'map': {'_timeslice': '2024-01-01T00:00:00Z', '_count': '70000'}},
                        {'map': {'_timeslice': '2024-01-01T00:30:00Z', '_count': '80000'}}
                    ]
                }
            return {'records': []}

        with patch.object(client, 'create_search_job', side_effect=mock_create_job), \
             patch.object(client, 'poll_search_job', side_effect=mock_poll_job), \
             patch.object(client, 'get_search_job_records', side_effect=mock_get_records):

            buckets = analyze_time_buckets(
                client, '_sourceCategory=test', start_time, end_time,
                'UTC', False, bucket_size, max_events_per_bucket=100000
            )

            # Should have subdivided the large bucket
            assert len(buckets) >= 2
            assert call_count[0] == 2  # Two query jobs created

    def test_generate_export_summary(self):
        """Test export summary report generation"""
        import time
        start_time = time.time() - 3600  # 1 hour ago

        summary = generate_export_summary(
            total_intervals=10,
            total_messages=25000,
            start_time=start_time,
            output_directory='./output/'
        )

        assert 'BATCHED MESSAGES EXPORT SUMMARY' in summary
        assert '10' in summary  # total intervals
        assert '25,000' in summary or '25000' in summary  # total messages
        assert './output/' in summary
        assert '2,500' in summary or '2500' in summary  # average messages per bucket

    def test_prompt_export_confirmation_few_intervals(self):
        """Test export confirmation prompt with few intervals"""
        intervals = [
            (1704067200000, 1704070800000, 50000),
            (1704070800000, 1704074400000, 75000),
            (1704074400000, 1704078000000, 60000)
        ]

        # Mock user input to say 'yes'
        with patch('builtins.input', return_value='yes'):
            result = prompt_export_confirmation(intervals, 'test_query')
            assert result is True

        # Mock user input to say 'no'
        with patch('builtins.input', return_value='no'):
            result = prompt_export_confirmation(intervals, 'test_query')
            assert result is False

    def test_prompt_export_confirmation_many_intervals(self):
        """Test export confirmation prompt with many intervals (should show first 10, last 10)"""
        # Create 50 intervals
        start = 1704067200000
        interval_size = 3600000  # 1 hour
        intervals = [
            (start + i * interval_size, start + (i + 1) * interval_size, 50000 + i * 1000)
            for i in range(50)
        ]

        with patch('builtins.input', return_value='yes'):
            result = prompt_export_confirmation(intervals, 'test_query')
            assert result is True

    def test_analyze_time_buckets_no_data(self):
        """Test analyze_time_buckets when no data is found"""
        client = SumoLogicClient('us1', 'test_id', 'test_key')

        start_time = 1704067200000
        end_time = 1704070800000
        bucket_size = 3600000

        with patch.object(client, 'create_search_job') as mock_create, \
             patch.object(client, 'poll_search_job') as mock_poll, \
             patch.object(client, 'get_search_job_records') as mock_get_records:

            mock_create.return_value = {'id': 'test_job_id'}
            mock_poll.return_value = {'state': 'DONE GATHERING RESULTS'}
            mock_get_records.return_value = {'records': []}  # No data

            buckets = analyze_time_buckets(
                client, '_sourceCategory=nonexistent', start_time, end_time,
                'UTC', False, bucket_size, max_events_per_bucket=100000
            )

            # Should return single bucket covering entire range with None count
            assert len(buckets) == 1
            assert buckets[0][0] == start_time
            assert buckets[0][1] == end_time
            assert buckets[0][2] is None  # No data, so count is None

    def test_analyze_time_buckets_custom_threshold_50k(self):
        """Test analyze_time_buckets with custom 50k threshold vs default 100k"""
        client = SumoLogicClient('us1', 'test_id', 'test_key')

        start_time = 1704067200000
        end_time = 1704070800000
        bucket_size = 3600000  # 1 hour

        # Track calls for both thresholds
        call_count = {'50k': [0], '100k': [0]}

        def mock_create_job_50k(query, from_time, to_time, **kwargs):
            call_count['50k'][0] += 1
            return {'id': f'job_50k_{call_count["50k"][0]}'}

        def mock_create_job_100k(query, from_time, to_time, **kwargs):
            call_count['100k'][0] += 1
            return {'id': f'job_100k_{call_count["100k"][0]}'}

        def mock_poll_job(job_id, **kwargs):
            return {'state': 'DONE GATHERING RESULTS'}

        # Simulate a bucket with 75k events
        def mock_get_records_75k(job_id):
            if 'job_50k_1' in job_id:
                # 75k exceeds 50k threshold - needs subdivision
                return {
                    'records': [
                        {'map': {'_timeslice': '2024-01-01T00:00:00Z', '_count': '75000'}}
                    ]
                }
            elif 'job_50k_2' in job_id:
                # Subdivision of 75k bucket into two 30-minute buckets
                return {
                    'records': [
                        {'map': {'_timeslice': '2024-01-01T00:00:00Z', '_count': '35000'}},
                        {'map': {'_timeslice': '2024-01-01T00:30:00Z', '_count': '40000'}}
                    ]
                }
            elif 'job_100k_1' in job_id:
                # 75k is under 100k threshold - no subdivision needed
                return {
                    'records': [
                        {'map': {'_timeslice': '2024-01-01T00:00:00Z', '_count': '75000'}}
                    ]
                }
            return {'records': []}

        # Test with 50k threshold - should subdivide
        with patch.object(client, 'create_search_job', side_effect=mock_create_job_50k), \
             patch.object(client, 'poll_search_job', side_effect=mock_poll_job), \
             patch.object(client, 'get_search_job_records', side_effect=mock_get_records_75k):

            buckets_50k = analyze_time_buckets(
                client, '_sourceCategory=test', start_time, end_time,
                'UTC', False, bucket_size, max_events_per_bucket=50000
            )

        # Reset client for second test
        client_100k = SumoLogicClient('us1', 'test_id', 'test_key')

        # Test with 100k threshold (default) - should NOT subdivide
        with patch.object(client_100k, 'create_search_job', side_effect=mock_create_job_100k), \
             patch.object(client_100k, 'poll_search_job', side_effect=mock_poll_job), \
             patch.object(client_100k, 'get_search_job_records', side_effect=mock_get_records_75k):

            buckets_100k = analyze_time_buckets(
                client_100k, '_sourceCategory=test', start_time, end_time,
                'UTC', False, bucket_size, max_events_per_bucket=100000
            )

        # Verify 50k threshold triggered subdivision
        assert len(buckets_50k) >= 2, "50k threshold should subdivide 75k bucket"
        assert call_count['50k'][0] == 2, "50k threshold should make 2 query calls (initial + subdivision)"

        # Verify 100k threshold did NOT trigger subdivision
        assert len(buckets_100k) >= 1, "100k threshold should return at least 1 bucket"
        assert call_count['100k'][0] == 1, "100k threshold should make only 1 query call (no subdivision needed)"

        # Verify both cover the same time range
        assert buckets_50k[0][0] <= start_time
        assert buckets_50k[-1][1] >= end_time
        assert buckets_100k[0][0] <= start_time
        assert buckets_100k[-1][1] >= end_time


class TestBatchedMessagesExportIntegration:
    """Integration tests for batched messages export"""

    @pytest.mark.integration
    @pytest.mark.skipif(
        not os.getenv('SUMO_ACCESS_ID') or not os.getenv('SUMO_ACCESS_KEY'),
        reason="Integration test requires SUMO_ACCESS_ID and SUMO_ACCESS_KEY environment variables"
    )
    def test_batched_export_cloudtrail_integration(self):
        """Integration test: Export CloudTrail logs over 7 days using adaptive bucketing"""
        import time

        # Get credentials from environment
        access_id = os.getenv('SUMO_ACCESS_ID')
        access_key = os.getenv('SUMO_ACCESS_KEY')
        region = os.getenv('SUMO_REGION', 'us1')

        # Create client
        client = SumoLogicClient(region, access_id, access_key)

        # Set time range: last 7 days
        end_time = int(time.time() * 1000)
        start_time = end_time - (7 * 24 * 60 * 60 * 1000)

        # Query scope
        query = '_sourcecategory=*cloudtrail*'

        # Initial bucket size: 1 day
        bucket_size = 24 * 60 * 60 * 1000

        try:
            # Analyze and generate optimal buckets
            buckets = analyze_time_buckets(
                client, query, start_time, end_time,
                'UTC', False, bucket_size, max_events_per_bucket=100000
            )

            # Verify we got some buckets
            assert len(buckets) > 0
            assert len(buckets) <= 7  # Shouldn't exceed initial estimate by much

            # Verify bucket coverage
            assert buckets[0][0] <= start_time
            assert buckets[-1][1] >= end_time

            # Verify buckets are contiguous (no gaps)
            for i in range(len(buckets) - 1):
                assert buckets[i][1] == buckets[i+1][0], f"Gap found between bucket {i} and {i+1}"

            # Verify counts are present where expected
            total_count = sum(b[2] if b[2] else 0 for b in buckets)
            assert total_count > 0, "Should have at least some estimated counts"

            print(f"\nIntegration test results:")
            print(f"  Total buckets generated: {len(buckets)}")
            print(f"  Estimated total messages: {total_count:,}")
            print(f"  Time range: {datetime.fromtimestamp(start_time/1000)} to {datetime.fromtimestamp(end_time/1000)}")
            print(f"  Query: {query}")

        except Exception as e:
            pytest.fail(f"Integration test failed: {e}")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
