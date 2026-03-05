# Sumo Logic Organizations Management API CLI

A Python command-line interface for interacting with Sumo Logic's Organizations Management API GET endpoints. This tool is designed for parent organizations to manage and monitor their child organizations in a multi-account or MSSP setup.

## Overview

The Organizations Management API allows parent organizations to:
- List and manage child organizations
- Monitor usage and credits allocation
- View organization details and configurations
- Manage permissions and user role mappings
- Check provisioning status and SSO configuration

## API Reference

- **Base URL**: `https://organizations.sumologic.com/api/`
- **API Documentation**: [Sumo Logic Organizations Management API](https://organizations.sumologic.com/api/docs)
- **Authentication**: HTTP Basic Authentication using Sumo Logic Access ID and Access Key

## Prerequisites

- Python 3.9 or higher
- Sumo Logic parent organization account
- Access ID and Access Key with appropriate permissions
- Knowledge of your parent deployment ID (e.g., `us2`, `eu`, `au`)

## Installation

This tool uses the `uv` environment from the parent directory. Ensure you have the environment set up:

```bash
# From the parent directory (account_management)
cd ..
uv sync

# Or if not yet initialized
uv init
uv sync
```

## Authentication

You can provide credentials in three ways:

### Option 1: Saved Credential Profiles (Recommended)
Save your credentials securely to named profiles for easy reuse:

```bash
# Save credentials to a profile
python organizations_cli.py profile-save \
  --name production \
  --access-id YOUR_ACCESS_ID \
  --access-key YOUR_ACCESS_KEY \
  --deployment us2

# Use the saved profile
python organizations_cli.py --profile production list-organizations

# List all saved profiles
python organizations_cli.py profile-list

# Show profile details (credentials masked)
python organizations_cli.py profile-show --name production

# Delete a profile
python organizations_cli.py profile-delete --name production

# Set a default profile for even easier use
python organizations_cli.py profile-set-default --name production

# Now you can run commands without --profile!
python organizations_cli.py list-organizations
```

**Security Notes:**
- Credentials are stored in `~/.config/sumo-logic/organizations_credentials.json` (or `$XDG_CONFIG_HOME/sumo-logic/`)
- Default profile is stored in `~/.config/sumo-logic/organizations_default_profile.txt`
- File permissions are set to `0600` (owner read/write only)
- Directory permissions are set to `0700` (owner access only)
- Credentials are base64-encoded (obfuscation, not encryption)
- Do not commit the credentials file to version control

### Option 2: Environment Variables
```bash
export SUMO_ACCESS_ID="your-access-id"
export SUMO_ACCESS_KEY="your-access-key"
```

### Option 3: Command-Line Arguments
```bash
python organizations_cli.py --access-id YOUR_ID --access-key YOUR_KEY --deployment us2 [command]
```

**Priority Order:** CLI arguments > Saved profile > Environment variables

## Usage

### General Syntax

```bash
# Using saved profile (recommended)
python organizations_cli.py --profile <PROFILE_NAME> [--output FORMAT] <command> [command-options]

# Or with explicit credentials
python organizations_cli.py --deployment <DEPLOYMENT_ID> [--output FORMAT] <command> [command-options]
```

**Common Arguments:**
- `--profile`: Use saved credential profile (includes deployment)
- `--deployment`: Your parent deployment ID (required if not using --profile)
- `--access-id`: Sumo Logic Access ID (optional with profile or env var)
- `--access-key`: Sumo Logic Access Key (optional with profile or env var)
- `--output`: Output format - `json` (default), `table`, or `csv`

## Credential Management Commands

### profile-save
Save credentials to a named profile for easy reuse.

```bash
python organizations_cli.py profile-save \
  --name <profile_name> \
  --access-id <your_access_id> \
  --access-key <your_access_key> \
  --deployment <deployment_id>
```

**Example:**
```bash
python organizations_cli.py profile-save \
  --name prod-us2 \
  --access-id suABC123... \
  --access-key ************ \
  --deployment us2
```

### profile-list
List all saved credential profiles.

```bash
python organizations_cli.py profile-list
```

**Output:**
```
Saved credential profiles:
  - prod-us2 (deployment: us2)
  - staging-eu (deployment: eu)
  - dev-au (deployment: au)
```

### profile-show
Show details of a saved profile with credentials masked.

```bash
python organizations_cli.py profile-show --name prod-us2
```

**Output:**
```
Profile: prod-us2
  Access ID: suAB...3456
  Access Key: ********************
  Deployment: us2
```

### profile-delete
Delete a saved credential profile.

```bash
python organizations_cli.py profile-delete --name <profile_name>
```

### profile-set-default
Set a profile as the default, allowing you to omit `--profile` in commands.

```bash
python organizations_cli.py profile-set-default --name <profile_name>
```

**Example:**
```bash
# Set production as default
python organizations_cli.py profile-set-default --name production

# Now you can omit --profile in commands
python organizations_cli.py list-organizations
python organizations_cli.py get-parent-usage --output table
```

### profile-clear-default
Clear the default profile setting.

```bash
python organizations_cli.py profile-clear-default
```

## API Query Commands

### 1. List Deployments
Get available deployments where organizations can be created.

```bash
python organizations_cli.py --deployment us2 list-deployments
```

### 2. List Organizations
Get a list of all child organizations (paginated).

```bash
# List active organizations (default)
python organizations_cli.py --deployment us2 list-organizations

# List all organizations with custom limit
python organizations_cli.py --deployment us2 list-organizations --limit 50 --status All

# Use pagination token
python organizations_cli.py --deployment us2 list-organizations --token "CONTINUATION_TOKEN"
```

**Options:**
- `--limit`: Number of results per page (1-1000, default: 100)
- `--status`: Filter by status - `Active` (default), `Inactive`, or `All`
- `--token`: Continuation token for pagination

### 3. Get Organization Details
Get detailed information about a specific organization.

```bash
python organizations_cli.py --deployment us2 get-organization --org-id us2-00000000FF42A0C3
```

### 4. Get Parent Organization Usage
View usage and credits allocation for the parent organization.

```bash
python organizations_cli.py --deployment us2 get-parent-usage --output table
```

### 5. Get Allocated Credits
Get the total credits allocated across all child organizations.

```bash
python organizations_cli.py --deployment us2 get-allocated-credits
```

### 6. Get Organization Usage Details
Get detailed usage breakdown for a specific child organization.

```bash
python organizations_cli.py --deployment us2 get-org-usage --org-id us2-00000000FF42A0C3 --output csv
```

### 7. Get Subdomain Login URL
Get the subdomain login URL for a child organization.

```bash
python organizations_cli.py --deployment us2 get-subdomain-url --org-id us2-00000000FF42A0C3
```

### 8. Get Parent SSO Status
Check if SSO with parent org is configured for a child organization.

```bash
python organizations_cli.py --deployment us2 get-sso-status --org-id us2-00000000FF42A0C3
```

### 9. Get Parent Organization Information
Get information about your parent organization, including plan details and deployment charges.

```bash
python organizations_cli.py --deployment us2 get-parent-info
```

### 10. Get Provisioning Status
Check the provisioning status for features like CSE and AI Investigation.

```bash
python organizations_cli.py --deployment us2 get-provisioning --org-id us2-00000000FF42A0C3
```

### 11. Get Organization Permissions
View permission settings for a child organization.

```bash
python organizations_cli.py --deployment us2 get-permissions --org-id us2-00000000FF42A0C3
```

### 12. Get User Role Mappings
Get user role mappings for a child organization.

```bash
python organizations_cli.py --deployment us2 get-user-roles --org-id us2-00000000FF42A0C3
```

## Output Formats

### JSON (Default)
Structured JSON output suitable for programmatic processing:
```bash
python organizations_cli.py --deployment us2 list-organizations --output json
```

### Table
Human-readable tabular format:
```bash
python organizations_cli.py --deployment us2 get-parent-usage --output table
```

### CSV
Comma-separated values for spreadsheet import:
```bash
python organizations_cli.py --deployment us2 list-organizations --output csv > organizations.csv
```

## Examples

### Example 1: First Time Setup with Profiles
```bash
# Save your credentials to a profile
python organizations_cli.py profile-save \
  --name my-prod \
  --access-id suABC123... \
  --access-key ************ \
  --deployment us2

# Now use the profile for all commands
python organizations_cli.py --profile my-prod list-organizations

# Much easier than typing credentials each time!
python organizations_cli.py --profile my-prod get-parent-usage --output table
```

### Example 2: Monitor Child Organization Usage
```bash
# Using saved profile
python organizations_cli.py --profile my-prod list-organizations --output csv > orgs.csv

# Check detailed usage for a specific org
python organizations_cli.py --profile my-prod get-org-usage \
  --org-id us2-00000000FF42A0C3 \
  --output table

# Check total allocated credits
python organizations_cli.py --profile my-prod get-allocated-credits
```

### Example 3: Organization Audit
```bash
# Get organization details
python organizations_cli.py --profile my-prod get-organization \
  --org-id us2-00000000FF42A0C3 \
  --output json

# Check permissions
python organizations_cli.py --profile my-prod get-permissions \
  --org-id us2-00000000FF42A0C3

# Check user role mappings
python organizations_cli.py --profile my-prod get-user-roles \
  --org-id us2-00000000FF42A0C3
```

### Example 4: Multi-Region Management
```bash
# Save profiles for different regions
python organizations_cli.py profile-save --name prod-us2 --access-id ... --access-key ... --deployment us2
python organizations_cli.py profile-save --name prod-eu --access-id ... --access-key ... --deployment eu
python organizations_cli.py profile-save --name prod-au --access-id ... --access-key ... --deployment au

# Query each region
python organizations_cli.py --profile prod-us2 list-organizations --output csv > orgs_us2.csv
python organizations_cli.py --profile prod-eu list-organizations --output csv > orgs_eu.csv
python organizations_cli.py --profile prod-au list-organizations --output csv > orgs_au.csv
```

### Example 5: Export All Organizations Data
```bash
# Using environment variables (alternative to profiles)
export SUMO_ACCESS_ID="your-access-id"
export SUMO_ACCESS_KEY="your-access-key"

# Export organizations list
python organizations_cli.py --deployment us2 list-organizations \
  --status All --limit 1000 --output csv > all_orgs.csv

# Get parent usage summary
python organizations_cli.py --deployment us2 get-parent-usage \
  --output json > parent_usage.json
```

## Common Use Cases

### MSSP (Managed Security Service Provider)
- Monitor all child organization usage and credits
- Audit permissions and user access across organizations
- Track provisioning status for security features (CSE)
- Generate usage reports for billing

### Enterprise Multi-Account Management
- Manage credits allocation across business units
- Monitor usage trends and forecast capacity needs
- Control access and permissions for different departments
- Track subdomain URLs for easy access

### DevOps & Automation
- Integrate with CI/CD pipelines for automated reporting
- Export data to external monitoring and billing systems
- Programmatic access to organization metadata
- Automated compliance and audit reports

## Error Handling

The CLI provides clear error messages for common issues:

- **403 Forbidden**: Your account may not be a parent organization or lacks permissions
- **404 Not Found**: The specified organization ID doesn't exist
- **401 Unauthorized**: Invalid credentials (check your Access ID and Key)
- **Rate Limiting**: If you encounter rate limits, add delays between requests

## Important Notes

1. **Parent Organization Required**: This API is only available for parent organizations with child organizations.

2. **Deployment ID**: Always use the deployment where your parent organization resides (e.g., `us2`, not the child org deployment).

3. **Organization ID Format**: Child organization IDs follow the format `{deployment}-{hexAccountId}`, e.g., `us2-00000000FF42A0C3`.

4. **Pagination**: For large result sets, use the pagination token from the response to retrieve subsequent pages.

5. **Permissions**: Ensure your access keys have the `viewOrganizations` permission at minimum.

## Troubleshooting

### "This endpoint is only available for parent organizations"
- Verify you're using credentials from a parent organization account
- Ensure your account has child organizations set up

### "Invalid deployment ID"
- Use the deployment where your *parent* organization is located
- Valid values: `us1`, `us2`, `eu`, `au`, `de`, `jp`, `ca`, `in`

### "Profile not found"
```bash
# List available profiles
python organizations_cli.py profile-list

# If empty, create one
python organizations_cli.py profile-save --name default --access-id ... --access-key ... --deployment us2
```

### Credential Storage Issues
If you encounter permission errors with saved credentials:
```bash
# Check credentials file location
ls -la ~/.config/sumo-logic/organizations_credentials.json

# Verify secure permissions (should be -rw-------)
# If permissions are wrong, the tool will attempt to fix them automatically

# Delete corrupted credentials file
rm ~/.config/sumo-logic/organizations_credentials.json

# Re-save credentials
python organizations_cli.py profile-save --name default --access-id ... --access-key ... --deployment us2
```

### Credentials Security Best Practices
1. **Never commit** `~/.config/sumo-logic/organizations_credentials.json` to version control
2. Add to `.gitignore` if your home directory is in a git repo:
   ```bash
   echo "organizations_credentials.json" >> ~/.config/sumo-logic/.gitignore
   ```
3. For CI/CD environments, use environment variables instead of profiles:
   ```bash
   export SUMO_ACCESS_ID="$CI_SUMO_ID"
   export SUMO_ACCESS_KEY="$CI_SUMO_KEY"
   python organizations_cli.py --deployment us2 list-organizations
   ```
4. Rotate access keys regularly and update saved profiles:
   ```bash
   python organizations_cli.py profile-save --name production --access-id NEW_ID --access-key NEW_KEY --deployment us2
   ```

### Rate Limiting
If you need to process many organizations:
```bash
# Process organizations in batches with delays
for org_id in $(cat org_ids.txt); do
  python organizations_cli.py --profile my-prod get-org-usage --org-id "$org_id"
  sleep 1  # Add delay between requests
done
```

## Related Tools

This tool is part of the Sumo Logic Account Management API Scripts collection:

- **get_child_usages.py**: Get child organization usage data via the standard API
- **get_account_status.py**: Get account status information
- **generate_usage_report.py**: Generate comprehensive usage reports

## API Limitations

- Maximum 1000 organizations per page (pagination required for larger sets)
- Rate limiting may apply (check API documentation)
- Some endpoints (marked `x-visibility: private` in the spec) may not be available to all customers

## Support

For issues or questions:
- Review the [API Documentation](https://organizations.sumologic.com/api/docs)
- Check [Sumo Logic Help](https://help.sumologic.com/)
- Contact your Sumo Logic account team

## License

This tool is provided as-is for use with Sumo Logic accounts.
