"""
Enhanced entropy-based string redaction with configurable word detection.

This script identifies and redacts high-entropy strings while preserving common words.
Configuration is loaded from three required YAML files in the same directory:
- 'common_words.yaml': Contains word lists and patterns
- 'entropy_settings.yaml': Contains thresholds and behavior settings
- 'redaction_patterns.yaml': Contains regex patterns for detecting sensitive data

Usage:
    # Command-line usage:
    python3 entropy.py input.txt                    # Process file, output redacted text
    python3 entropy.py -c input.txt                 # Comparative mode (original vs redacted)
    cat logfile.txt | python3 entropy.py           # Process stdin
    python3 entropy.py -c -o output.txt input.txt  # Save to file

    # In your code (recommended - token-based approach):
    from entropy import redact_sensitive_data
    result = redact_sensitive_data("file-path-document-final-version-abc123")

    # Alternative approaches:
    from entropy import redact_high_entropy_tokens, redact_high_entropy_strings
    result = redact_high_entropy_tokens("text")  # Token-level (more reliable)
    result = redact_high_entropy_strings("text")  # Sliding window (more granular)

    # Run tests:
    python3 test_entropy.py  # Comprehensive test suite

Required Configuration Files:
    common_words.yaml:
    - common_words: List of words to never redact
    - word_patterns: Prefixes and suffixes for word detection

    entropy_settings.yaml:
    - entropy_detection: Thresholds and analysis parameters
    - output_formatting: Output format options (e.g., asterisk condensation)
    - pattern_detection: Enable/disable specific pattern types
    - heuristic_scoring: Scoring adjustments for mixed patterns

    redaction_patterns.yaml:
    - datetime_patterns: Date/time string patterns
    - ip_address_patterns: IPv4/IPv6 address patterns
    - aws_ec2_patterns: AWS hostname patterns
    - aws_selective_patterns: AWS service patterns with selective redaction
    - custom_patterns: User-defined patterns

Note: The script will exit with an error if any required YAML configuration file is missing.
"""

import math
from collections import Counter
import re
import yaml
import os

# Global configuration variables loaded from YAML
CONFIG = None
COMMON_WORDS = set()
COMMON_PREFIXES = set()
COMMON_SUFFIXES = set()
ENTROPY_SETTINGS = {}
REDACTION_PATTERNS = []
AWS_SELECTIVE_PATTERNS = []
EXACT_MATCH_PATTERNS = []
HUMAN_READABLE_DATETIME_PATTERNS = []

