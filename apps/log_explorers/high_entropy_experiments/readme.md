# High-Entropy String Redaction Tool

A configurable Python tool for detecting and redacting sensitive data in text using entropy analysis and pattern matching. Designed for processing log files, user input, and any text containing potentially sensitive information like timestamps, UUIDs, account IDs, IP addresses, and AWS hostnames.

## 🚀 Quick Start

```bash
# Process a file (redacted output only)
python3 entropy.py input.txt

# Comparative mode (see original vs redacted)
python3 entropy.py -c input.txt

# Comparative mode with condensed asterisks
python3 entropy.py -c test_strings.txt --condense-asterisks

# Process stdin
cat logfile.txt | python3 entropy.py

# Save to file
python3 entropy.py -c -o output.txt input.txt

# Run comprehensive tests
python3 test_entropy.py
```

## 📋 Features

### Core Capabilities
- **Shannon Entropy Analysis**: Identifies high-randomness strings using information theory
- **Pattern-Based Detection**: Recognizes structured data like timestamps, IPs, and AWS hostnames
- **Word Preservation**: Protects common English words and technical terms from redaction
- **Selective Redaction**: AWS hostname patterns preserve domain parts while redacting sensitive IDs
- **Two Redaction Methods**: Token-level (default, more reliable) and sliding window (more granular)

### Supported Pattern Types
- **Datetime/Timestamps**: ISO 8601, human-readable dates, epoch timestamps
- **IP Addresses**: IPv4, IPv6, with contextual detection
- **AWS Resources**: EC2 hostnames, RDS endpoints, CloudFront distributions, API Gateway
- **UUIDs and Hex Sequences**: Full and partial UUID detection
- **Account IDs and Random Strings**: Long numeric and alphanumeric sequences

## ⚙️ Configuration

The tool requires three YAML configuration files:

### `common_words.yaml`
Contains word lists and patterns to preserve during redaction:
```yaml
common_words:
  - admin, alert, application, auth, backup, cache
  - database, debug, deployment, development, device
  # ... extensive list of technical and common terms

word_patterns:
  prefixes: [pre, post, anti, auto, co, de, dis, ...]
  suffixes: [able, ible, al, ed, er, est, ful, ic, ...]
```

### `entropy_settings.yaml`
Controls detection behavior and thresholds:
```yaml
entropy_detection:
  default_threshold: 2.5        # Higher = less sensitive
  word_pattern_bonus: 0.5       # Extra threshold for word-like patterns
  min_length: 4                 # Minimum string length to consider
  window_size: 6                # Sliding window size

output_formatting:
  # Note: condense_asterisks is now a command-line option only

pattern_detection:
  detect_timestamps: true       # Enable timestamp detection
  detect_ip_addresses: true     # Enable IP address detection
  detect_aws_hostnames: true    # Enable AWS hostname detection
```

### `redaction_patterns.yaml`
Defines regex patterns for structured data detection:
```yaml
datetime_patterns:
  human_readable_datetime: |
    (Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\w+\s+\d{4}
  date_yyyy_mm_dd: '\d{4}/\d{2}/\d{2}'
  # ... more datetime patterns

aws_selective_patterns:
  ec2_public_ipv4_dns:
    pattern: 'ec2-(\d{1,3}-\d{1,3}-\d{1,3}-\d{1,3})(\..*\.amazonaws\.com)'
    replacement: 'ec2-*\2'
  # ... selective redaction patterns
```

## 🛠️ Command-Line Options

```bash
python3 entropy.py [options] [input_file]

Options:
  -c, --comparative           Show original and redacted (default: redacted only)
  -o OUTPUT, --output OUTPUT  Output file path (default: stdout)
  --method {token,sliding}    Redaction method (default: token)
  --threshold THRESHOLD       Override entropy threshold
  --min-length MIN_LENGTH     Override minimum length
  --condense-asterisks        Condense consecutive asterisks to single *

Positional:
  input_file                  Input file path (use "-" or omit for stdin)
```

## 📚 Library Usage

