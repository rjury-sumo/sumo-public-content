#!/usr/bin/env python3
"""
Sumo Logic Organizations Management API CLI

This script provides a command-line interface to interact with Sumo Logic's
Organizations Management API GET endpoints.

API Reference: https://organizations.sumologic.com/api/docs
Base URL: https://organizations.sumologic.com/api/

This API is used to manage child organizations in a parent organization account.
It requires a parent organization account with appropriate permissions.
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from urllib.parse import urljoin, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class CredentialStore:
    """Secure credential storage for named profiles"""

    def __init__(self):
        """Initialize credential store with secure location"""
        # Use XDG_CONFIG_HOME or fallback to ~/.config
        config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        self.config_dir = Path(config_home) / 'sumo-logic'
        self.credentials_file = self.config_dir / 'organizations_credentials.json'
        self.default_profile_file = self.config_dir / 'organizations_default_profile.txt'
        self._ensure_secure_storage()

    def _ensure_secure_storage(self):
        """Create config directory with secure permissions"""
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True, mode=0o700)
        else:
            # Ensure directory has secure permissions
            os.chmod(self.config_dir, 0o700)

    def _get_credentials(self):
        """Load all credentials from storage"""
        if not self.credentials_file.exists():
            return {}

        # Ensure file has secure permissions
        os.chmod(self.credentials_file, 0o600)

        try:
            with open(self.credentials_file, 'r') as f:
                # Decode base64 encoded credentials for basic obfuscation
                data = json.load(f)
                credentials = {}
                for profile, creds in data.items():
                    credentials[profile] = {
                        'access_id': base64.b64decode(creds['access_id'].encode()).decode(),
                        'access_key': base64.b64decode(creds['access_key'].encode()).decode(),
                        'deployment': creds['deployment']
                    }
                return credentials
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Warning: Corrupted credentials file: {e}", file=sys.stderr)
            return {}

    def _save_credentials(self, credentials):
        """Save all credentials to storage"""
        # Encode credentials with base64 for basic obfuscation
        encoded = {}
        for profile, creds in credentials.items():
            encoded[profile] = {
                'access_id': base64.b64encode(creds['access_id'].encode()).decode(),
                'access_key': base64.b64encode(creds['access_key'].encode()).decode(),
                'deployment': creds['deployment']
            }

        with open(self.credentials_file, 'w') as f:
            json.dump(encoded, f, indent=2)

        # Ensure file has secure permissions (owner read/write only)
        os.chmod(self.credentials_file, 0o600)

    def save_profile(self, profile_name, access_id, access_key, deployment):
        """
        Save a named credential profile

        Args:
            profile_name (str): Name for this credential profile
            access_id (str): Sumo Logic access ID
            access_key (str): Sumo Logic access key
            deployment (str): Deployment ID
        """
        credentials = self._get_credentials()
        credentials[profile_name] = {
            'access_id': access_id,
            'access_key': access_key,
            'deployment': deployment
        }
        self._save_credentials(credentials)

    def load_profile(self, profile_name):
        """
        Load a named credential profile

        Args:
            profile_name (str): Name of the profile to load

        Returns:
            dict: Credentials with keys 'access_id', 'access_key', 'deployment'
            None: If profile doesn't exist
        """
        credentials = self._get_credentials()
        return credentials.get(profile_name)

    def list_profiles(self):
        """
        List all saved profile names

        Returns:
            list: List of profile names
        """
        credentials = self._get_credentials()
        return list(credentials.keys())

    def delete_profile(self, profile_name):
        """
        Delete a named credential profile

        Args:
            profile_name (str): Name of the profile to delete

        Returns:
            bool: True if profile was deleted, False if it didn't exist
        """
        credentials = self._get_credentials()
        if profile_name in credentials:
            del credentials[profile_name]
            self._save_credentials(credentials)
            # Clear default if this was the default profile
            if self.get_default_profile() == profile_name:
                self.clear_default_profile()
            return True
        return False

    def set_default_profile(self, profile_name):
        """
        Set a profile as the default

        Args:
            profile_name (str): Name of the profile to set as default

        Returns:
            bool: True if successful, False if profile doesn't exist
        """
        # Verify profile exists
        if self.load_profile(profile_name) is None:
            return False

        with open(self.default_profile_file, 'w') as f:
            f.write(profile_name)
        os.chmod(self.default_profile_file, 0o600)
        return True

    def get_default_profile(self):
        """
        Get the name of the default profile

        Returns:
            str: Name of default profile, or None if not set
        """
        if not self.default_profile_file.exists():
            return None

        try:
            with open(self.default_profile_file, 'r') as f:
                profile_name = f.read().strip()
                # Verify profile still exists
                if self.load_profile(profile_name):
                    return profile_name
                return None
        except Exception:
            return None

    def clear_default_profile(self):
        """Clear the default profile setting"""
        if self.default_profile_file.exists():
            self.default_profile_file.unlink()


class OrganizationsAPIClient:
    """Client for interacting with Sumo Logic Organizations Management API"""

    def __init__(self, access_id, access_key, deployment_id):
        """
        Initialize the client

        Args:
            access_id (str): Sumo Logic access ID
            access_key (str): Sumo Logic access key
            deployment_id (str): Parent deployment ID (e.g., 'us2', 'au', 'eu')
        """
        self.access_id = access_id
        self.access_key = access_key
        self.deployment_id = deployment_id
        self.auth_header = self._create_auth_header()
        # Build deployment-specific base URL
        self.base_url = self._build_base_url(deployment_id)

    def _build_base_url(self, deployment_id):
        """Build the deployment-specific base URL"""
        if deployment_id == 'us1':
            return 'https://organizations.sumologic.com/api/'
        else:
            return f'https://organizations.{deployment_id}.sumologic.com/api/'

    def _create_auth_header(self):
        """Create Basic Auth header from access ID and key"""
        credentials = f"{self.access_id}:{self.access_key}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded_credentials}"

    def _make_request(self, path, method='GET', params=None, data=None):
        """Make HTTP request to Organizations API"""
        url = urljoin(self.base_url, path)

        if params:
            url += '?' + urlencode(params)

        # Prepare request body for POST
        request_data = None
        if data is not None:
            request_data = json.dumps(data).encode('utf-8')

        request = Request(url, data=request_data, method=method)
        request.add_header('Authorization', self.auth_header)
        request.add_header('parentDeploymentId', self.deployment_id)
        request.add_header('Content-Type', 'application/json')
        request.add_header('Accept', 'application/json')

        try:
            with urlopen(request) as response:
                return json.loads(response.read().decode())
        except HTTPError as e:
            error_body = e.read().decode() if e.fp else 'No error details'
            print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
            print(f"Request URL: {method} {url}", file=sys.stderr)
            print(f"Deployment ID Header: {self.deployment_id}", file=sys.stderr)
            print(f"Error details: {error_body}", file=sys.stderr)
            sys.exit(1)
        except URLError as e:
            print(f"URL Error: {e.reason}", file=sys.stderr)
            print(f"Request URL: {method} {url}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            print(f"Request URL: {method} {url}", file=sys.stderr)
            sys.exit(1)

    # GET endpoint methods
    def get_deployments(self):
        """Get deployment details where organizations can be created"""
        return self._make_request('/v1/deployments')

    def list_organizations(self, limit=100, token=None, status='Active'):
        """
        Get a list of all organizations

        Args:
            limit (int): Number of organizations per page (1-1000)
            token (str): Continuation token for pagination
            status (str): Filter by status ('Active', 'Inactive', 'All')
        """
        params = {'limit': limit, 'status': status}
        if token:
            params['token'] = token
        return self._make_request('/v1/organizations', params=params)

    def get_organization(self, org_id):
        """Get details of a specific organization"""
        return self._make_request(f'/v1/organizations/{org_id}')

    def get_parent_usage(self):
        """Get usage details of the parent organization"""
        return self._make_request('/v1/organizations/usages')

    def get_allocated_credits(self):
        """Get total allocated credits across all child organizations"""
        return self._make_request('/v1/organizations/allocatedCredits')

    def get_org_usage(self, org_id):
        """Get detailed usage breakdown for a specific organization"""
        return self._make_request(f'/v1/organizations/usages/{org_id}')

    def get_subdomain_login_url(self, org_id):
        """Get the subdomain login URL for an organization"""
        return self._make_request(f'/v1/organizations/{org_id}/subdomainLoginUrl')

    def get_parent_sso_status(self, org_id):
        """Get parent SSO status for a child organization"""
        return self._make_request(f'/v1/organizations/{org_id}/parentsso')

    def get_parent_org_info(self):
        """Get information about the parent organization"""
        return self._make_request('/v1/organizations/parentOrg')

    def get_provisioning(self, org_id):
        """Get provisioning status for a child organization"""
        return self._make_request(f'/v1/organizations/provisioning/{org_id}')

    def get_permissions(self, org_id):
        """Get permissions for an organization"""
        return self._make_request(f'/v1/organizations/{org_id}/permissions')

    def get_user_role_mappings(self, org_id):
        """Get user role mappings for an organization"""
        return self._make_request(f'/v1/organizations/{org_id}/userRoleMappings')


def format_table_output(data, title="API Response"):
    """Format API response data as a readable table"""
    lines = []
    lines.append("=" * 100)
    lines.append(title.upper())
    lines.append("=" * 100)

    def format_value(value, indent=0):
        """Recursively format values"""
        prefix = "  " * indent
        if isinstance(value, dict):
            result = []
            for k, v in value.items():
                formatted_key = ''.join([' ' + c if c.isupper() else c for c in k]).strip().title()
                if isinstance(v, (dict, list)):
                    result.append(f"{prefix}{formatted_key}:")
                    result.extend(format_value(v, indent + 1))
                else:
                    formatted_v = format_single_value(v)
                    result.append(f"{prefix}{formatted_key}: {formatted_v}")
            return result
        elif isinstance(value, list):
            result = []
            for i, item in enumerate(value, 1):
                if isinstance(item, (dict, list)):
                    result.append(f"{prefix}[{i}]")
                    result.extend(format_value(item, indent + 1))
                else:
                    formatted_item = format_single_value(item)
                    result.append(f"{prefix}- {formatted_item}")
            return result
        else:
            return [f"{prefix}{format_single_value(value)}"]

    def format_single_value(value):
        """Format a single value"""
        if value is None:
            return "N/A"
        elif isinstance(value, (int, float)) and value > 1000:
            return f"{value:,.2f}"
        else:
            return str(value)

    lines.extend(format_value(data))
    lines.append("=" * 100)
    return '\n'.join(lines)


def format_csv_output(data):
    """Format API response data as CSV"""
    lines = []

    def flatten_dict(d, parent_key='', sep='_'):
        """Flatten nested dictionary"""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(flatten_dict(v, new_key, sep=sep).items())
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                # For lists of dicts, skip in flattening (handle separately)
                items.append((new_key, str(v)))
            else:
                items.append((new_key, v))
        return dict(items)

    # Handle different response types
    if isinstance(data, dict):
        if 'data' in data and isinstance(data['data'], list):
            # Paginated list response
            all_rows = []
            for item in data['data']:
                flattened = flatten_dict(item) if isinstance(item, dict) else {'value': item}
                all_rows.append(flattened)

            if all_rows:
                # Get all unique keys
                all_keys = set()
                for row in all_rows:
                    all_keys.update(row.keys())
                headers = sorted(all_keys)

                # Write CSV
                lines.append(','.join(headers))
                for row in all_rows:
                    values = []
                    for key in headers:
                        value = row.get(key, '')
                        if value is None:
                            values.append('N/A')
                        elif isinstance(value, str) and ',' in value:
                            values.append(f'"{value}"')
                        else:
                            values.append(str(value))
                    lines.append(','.join(values))
        else:
            # Single object response
            flattened = flatten_dict(data)
            lines.append(','.join(flattened.keys()))
            values = []
            for value in flattened.values():
                if value is None:
                    values.append('N/A')
                elif isinstance(value, str) and ',' in value:
                    values.append(f'"{value}"')
                else:
                    values.append(str(value))
            lines.append(','.join(values))
    elif isinstance(data, list):
        # Direct list response
        all_rows = []
        for item in data:
            flattened = flatten_dict(item) if isinstance(item, dict) else {'value': item}
            all_rows.append(flattened)

        if all_rows:
            all_keys = set()
            for row in all_rows:
                all_keys.update(row.keys())
            headers = sorted(all_keys)

            lines.append(','.join(headers))
            for row in all_rows:
                values = []
                for key in headers:
                    value = row.get(key, '')
                    if value is None:
                        values.append('N/A')
                    elif isinstance(value, str) and ',' in value:
                        values.append(f'"{value}"')
                    else:
                        values.append(str(value))
                lines.append(','.join(values))

    return '\n'.join(lines)


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Sumo Logic Organizations Management API CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Save credentials to a profile
  %(prog)s profile-save --name production --access-id YOUR_ID --access-key YOUR_KEY --deployment us2

  # List all organizations using saved profile
  %(prog)s --profile production list-organizations

  # Get specific organization details
  %(prog)s --deployment us2 get-organization --org-id us2-00000000FF42A0C3

  # Get parent organization usage
  %(prog)s --profile production get-parent-usage --output table

  # List saved profiles
  %(prog)s profile-list

  # Delete a profile
  %(prog)s profile-delete --name production

Authentication:
  Set SUMO_ACCESS_ID and SUMO_ACCESS_KEY environment variables, use --access-id and --access-key,
  or save credentials to a named profile with profile-save and use --profile

API Reference: https://organizations.sumologic.com/api/docs
        """
    )

    # Common arguments
    parser.add_argument(
        '--profile',
        help='Use saved credential profile'
    )
    parser.add_argument(
        '--access-id',
        help='Sumo Logic access ID (default: SUMO_ACCESS_ID environment variable or saved profile)'
    )
    parser.add_argument(
        '--access-key',
        help='Sumo Logic access key (default: SUMO_ACCESS_KEY environment variable or saved profile)'
    )
    parser.add_argument(
        '--deployment',
        help='Parent deployment ID (e.g., us1, us2, eu, au, de, jp, ca, in) - required unless using --profile'
    )
    parser.add_argument(
        '--output',
        choices=['json', 'table', 'csv'],
        default='json',
        help='Output format (default: json)'
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Available commands', required=True)

    # Profile management commands
    profile_save = subparsers.add_parser('profile-save', help='Save credentials to a named profile')
    profile_save.add_argument('--name', required=True, help='Profile name')
    profile_save.add_argument('--access-id', required=True, help='Sumo Logic access ID')
    profile_save.add_argument('--access-key', required=True, help='Sumo Logic access key')
    profile_save.add_argument('--deployment', required=True, help='Parent deployment ID')

    subparsers.add_parser('profile-list', help='List all saved credential profiles')

    profile_delete = subparsers.add_parser('profile-delete', help='Delete a saved credential profile')
    profile_delete.add_argument('--name', required=True, help='Profile name to delete')

    profile_show = subparsers.add_parser('profile-show', help='Show details of a saved profile (credentials hidden)')
    profile_show.add_argument('--name', required=True, help='Profile name')

    profile_default = subparsers.add_parser('profile-set-default', help='Set a profile as the default')
    profile_default.add_argument('--name', required=True, help='Profile name to set as default')

    subparsers.add_parser('profile-clear-default', help='Clear the default profile setting')

    # list-deployments
    subparsers.add_parser('list-deployments', help='List available deployments')

    # list-organizations
    list_orgs = subparsers.add_parser('list-organizations', help='List all organizations')
    list_orgs.add_argument('--limit', type=int, default=100, help='Number of results per page (1-1000)')
    list_orgs.add_argument('--token', help='Continuation token for pagination')
    list_orgs.add_argument('--status', default='Active', choices=['Active', 'Inactive', 'All'],
                          help='Filter by organization status')

    # get-organization
    get_org = subparsers.add_parser('get-organization', help='Get organization details')
    get_org.add_argument('--org-id', required=True, help='Organization ID')

    # get-parent-usage
    subparsers.add_parser('get-parent-usage', help='Get parent organization usage details')

    # get-allocated-credits
    subparsers.add_parser('get-allocated-credits', help='Get total allocated credits')

    # get-org-usage
    org_usage = subparsers.add_parser('get-org-usage', help='Get detailed usage for an organization')
    org_usage.add_argument('--org-id', required=True, help='Organization ID')

    # get-subdomain-url
    subdomain = subparsers.add_parser('get-subdomain-url', help='Get subdomain login URL')
    subdomain.add_argument('--org-id', required=True, help='Organization ID')

    # get-sso-status
    sso = subparsers.add_parser('get-sso-status', help='Get parent SSO status')
    sso.add_argument('--org-id', required=True, help='Organization ID')

    # get-parent-info
    subparsers.add_parser('get-parent-info', help='Get parent organization information')

    # get-provisioning
    prov = subparsers.add_parser('get-provisioning', help='Get provisioning status')
    prov.add_argument('--org-id', required=True, help='Organization ID')

    # get-permissions
    perms = subparsers.add_parser('get-permissions', help='Get organization permissions')
    perms.add_argument('--org-id', required=True, help='Organization ID')

    # get-user-roles
    roles = subparsers.add_parser('get-user-roles', help='Get user role mappings')
    roles.add_argument('--org-id', required=True, help='Organization ID')

    args = parser.parse_args()

    # Initialize credential store
    cred_store = CredentialStore()

    # Handle profile management commands
    if args.command == 'profile-save':
        cred_store.save_profile(args.name, args.access_id, args.access_key, args.deployment)
        print(f"Credentials saved to profile '{args.name}'")
        print(f"Location: {cred_store.credentials_file}")
        print(f"\nUse with: {sys.argv[0]} --profile {args.name} [command]")
        return

    elif args.command == 'profile-list':
        profiles = cred_store.list_profiles()
        default_profile = cred_store.get_default_profile()
        if profiles:
            print("Saved credential profiles:")
            for profile in profiles:
                creds = cred_store.load_profile(profile)
                default_marker = " [DEFAULT]" if profile == default_profile else ""
                print(f"  - {profile} (deployment: {creds['deployment']}){default_marker}")
            if default_profile:
                print(f"\nDefault profile: {default_profile}")
        else:
            print("No saved credential profiles found.")
            print(f"Create one with: {sys.argv[0]} profile-save --name <name> --access-id <id> --access-key <key> --deployment <deployment>")
        return

    elif args.command == 'profile-delete':
        if cred_store.delete_profile(args.name):
            print(f"Profile '{args.name}' deleted successfully")
        else:
            print(f"Profile '{args.name}' not found", file=sys.stderr)
            sys.exit(1)
        return

    elif args.command == 'profile-show':
        creds = cred_store.load_profile(args.name)
        if creds:
            default_profile = cred_store.get_default_profile()
            is_default = " (DEFAULT)" if args.name == default_profile else ""
            print(f"Profile: {args.name}{is_default}")
            print(f"  Access ID: {creds['access_id'][:4]}...{creds['access_id'][-4:] if len(creds['access_id']) > 8 else '***'}")
            print(f"  Access Key: {'*' * 20}")
            print(f"  Deployment: {creds['deployment']}")
        else:
            print(f"Profile '{args.name}' not found", file=sys.stderr)
            sys.exit(1)
        return

    elif args.command == 'profile-set-default':
        if cred_store.set_default_profile(args.name):
            print(f"Profile '{args.name}' set as default")
            print(f"\nYou can now omit --profile in commands:")
            print(f"  {sys.argv[0]} list-organizations")
        else:
            print(f"Profile '{args.name}' not found", file=sys.stderr)
            sys.exit(1)
        return

    elif args.command == 'profile-clear-default':
        default = cred_store.get_default_profile()
        if default:
            cred_store.clear_default_profile()
            print(f"Default profile '{default}' cleared")
        else:
            print("No default profile is currently set")
        return

    # Get credentials from profile, args, or environment
    access_id = args.access_id
    access_key = args.access_key
    deployment = args.deployment

    # Determine which profile to use
    profile_to_use = args.profile
    if not profile_to_use and not access_id and not access_key:
        # No explicit profile and no credentials provided - try default profile
        profile_to_use = cred_store.get_default_profile()

    if profile_to_use:
        # Load from profile
        creds = cred_store.load_profile(profile_to_use)
        if not creds:
            parser.error(f"Profile '{profile_to_use}' not found. Use 'profile-list' to see available profiles.")

        # Profile credentials can be overridden by CLI args
        access_id = access_id or creds['access_id']
        access_key = access_key or creds['access_key']
        deployment = deployment or creds['deployment']
    else:
        # Fall back to environment variables
        access_id = access_id or os.environ.get('SUMO_ACCESS_ID')
        access_key = access_key or os.environ.get('SUMO_ACCESS_KEY')

    # Validate credentials
    if not access_id:
        parser.error("--access-id is required (or set SUMO_ACCESS_ID environment variable or use --profile)")
    if not access_key:
        parser.error("--access-key is required (or set SUMO_ACCESS_KEY environment variable or use --profile)")
    if not deployment:
        parser.error("--deployment is required (or use --profile)")

    # Create client
    client = OrganizationsAPIClient(access_id, access_key, deployment)

    # Execute command
    try:
        if args.command == 'list-deployments':
            result = client.get_deployments()
            title = "Available Deployments"
        elif args.command == 'list-organizations':
            result = client.list_organizations(args.limit, args.token, args.status)
            title = f"Organizations (Status: {args.status})"
        elif args.command == 'get-organization':
            result = client.get_organization(args.org_id)
            title = f"Organization Details: {args.org_id}"
        elif args.command == 'get-parent-usage':
            result = client.get_parent_usage()
            title = "Parent Organization Usage"
        elif args.command == 'get-allocated-credits':
            result = client.get_allocated_credits()
            title = "Allocated Credits"
        elif args.command == 'get-org-usage':
            result = client.get_org_usage(args.org_id)
            title = f"Usage Details: {args.org_id}"
        elif args.command == 'get-subdomain-url':
            result = client.get_subdomain_login_url(args.org_id)
            title = f"Subdomain Login URL: {args.org_id}"
        elif args.command == 'get-sso-status':
            result = client.get_parent_sso_status(args.org_id)
            title = f"Parent SSO Status: {args.org_id}"
        elif args.command == 'get-parent-info':
            result = client.get_parent_org_info()
            title = "Parent Organization Information"
        elif args.command == 'get-provisioning':
            result = client.get_provisioning(args.org_id)
            title = f"Provisioning Status: {args.org_id}"
        elif args.command == 'get-permissions':
            result = client.get_permissions(args.org_id)
            title = f"Permissions: {args.org_id}"
        elif args.command == 'get-user-roles':
            result = client.get_user_role_mappings(args.org_id)
            title = f"User Role Mappings: {args.org_id}"
        else:
            parser.error(f"Unknown command: {args.command}")

        # Format and print output
        if args.output == 'json':
            print(json.dumps(result, indent=2))
        elif args.output == 'table':
            print(format_table_output(result, title))
        elif args.output == 'csv':
            print(format_csv_output(result))

    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