def load_config(words_config_path="common_words.yaml", entropy_config_path="entropy_settings.yaml", patterns_config_path="redaction_patterns.yaml"):
    """Load configuration from YAML files."""
    global CONFIG, COMMON_WORDS, COMMON_PREFIXES, COMMON_SUFFIXES, ENTROPY_SETTINGS, REDACTION_PATTERNS, AWS_SELECTIVE_PATTERNS, EXACT_MATCH_PATTERNS, HUMAN_READABLE_DATETIME_PATTERNS

    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    words_file_path = os.path.join(script_dir, words_config_path)
    entropy_file_path = os.path.join(script_dir, entropy_config_path)
    patterns_file_path = os.path.join(script_dir, patterns_config_path)

    # Load common words configuration
    try:
        with open(words_file_path, 'r', encoding='utf-8') as f:
            words_config = yaml.safe_load(f)

        # Load common words into a set for fast lookup
        common_words_list = words_config.get('common_words', [])
        COMMON_WORDS = set(word.lower() for word in common_words_list if isinstance(word, str))

        # Load pattern matching configuration
        patterns = words_config.get('word_patterns', {})
        COMMON_PREFIXES = set(patterns.get('prefixes', []))
        COMMON_SUFFIXES = set(patterns.get('suffixes', []))

    except FileNotFoundError:
        print(f"Error: Required config file '{words_file_path}' not found.")
        exit(1)
    except yaml.YAMLError as e:
        print(f"Error: Failed to parse words YAML config: {e}")
        exit(1)

    # Load entropy settings configuration
    try:
        with open(entropy_file_path, 'r', encoding='utf-8') as f:
            entropy_config = yaml.safe_load(f)

        # Extract settings from the structured config - all required
        detection_settings = entropy_config.get('entropy_detection')

        if not detection_settings:
            print(f"Error: Missing 'entropy_detection' section in '{entropy_file_path}'")
            exit(1)

        # Extract required settings with validation
        required_detection_keys = ['default_threshold', 'word_pattern_bonus', 'min_length', 'window_size']

        for key in required_detection_keys:
            if key not in detection_settings:
                print(f"Error: Missing required setting 'entropy_detection.{key}' in '{entropy_file_path}'")
                exit(1)

        # Set settings directly from YAML without fallbacks
        # Note: condense_asterisks is now a command-line option only
        ENTROPY_SETTINGS = {
            'default_threshold': detection_settings['default_threshold'],
            'word_pattern_bonus': detection_settings['word_pattern_bonus'],
            'min_length': detection_settings['min_length'],
            'window_size': detection_settings['window_size']
        }

        # Store the full config for potential future use
        CONFIG = entropy_config

    except FileNotFoundError:
        print(f"Error: Required config file '{entropy_file_path}' not found.")
        exit(1)
    except yaml.YAMLError as e:
        print(f"Error: Failed to parse entropy YAML config: {e}")
        exit(1)

    # Load redaction patterns configuration
    try:
        with open(patterns_file_path, 'r', encoding='utf-8') as f:
            patterns_config = yaml.safe_load(f)

        # Build redaction patterns list from enabled groups
        REDACTION_PATTERNS = []
        enabled_groups = patterns_config.get('pattern_groups', {}).get('enabled', [])

        for group_name in enabled_groups:
            if group_name == 'aws_selective_patterns':
                # Handle selective patterns separately
                continue

            group_patterns = patterns_config.get(group_name, {})
            for pattern_name, pattern_value in group_patterns.items():
                if isinstance(pattern_value, str):
                    REDACTION_PATTERNS.append(pattern_value)

        # Load AWS selective patterns
        AWS_SELECTIVE_PATTERNS = []
        selective_patterns = patterns_config.get('aws_selective_patterns', {})
        for pattern_name, pattern_config in selective_patterns.items():
            if isinstance(pattern_config, dict) and 'pattern' in pattern_config and 'replacement' in pattern_config:
                AWS_SELECTIVE_PATTERNS.append((pattern_config['pattern'], pattern_config['replacement']))

        # Load exact match patterns for token validation
        EXACT_MATCH_PATTERNS = []
        exact_patterns = patterns_config.get('exact_match_patterns', {})
        for pattern_name, pattern_value in exact_patterns.items():
            if isinstance(pattern_value, str):
                EXACT_MATCH_PATTERNS.append(pattern_value)

        # Load human-readable datetime patterns
        HUMAN_READABLE_DATETIME_PATTERNS = []
        human_datetime_patterns = patterns_config.get('human_readable_datetime_patterns', {})
        for pattern_name, pattern_value in human_datetime_patterns.items():
            if isinstance(pattern_value, str):
                HUMAN_READABLE_DATETIME_PATTERNS.append(pattern_value)

        # Add custom patterns if any
        custom_patterns = patterns_config.get('custom_patterns', {})
        if custom_patterns:
            for pattern_name, pattern_value in custom_patterns.items():
                if isinstance(pattern_value, str) and not pattern_name.startswith('#'):
                    REDACTION_PATTERNS.append(pattern_value)

    except FileNotFoundError:
        print(f"Error: Required config file '{patterns_file_path}' not found.")
        exit(1)
    except yaml.YAMLError as e:
        print(f"Error: Failed to parse patterns YAML config: {e}")
        exit(1)