```python
from entropy import redact_sensitive_data, load_config

# Load configuration (required)
load_config()

# Basic usage (recommended)
result = redact_sensitive_data("model-scheduler-667689996-jd4g7")
# Output: "model-scheduler-*********-*****"

# Alternative methods
from entropy import redact_high_entropy_tokens, redact_high_entropy_strings

# Token-level approach (more reliable)
result = redact_high_entropy_tokens("text")

# Sliding window approach (more granular)
result = redact_high_entropy_strings("text")
```

## 🎯 Examples

### Input/Output Examples

```bash
# AWS CloudTrail path
Original: s3://aws-cloudtrail-logs-123456789012-us-east-1/CloudTrail/...
Redacted: s3://aws-cloudtrail-logs-************-us-east-1/CloudTrail/...

# EC2 hostname (selective redaction)
Original: ec2-198-51-100-1.compute-1.amazonaws.com
Redacted: ec2-*.compute-1.amazonaws.com

# Human-readable datetime
Original: Wed Sep 24 11:17:52 NZST 2025
Redacted: Wed Sep 24 ******** NZST 2025

# UUID
Original: uuid-550e8400-e29b-41d4-a716-446655440000
Redacted: uuid-********-****-****-****-************

# Mixed content preserving common words
Original: database-connection-string-server-production-guid-550e8400
Redacted: database-connection-string-server-production-guid-********

# With --condense-asterisks flag
Original: user-session-abc123def456-another-xyz789abc123
Redacted: user-session-*-another-*

# Without --condense-asterisks flag (default)
Original: user-session-abc123def456-another-xyz789abc123
Redacted: user-session-************-another-************
```

## 🧪 Testing

Run the comprehensive test suite:

```bash
python3 test_entropy.py
```

The test suite includes:
- AWS S3 CloudTrail and CloudWatch paths
- Container and Docker paths
- Windows and Linux file paths
- Database connection strings
- IP addresses and network identifiers
- Various timestamp and datetime formats

## 🔧 How It Works

### Entropy Analysis
The tool uses Shannon entropy to measure randomness in character distributions:
- **High entropy** (>2.5 bits): Random-looking strings like `abc123def456`
- **Low entropy** (<2.0 bits): Structured text like common words
- **Pattern boosting**: Adds entropy score for mixed case, alphanumeric combinations

### Two-Phase Detection
1. **Pattern-based detection**: Identifies structured data using regex patterns
2. **Entropy-based analysis**: Catches random strings missed by patterns

### Word Preservation
- Extensive dictionary of common English and technical terms
- Pattern matching for word prefixes/suffixes
- Contextual analysis to avoid redacting legitimate words

## 📁 File Structure

```
high_entropy_experiments/
├── entropy.py                    # Main script with CLI
├── test_entropy.py              # Comprehensive test suite
├── common_words.yaml            # Word lists and patterns
├── entropy_settings.yaml        # Detection and output settings
├── redaction_patterns.yaml      # Regex patterns for structured data
└── readme.md                    # This documentation
```

## ⚠️ Configuration Requirements

The script will exit with an error if any required configuration files or settings are missing. This ensures consistent behavior and prevents fallback to hardcoded values.

Required sections in YAML files:
- `common_words.yaml`: `common_words`, `word_patterns`
- `entropy_settings.yaml`: `entropy_detection`, `output_formatting`
- `redaction_patterns.yaml`: Pattern sections as needed

## 🎛️ Customization

### Adding Custom Patterns
Add to `redaction_patterns.yaml`:
```yaml
custom_patterns:
  my_identifier: 'pattern-\d{6}-[a-z]{4}'
```

### Adjusting Sensitivity
Modify `entropy_settings.yaml`:
```yaml
entropy_detection:
  default_threshold: 3.0    # Less sensitive (higher threshold)
  min_length: 6            # Only redact longer strings
```

### Adding Words to Preserve
Add to `common_words.yaml`:
```yaml
common_words:
  - mycompany
  - customterm
  - projectname
```

This tool provides enterprise-grade sensitive data redaction with full configurability and no hardcoded assumptions about your data formats.