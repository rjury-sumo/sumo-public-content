#!/usr/bin/env python3

import subprocess
import json
import requests
import time
import sys
import argparse
import logging
from datetime import datetime, timezone
import uuid

def setup_logging(verbose=False):
    """Configure logging for the application"""
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Disable urllib3 warnings for self-signed certificates
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    
    return logging.getLogger('otlp_log_sender')

class OTLPLogSender:
    def __init__(self, endpoint="http://localhost:4318/v1/logs", service_name="flog-generator", delay=0.1, 
                 otlp_headers=None, otlp_attributes=None, telemetry_attributes=None):
        self.endpoint = endpoint
        self.service_name = service_name
        self.delay = delay
        self.otlp_headers = otlp_headers or {}
        self.otlp_attributes = otlp_attributes or {}
        self.telemetry_attributes = telemetry_attributes or {}
        self.session = requests.Session()
        self.logger = logging.getLogger(f'{__name__}.{self.__class__.__name__}')
        
        # Note: OTLP HTTP/JSON typically uses HTTP on port 4318
        # Use HTTPS (port 4318) only if your collector is specifically configured for it
        # For HTTPS, change endpoint to https://localhost:4318/v1/logs and uncomment below:
        
        # self.session.verify = False  # Only for self-signed certs
        # import urllib3
        # urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def parse_flog_line(self, line):
        """Parse a single flog line and extract relevant information"""
        try:
            # Try to parse as JSON first (if flog outputs JSON)
            log_data = json.loads(line)
            return {
                'message': log_data.get('message', line),
                'level': log_data.get('level', 'INFO'),
                'timestamp': log_data.get('time', datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))
            }
        except json.JSONDecodeError:
            # If not JSON, treat as plain text log
            return {
                'message': line.strip(),
                'level': 'INFO',
                'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            }
    
    def create_otlp_payload(self, log_entry):
        """Create OTLP-compliant JSON payload"""
        # Convert timestamp to nanoseconds since Unix epoch (always in UTC)
        try:
            if log_entry['timestamp'].endswith('Z'):
                # ISO format with Z suffix (UTC)
                dt = datetime.fromisoformat(log_entry['timestamp'][:-1]).replace(tzinfo=timezone.utc)
            else:
                # Try to parse as ISO format and assume UTC if no timezone info
                try:
                    dt = datetime.fromisoformat(log_entry['timestamp'])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    # Fallback to current UTC time
                    dt = datetime.now(timezone.utc)
            timestamp_ns = int(dt.timestamp() * 1_000_000_000)
        except:
            # Fallback to current UTC time
            timestamp_ns = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
        
        # Build resource attributes - start with defaults then add custom OTLP attributes
        resource_attributes = [
            {
                "key": "service.name",
                "value": {"stringValue": self.service_name}
            },
            {
                "key": "service.version",
                "value": {"stringValue": "1.0.0"}
            }
        ]
        
        # Add custom OTLP attributes to resource
        for key, value in self.otlp_attributes.items():
            resource_attributes.append({
                "key": key,
                "value": self._convert_attribute_value(value)
            })
        
        # Build log record attributes - start with defaults then add telemetry attributes
        log_attributes = [
            {
                "key": "log.source",
                "value": {"stringValue": "flog"}
            }
        ]
        
        # Add custom telemetry attributes to log record
        for key, value in self.telemetry_attributes.items():
            log_attributes.append({
                "key": key,
                "value": self._convert_attribute_value(value)
            })
        
        payload = {
            "resourceLogs": [
                {
                    "resource": {
                        "attributes": resource_attributes
                    },
                    "scopeLogs": [
                        {
                            "scope": {
                                "name": "flog-processor",
                                "version": "1.0.0"
                            },
                            "logRecords": [
                                {
                                    "timeUnixNano": str(timestamp_ns),
                                    "severityText": log_entry['level'],
                                    "severityNumber": self.get_severity_number(log_entry['level']),
                                    "body": {
                                        "stringValue": log_entry['message']
                                    },
                                    "attributes": log_attributes,
                                    "traceId": "",
                                    "spanId": ""
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        return payload
    
    def _convert_attribute_value(self, value):
        """Convert attribute value to OTLP format"""
        if isinstance(value, str):
            return {"stringValue": value}
        elif isinstance(value, bool):
            return {"boolValue": value}
        elif isinstance(value, int):
            return {"intValue": value}
        elif isinstance(value, float):
            return {"doubleValue": value}
        else:
            # Fallback to string representation
            return {"stringValue": str(value)}
    
    def get_severity_number(self, level):
        """Convert log level to OTLP severity number"""
        level_map = {
            'TRACE': 1,
            'DEBUG': 5,
            'INFO': 9,
            'WARN': 13,
            'WARNING': 13,
            'ERROR': 17,
            'FATAL': 21,
            'CRITICAL': 21
        }
        return level_map.get(level.upper(), 9)  # Default to INFO
    
    def send_log(self, payload):
        """Send OTLP payload to the endpoint"""
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'otlp-log-sender/1.0'
        }
        
        # Add custom OTLP headers
        headers.update(self.otlp_headers)
        
        try:
            response = self.session.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                self.logger.debug("Log sent successfully")
            else:
                self.logger.error(f"Failed to send log: {response.status_code} - {response.text}")
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed: {e}")
    
    def process_flog_output(self, flog_cmd):
        """Execute flog and process its output"""
        self.logger.info(f"Executing: {' '.join(flog_cmd)}")
        self.logger.info(f"Sending logs to: {self.endpoint}")
        
        try:
            # Start flog process
            process = subprocess.Popen(
                flog_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            line_count = 0
            
            # Process each line of output
            for line in iter(process.stdout.readline, ''):
                if line.strip():  # Skip empty lines
                    line_count += 1
                    # Detailed log line processing at DEBUG level
                    self.logger.debug(f"Processing line {line_count}: {line.strip()[:100]}...")
                    
                    # Parse the log line
                    log_entry = self.parse_flog_line(line)
                    
                    # Create OTLP payload
                    otlp_payload = self.create_otlp_payload(log_entry)
                    
                    # Send to endpoint
                    self.send_log(otlp_payload)
                    
                    # Configurable delay to avoid overwhelming the endpoint
                    if self.delay > 0:
                        time.sleep(self.delay)
            
            # Wait for process to complete
            process.wait()
            
            if process.returncode != 0:
                stderr_output = process.stderr.read()
                self.logger.error(f"flog process failed with return code {process.returncode}: {stderr_output}")
                return False, line_count
            
            self.logger.info(f"Completed processing {line_count} log lines")
            return True, line_count
            
        except FileNotFoundError:
            self.logger.error("'flog' command not found. Please install flog first.")
            self.logger.error("Installation: go install github.com/mingrammer/flog@latest")
            return False, 0
        except KeyboardInterrupt:
            self.logger.warning("Interrupted by user")
            if 'process' in locals():
                process.terminate()
            return False, 0
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            return False, 0
    
    def run_recurring_executions(self, flog_cmd, wait_time, max_executions):
        """Run flog executions on a recurring schedule"""
        execution_count = 0
        total_logs_processed = 0
        start_time = datetime.now(timezone.utc)
        
        self.logger.info("Starting recurring flog executions")
        self.logger.info(f"Wait time between executions: {wait_time}s")
        self.logger.info(f"Max executions: {'∞ (until stopped)' if max_executions == 0 else max_executions}")
        self.logger.info(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        try:
            while max_executions == 0 or execution_count < max_executions:
                execution_count += 1
                execution_start = datetime.now(timezone.utc)
                
                self.logger.info(f"Execution #{execution_count} started at {execution_start.strftime('%H:%M:%S UTC')}")
                
                # Process flog output
                success, line_count = self.process_flog_output(flog_cmd)
                total_logs_processed += line_count
                
                execution_end = datetime.now(timezone.utc)
                execution_duration = (execution_end - execution_start).total_seconds()
                
                if success:
                    self.logger.info(f"Execution #{execution_count} completed in {execution_duration:.1f}s ({line_count} logs)")
                else:
                    self.logger.warning(f"Execution #{execution_count} failed after {execution_duration:.1f}s")
                
                # Check if we should continue
                if max_executions > 0 and execution_count >= max_executions:
                    break
                
                # Wait before next execution
                if wait_time > 0:
                    self.logger.info(f"Waiting {wait_time}s before next execution...")
                    time.sleep(wait_time)
                
        except KeyboardInterrupt:
            self.logger.warning(f"Stopped by user after {execution_count} executions")
        
        # Summary
        end_time = datetime.now(timezone.utc)
        total_duration = (end_time - start_time).total_seconds()
        
        self.logger.info("EXECUTION SUMMARY:")
        self.logger.info(f"Total executions: {execution_count}")
        self.logger.info(f"Total logs processed: {total_logs_processed}")
        self.logger.info(f"Total runtime: {total_duration:.1f}s")
        self.logger.info(f"Average logs per execution: {total_logs_processed/execution_count if execution_count > 0 else 0:.1f}")
        self.logger.info(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        self.logger.info(f"Ended: {end_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        return execution_count > 0

def parse_key_value_pairs(values_list):
    """Parse key=value pairs from command line arguments"""
    result = {}
    logger = logging.getLogger('otlp_log_sender.parser')
    
    if not values_list:
        return result
    
    for item in values_list:
        if '=' not in item:
            logger.warning(f"Ignoring malformed attribute '{item}' (expected format: key=value)")
            continue
            
        key, value = item.split('=', 1)
        key = key.strip()
        value = value.strip()
        
        # Remove surrounding quotes if present
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        
        # Convert value to appropriate type
        if value.lower() == 'true':
            result[key] = True
        elif value.lower() == 'false':
            result[key] = False
        else:
            # Try to parse as integer
            try:
                result[key] = int(value)
            except ValueError:
                # Try to parse as float
                try:
                    result[key] = float(value)
                except ValueError:
                    # Keep as string
                    result[key] = value
    
    return result

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='OTLP Log Sender for flog - Generate logs and send to OTLP endpoint',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s                              # Default: 200 logs over 10 seconds (single execution)
  %(prog)s -n 100 -s 5s                 # 100 logs over 5 seconds (single execution)
  %(prog)s -f apache_common -n 50       # 50 Apache common format logs (single execution)
  %(prog)s -f json -n 100 --no-loop     # 100 JSON logs, no infinite loop (single execution)
  %(prog)s --otlp-endpoint https://collector:4318/v1/logs  # Custom endpoint (single execution)
  
  # Recurring executions:
  %(prog)s --wait-time 30 --max-executions 10    # Run 10 times, 30s between executions
  %(prog)s --wait-time 60 --max-executions 0     # Run forever, 60s between executions  
  %(prog)s -n 50 -s 5s --wait-time 10 --max-executions 5  # 5 executions: 50 logs/5s, 10s wait
  
  # Custom attributes and headers:
  %(prog)s --otlp-attributes environment=production --otlp-attributes region=us-east-1
  %(prog)s --telemetry-attributes app=web-server --telemetry-attributes debug=true
  %(prog)s --otlp-header "Authorization=Bearer token123" --otlp-header "X-Custom=value"
  
Supported log formats:
  apache_common, apache_combined, apache_error, rfc3164, rfc5424, common_log, json
        '''
    )
    
    # OTLP-specific options (matching telemetrygen)
    parser.add_argument(
        '--otlp-endpoint', 
        default='http://localhost:4318/v1/logs',
        help='Destination endpoint for exporting logs (default: http://localhost:4318/v1/logs)'
    )
    
    parser.add_argument(
        '--otlp-attributes',
        action='append',
        help='Custom OTLP resource attributes. Format: key=value, key=true, key=false, or key=123. Can be repeated.'
    )
    
    parser.add_argument(
        '--otlp-header',
        action='append', 
        help='Custom header for OTLP requests. Format: key=value. Can be repeated.'
    )
    
    parser.add_argument(
        '--telemetry-attributes',
        action='append',
        help='Custom telemetry log attributes. Format: key=value, key=true, key=false, or key=123. Can be repeated.'
    )
    
    parser.add_argument(
        '--service-name',
        default='flog-generator',
        help='Service name for OTLP resource attributes (default: flog-generator)'
    )
    
    parser.add_argument(
        '--delay',
        type=float,
        default=0.1,
        help='Delay between log sends in seconds (default: 0.1)'
    )
    
    # Recurring execution options
    parser.add_argument(
        '--wait-time',
        type=float,
        default=0,
        help='Wait time in seconds between flog executions (default: 0 - single execution)'
    )
    
    parser.add_argument(
        '--max-executions',
        type=int,
        default=1,
        help='Number of flog executions (0 = run until manually stopped, default: 1)'
    )
    
    # flog options - main parameters
    parser.add_argument(
        '-f', '--format',
        choices=['apache_common', 'apache_combined', 'apache_error', 'rfc3164', 'rfc5424', 'common_log', 'json'],
        default='apache_common',
        help='Log format (default: apache_common)'
    )
    
    parser.add_argument(
        '-n', '--number',
        type=int,
        default=200,
        help='Number of log lines to generate (default: 200)'
    )
    
    parser.add_argument(
        '-s', '--sleep',
        default='10s',
        help='Duration to generate logs over (e.g., 10s, 2m, 1h) (default: 10s)'
    )
    
    # flog options - behavior
    parser.add_argument(
        '--no-loop',
        action='store_true',
        help='Disable infinite loop mode'
    )
    
    parser.add_argument(
        '-d', '--delay-flog',
        help='Delay between log generation (flog -d option)'
    )
    
    # flog options - rate limiting
    parser.add_argument(
        '-r', '--rate',
        type=int,
        help='Rate limit in logs per second'
    )
    
    parser.add_argument(
        '-p', '--bytes',
        type=int,
        help='Bytes limit per second'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    return parser.parse_args()

def build_flog_command(args):
    """Build flog command from parsed arguments"""
    cmd = ['flog']
    
    # Add format
    if args.format:
        cmd.extend(['-f', args.format])
    
    # Add number of logs
    if args.number:
        cmd.extend(['-n', str(args.number)])
    
    # Add sleep duration
    if args.sleep:
        cmd.extend(['-s', args.sleep])
    
    # Add no-loop flag
    if args.no_loop:
        cmd.append('--no-loop')
    
    # Add flog delay
    if args.delay_flog:
        cmd.extend(['-d', args.delay_flog])
    
    # Add rate limiting
    if args.rate:
        cmd.extend(['-r', str(args.rate)])
    
    if args.bytes:
        cmd.extend(['-p', str(args.bytes)])
    
    return cmd

def main():
    # Parse command line arguments
    args = parse_args()
    
    # Setup logging based on verbose flag
    logger = setup_logging(verbose=args.verbose)
    
    logger.info("OTLP Log Sender for flog")
    
    # Parse custom attributes and headers
    otlp_attributes = parse_key_value_pairs(args.otlp_attributes)
    telemetry_attributes = parse_key_value_pairs(args.telemetry_attributes) 
    otlp_headers = parse_key_value_pairs(args.otlp_header)
    
    # Log configuration details
    logger.info(f"Configuration:")
    logger.info(f"  Endpoint: {args.otlp_endpoint}")
    logger.info(f"  Service Name: {args.service_name}")
    logger.info(f"  Send Delay: {args.delay}s")
    logger.info(f"  Log Format: {args.format}")
    logger.info(f"  Log Count: {args.number}")
    logger.info(f"  Duration: {args.sleep}")
    logger.info(f"  Wait Time: {args.wait_time}s")
    logger.info(f"  Max Executions: {'∞' if args.max_executions == 0 else args.max_executions}")
    
    if otlp_attributes:
        logger.info(f"  OTLP Attributes: {otlp_attributes}")
    if telemetry_attributes:
        logger.info(f"  Telemetry Attributes: {telemetry_attributes}")
    if otlp_headers:
        logger.debug(f"  Custom Headers: {otlp_headers}")  # Headers may contain sensitive data
    
    # Build flog command
    flog_cmd = build_flog_command(args)
    logger.debug(f"Built flog command: {' '.join(flog_cmd)}")
    
    # Create sender instance with custom parameters
    sender = OTLPLogSender(
        endpoint=args.otlp_endpoint,
        service_name=args.service_name,
        delay=args.delay,
        otlp_headers=otlp_headers,
        otlp_attributes=otlp_attributes,
        telemetry_attributes=telemetry_attributes
    )
    
    # Determine execution mode
    if args.wait_time > 0 or args.max_executions != 1:
        # Recurring execution mode
        logger.info("Using recurring execution mode")
        success = sender.run_recurring_executions(flog_cmd, args.wait_time, args.max_executions)
    else:
        # Single execution mode
        logger.info("Using single execution mode")
        success, _ = sender.process_flog_output(flog_cmd)
    
    if success:
        logger.info("All logs processed successfully")
    else:
        logger.error("Log processing completed with errors")
        sys.exit(1)

if __name__ == "__main__":
    main()