def is_common_word(word):
    """Check if a word is a common English word or technical term."""
    return word.lower() in COMMON_WORDS

def is_always_redact_pattern(text):
    """
    Check if text matches patterns that should always be redacted regardless of word detection.
    This includes timestamps, UUIDs, long numeric sequences, etc.
    """
    # UUID patterns (8-4-4-4-12 hex digits)
    uuid_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    if re.match(uuid_pattern, text):
        return True

    # Partial UUID segments (hex characters that are likely random)
    # Must be 6+ chars OR contain both letters and numbers OR not be common values
    if len(text) >= 4 and re.match(r'^[0-9a-fA-F]+$', text):
        # Exclude common words that happen to be hex
        common_hex_words = {'beef', 'cafe', 'dead', 'face', 'fade', 'feed', 'deed', 'bead', 'deaf'}

        # If it's all numeric, apply stricter rules
        if text.isdigit():
            num_val = int(text)
            # Don't redact years, small port numbers, or common small numbers
            if (1900 <= num_val <= 2100 or  # Years
                1 <= num_val <= 1000 or      # Small numbers
                num_val in {8080, 8443, 3000, 5432, 3306, 5000, 9000}):  # Common ports
                return False

        # If it's 6+ characters or contains both letters and digits, likely random
        if (len(text) >= 6 or
            (any(c.isdigit() for c in text) and any(c.isalpha() for c in text))):
            if text.lower() not in common_hex_words:
                return True

    # Long numeric sequences (8+ digits, often account IDs, timestamps)
    # But exclude reasonable years (1900-2100) and short numeric values
    if len(text) >= 8 and text.isdigit():
        return True

    # Also catch 6-7 digit sequences that are likely IDs
    if len(text) >= 6 and text.isdigit():
        # Exclude years and reasonable small numbers
        num_val = int(text)
        if not (1900 <= num_val <= 2100 or num_val <= 100):
            return True

    # Epoch timestamps (10 or 13 digits)
    if text.isdigit():
        # 10-digit epoch (seconds since 1970) - roughly 2001-2038 range
        if len(text) == 10 and 1000000000 <= int(text) <= 2147483647:
            return True
        # 13-digit epoch (milliseconds since 1970)
        if len(text) == 13 and 1000000000000 <= int(text) <= 2147483647000:
            return True

    # Date/time string patterns from YAML configuration
    for pattern in EXACT_MATCH_PATTERNS:
        if re.match(pattern, text):
            return True

    # Human-readable datetime strings from YAML configuration
    for pattern in HUMAN_READABLE_DATETIME_PATTERNS:
        if re.match(pattern, text, re.IGNORECASE):
            return True

    # Mixed alphanumeric sequences that look like tokens/hashes (6+ chars, mixed case/digits)
    if (len(text) >= 6 and
        any(c.isdigit() for c in text) and
        any(c.isalpha() for c in text) and
        not any(c in 'aeiouAEIOU' for c in text[1:-1])): # No vowels in middle (unlikely to be words)
        return True

    # Base64-like patterns (ends with = or ==, or long alphanumeric)
    if (len(text) >= 8 and
        (text.endswith('=') or text.endswith('==')) and
        re.match(r'^[A-Za-z0-9+/]+=*$', text)):
        return True

    return False

def has_word_pattern(text):
    """
    Check if text follows common word patterns that suggest it's a real word
    rather than random characters.
    """
    text_lower = text.lower()

    # Check for prefix patterns
    for prefix in COMMON_PREFIXES:
        if text_lower.startswith(prefix) and len(text) > len(prefix) + 2:
            return True

    # Check for suffix patterns
    for suffix in COMMON_SUFFIXES:
        if text_lower.endswith(suffix) and len(text) > len(suffix) + 2:
            return True

    # Check for vowel distribution (real words usually have vowels)
    vowels = set('aeiou')
    vowel_count = sum(1 for c in text_lower if c in vowels)
    vowel_ratio = vowel_count / len(text) if text else 0

    # Real words typically have 20-50% vowels
    if 0.2 <= vowel_ratio <= 0.5:
        return True

    return False

