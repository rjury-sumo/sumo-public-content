#!/usr/bin/env python3

import subprocess
import json
import requests
import time
import sys
import argparse
from datetime import datetime, timezone
import uuid

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
                print(f"✓ Log sent successfully")
            else:
                print(f"✗ Failed to send log: {response.status_code} - {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"✗ Request failed: {e}")
    
    def process_flog_output(self, flog_cmd):
        """Execute flog and process its output"""
        print(f"Executing: {' '.join(flog_cmd)}")
        print(f"Sending logs to: {self.endpoint}")
        print("-" * 50)
        
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
                    print(f"Processing line {line_count}: {line.strip()[:100]}...")
                    
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
                print(f"flog process failed: {stderr_output}")
                return False
            
            print(f"\nCompleted processing {line_count} log lines")
            return True
            
        except FileNotFoundError:
            print("Error: 'flog' command not found. Please install flog first.")
            print("Installation: go install github.com/mingrammer/flog@latest")
            return False
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            if 'process' in locals():
                process.terminate()
            return False
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False

def parse_key_value_pairs(values_list):
    """Parse key=value pairs from command line arguments"""
    result = {}
    if not values_list:
        return result
    
    for item in values_list:
        if '=' not in item:
            print(f"Warning: Ignoring malformed attribute '{item}' (expected format: key=value)")
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
  %(prog)s                              # Default: 200 logs over 10 seconds
  %(prog)s -n 100 -s 5s                 # 100 logs over 5 seconds  
  %(prog)s -f apache_common -n 50       # 50 Apache common format logs
  %(prog)s -f json -n 100 --no-loop     # 100 JSON logs, no infinite loop
  %(prog)s --otlp-endpoint https://collector:4318/v1/logs  # Custom endpoint
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
    
    print("OTLP Log Sender for flog")
    print("=" * 30)
    
    # Parse custom attributes and headers
    otlp_attributes = parse_key_value_pairs(args.otlp_attributes)
    telemetry_attributes = parse_key_value_pairs(args.telemetry_attributes) 
    otlp_headers = parse_key_value_pairs(args.otlp_header)
    
    if args.verbose:
        print(f"Configuration:")
        print(f"  Endpoint: {args.otlp_endpoint}")
        print(f"  Service Name: {args.service_name}")
        print(f"  Send Delay: {args.delay}s")
        print(f"  Log Format: {args.format}")
        print(f"  Log Count: {args.number}")
        print(f"  Duration: {args.sleep}")
        if otlp_attributes:
            print(f"  OTLP Attributes: {otlp_attributes}")
        if telemetry_attributes:
            print(f"  Telemetry Attributes: {telemetry_attributes}")
        if otlp_headers:
            print(f"  Custom Headers: {otlp_headers}")
        print()
    
    # Build flog command
    flog_cmd = build_flog_command(args)
    
    # Create sender instance with custom parameters
    sender = OTLPLogSender(
        endpoint=args.otlp_endpoint,
        service_name=args.service_name,
        delay=args.delay,
        otlp_headers=otlp_headers,
        otlp_attributes=otlp_attributes,
        telemetry_attributes=telemetry_attributes
    )
    
    # Process flog output
    success = sender.process_flog_output(flog_cmd)
    
    if success:
        print("✓ All logs processed successfully")
    else:
        print("✗ Log processing completed with errors")
        sys.exit(1)

if __name__ == "__main__":
    main()