def calculate_entropy(text):
    """Calculate Shannon entropy of a string."""
    if not text:
        return 0
    
    # Count character frequencies
    char_counts = Counter(text.lower())
    length = len(text)
    
    # Calculate entropy
    entropy = 0
    for count in char_counts.values():
        probability = count / length
        if probability > 0:
            entropy -= probability * math.log2(probability)
    
    return entropy

def is_high_entropy_segment(segment, entropy_threshold=None, min_length=None):
    """
    Determine if a segment has high entropy and is not a common word.

    Args:
        segment: String segment to analyze
        entropy_threshold: Minimum entropy to consider "high" (uses config default if None)
        min_length: Minimum length to consider for redaction (uses config default if None)

    Returns:
        bool: True if segment should be redacted
    """
    # Use configured defaults if not specified
    if entropy_threshold is None:
        entropy_threshold = ENTROPY_SETTINGS.get('default_threshold', 2.5)
    if min_length is None:
        min_length = ENTROPY_SETTINGS.get('min_length', 4)

    if len(segment) < min_length:
        return False

    # Check for patterns that should always be redacted (timestamps, UUIDs, etc.)
    if is_always_redact_pattern(segment):
        return True

    # Check if it's a common word - if so, don't redact
    if is_common_word(segment):
        return False

    # Check if it has word-like patterns - if so, be more conservative
    if has_word_pattern(segment):
        # For word-like patterns, require higher entropy to redact
        word_pattern_bonus = ENTROPY_SETTINGS.get('word_pattern_bonus', 0.5)
        entropy_threshold = entropy_threshold + word_pattern_bonus

    entropy = calculate_entropy(segment)

    # Additional heuristics for common high-entropy patterns
    has_mixed_case = any(c.isupper() for c in segment) and any(c.islower() for c in segment)
    has_digits_and_letters = any(c.isdigit() for c in segment) and any(c.isalpha() for c in segment)
    digit_ratio = sum(1 for c in segment if c.isdigit()) / len(segment)

    # Boost entropy score for mixed patterns
    adjusted_entropy = entropy
    if has_mixed_case:
        adjusted_entropy += 0.3
    if has_digits_and_letters:
        adjusted_entropy += 0.4
    if digit_ratio > 0.6:  # Mostly numeric sequences
        adjusted_entropy += 0.2

    return adjusted_entropy >= entropy_threshold

def redact_high_entropy_strings(text, entropy_threshold=None, min_length=None, window_size=None, condense_asterisks=None):
    """
    Redact high-entropy substrings from text using a sliding window approach.

    Args:
        text: Input string to process
        entropy_threshold: Minimum entropy to consider "high" (uses config default if None)
        min_length: Minimum length of segments to consider (uses config default if None)
        window_size: Size of sliding window for analysis (uses config default if None)
        condense_asterisks: If True, condense consecutive asterisks to single asterisk (uses config default if None)

    Returns:
        str: Text with high-entropy segments replaced with asterisks
    """
    # Use configured defaults if not specified
    if entropy_threshold is None:
        entropy_threshold = ENTROPY_SETTINGS.get('default_threshold', 2.5)
    if min_length is None:
        min_length = ENTROPY_SETTINGS.get('min_length', 4)
    if window_size is None:
        window_size = ENTROPY_SETTINGS.get('window_size', 6)
    if condense_asterisks is None:
        condense_asterisks = False
    if len(text) < min_length:
        return text
    
    # Split text into tokens (preserve separators)
    tokens = re.findall(r'[a-zA-Z0-9]+|[^a-zA-Z0-9]', text)
    
    redacted_tokens = []
    
    for token in tokens:
        if not re.match(r'^[a-zA-Z0-9]+$', token):
            # Keep separators as-is
            redacted_tokens.append(token)
            continue
        
        if len(token) < min_length:
            # Keep short tokens as-is
            redacted_tokens.append(token)
            continue
        
        # Use sliding window to find high-entropy regions
        redacted_chars = list(token)
        i = 0
        
        while i <= len(token) - window_size:
            window = token[i:i + window_size]
            
            if is_high_entropy_segment(window, entropy_threshold, min_length):
                # Mark this region for redaction and extend it
                start = i
                end = i + window_size
                
                # Extend backwards if previous chars are also high entropy
                while start > 0:
                    extended_window = token[start-1:end]
                    if is_high_entropy_segment(extended_window, entropy_threshold, min_length):
                        start -= 1
                    else:
                        break
                
                # Extend forwards if next chars are also high entropy
                while end < len(token):
                    extended_window = token[start:end+1]
                    if is_high_entropy_segment(extended_window, entropy_threshold, min_length):
                        end += 1
                    else:
                        break
                
                # Redact the identified region
                for j in range(start, end):
                    redacted_chars[j] = '*'
                
                # Skip ahead to avoid overlapping redactions
                i = end
            else:
                i += 1
        
        redacted_tokens.append(''.join(redacted_chars))

    result = ''.join(redacted_tokens)

    # Condense consecutive asterisks if requested
    if condense_asterisks:
        result = re.sub(r'\*+', '*', result)

    return result

# Alternative simpler approach focusing on token-level analysis
def redact_high_entropy_tokens(text, entropy_threshold=None, min_length=None, condense_asterisks=None):
    """
    Simpler approach that analyzes and redacts entire tokens.
    Also handles multi-token datetime patterns.

    Args:
        text: Input string to process
        entropy_threshold: Minimum entropy to consider "high" (uses config default if None)
        min_length: Minimum length of tokens to consider (uses config default if None)
        condense_asterisks: If True, condense consecutive asterisks to single asterisk (uses config default if None)

    Returns:
        str: Text with high-entropy tokens replaced with asterisks
    """
    # Use configured defaults if not specified
    if entropy_threshold is None:
        entropy_threshold = ENTROPY_SETTINGS.get('default_threshold', 2.5)
    if min_length is None:
        min_length = ENTROPY_SETTINGS.get('min_length', 4)
    if condense_asterisks is None:
        condense_asterisks = False

    # First, check for multi-token datetime patterns that should be redacted entirely
    datetime_replacements = []

    # Use patterns loaded from YAML configuration
    for pattern in REDACTION_PATTERNS:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        for match in matches:
            replacement = '*' * len(match.group())
            datetime_replacements.append((match.start(), match.end(), replacement))

    # Selective redaction for AWS service hostnames (preserve service/domain parts)
    for pattern, replacement in AWS_SELECTIVE_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Apply datetime replacements first
    if datetime_replacements:
        # Sort by start position in reverse order to avoid index shifts
        datetime_replacements.sort(key=lambda x: x[0], reverse=True)
        result_text = text
        for start, end, replacement in datetime_replacements:
            result_text = result_text[:start] + replacement + result_text[end:]
        text = result_text

    # Split on common separators while preserving them
    parts = re.split(r'([^a-zA-Z0-9]+)', text)

    redacted_parts = []
    for part in parts:
        if re.match(r'^[a-zA-Z0-9]+$', part) and is_high_entropy_segment(part, entropy_threshold, min_length):
            # Redact high-entropy alphanumeric tokens
            redacted_parts.append('*' * len(part))
        else:
            redacted_parts.append(part)

    result = ''.join(redacted_parts)

    # Condense consecutive asterisks if requested
    if condense_asterisks:
        result = re.sub(r'\*+', '*', result)

    return result

def redact_sensitive_data(text, entropy_threshold=None, min_length=None, condense_asterisks=None):
    """
    Default function for redacting sensitive data using the token-based approach.

    This is the recommended function to use as it provides the most reliable results
    by analyzing complete tokens and using pattern-based detection for structured data.

    Args:
        text: Input string to process
        entropy_threshold: Minimum entropy to consider "high" (uses config default if None)
        min_length: Minimum length of tokens to consider (uses config default if None)
        condense_asterisks: If True, condense consecutive asterisks to single asterisk (uses config default if None)

    Returns:
        str: Text with high-entropy tokens and structured patterns replaced with asterisks
    """
    return redact_high_entropy_tokens(text, entropy_threshold, min_length, condense_asterisks)

def main():
    """Command-line interface for processing files or stdin."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description='Redact high-entropy strings from text files or stdin',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s input.txt                    # Redact file, output redacted strings only
  %(prog)s -c input.txt                 # Comparative mode (original vs redacted)
  cat logfile.txt | %(prog)s            # Process stdin
  %(prog)s -c -o output.txt input.txt   # Save comparative output to file
        """
    )

    parser.add_argument('input_file', nargs='?',
                       help='Input file path (use "-" or omit for stdin)')
    parser.add_argument('-c', '--comparative', action='store_true',
                       help='Show both original and redacted strings (default: redacted only)')
    parser.add_argument('-o', '--output',
                       help='Output file path (default: stdout)')
    parser.add_argument('--method', choices=['token', 'sliding'], default='token',
                       help='Redaction method (default: token)')
    parser.add_argument('--threshold', type=float,
                       help='Override entropy threshold from config')
    parser.add_argument('--min-length', type=int,
                       help='Override minimum length from config')
    parser.add_argument('--condense-asterisks', action='store_true',
                       help='Condense consecutive asterisks to single asterisk')

    args = parser.parse_args()

    # Load configuration
    try:
        load_config()
    except SystemExit:
        sys.stderr.write("Error: Failed to load configuration files. See above for details.\n")
        sys.exit(1)

    # Choose redaction function
    if args.method == 'token':
        redact_func = redact_high_entropy_tokens
    else:
        redact_func = redact_high_entropy_strings

    # Setup input
    if args.input_file and args.input_file != '-':
        try:
            input_file = open(args.input_file, 'r', encoding='utf-8')
        except IOError as e:
            sys.stderr.write(f"Error opening input file: {e}\n")
            sys.exit(1)
    else:
        input_file = sys.stdin

    # Setup output
    if args.output:
        try:
            output_file = open(args.output, 'w', encoding='utf-8')
        except IOError as e:
            sys.stderr.write(f"Error opening output file: {e}\n")
            sys.exit(1)
    else:
        output_file = sys.stdout

    # Process input line by line
    try:
        for line_num, line in enumerate(input_file, 1):
            line = line.rstrip('\n\r')
            if not line.strip():  # Skip empty lines
                continue

            try:
                # Apply redaction with optional parameter overrides
                kwargs = {}
                if args.threshold is not None:
                    kwargs['entropy_threshold'] = args.threshold
                if args.min_length is not None:
                    kwargs['min_length'] = args.min_length
                if args.condense_asterisks:
                    kwargs['condense_asterisks'] = True

                redacted = redact_func(line, **kwargs)

                if args.comparative:
                    output_file.write(f"Original:  {line}\n")
                    output_file.write(f"Redacted:  {redacted}\n")
                    output_file.write("\n")
                else:
                    output_file.write(f"{redacted}\n")

            except Exception as e:
                sys.stderr.write(f"Error processing line {line_num}: {e}\n")

    except KeyboardInterrupt:
        sys.stderr.write("\nInterrupted by user\n")
        sys.exit(1)
    finally:
        if input_file != sys.stdin:
            input_file.close()
        if output_file != sys.stdout:
            output_file.close()

if __name__ == "__main__":
    main()