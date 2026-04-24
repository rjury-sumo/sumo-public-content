# Sumo Logic Partition Scripts

Python scripts for listing, managing, and exporting Sumo Logic partitions via the REST API.

## Authentication

All scripts read credentials from environment variables by default:

```bash
export SUMO_ACCESS_ID=your_access_id
export SUMO_ACCESS_KEY=your_access_key
```

Or pass them explicitly with `--access-id` / `--access-key`.

**Regions:** `us1` `us2` `eu` `au` `de` `jp` `ca` `in`

---

## list_partitions.py

Lists partitions with flexible filtering and output formatting.

**API:** [GET /api/v1/partitions](https://api.sumologic.com/docs/#operation/listPartitions)

### Usage

```
list_partitions.py --region REGION [filters] [--output json|table|list]
```

### Filter arguments

| Argument | Default | Description |
|---|---|---|
| `--name-filter` | `.*` | Regex on partition name |
| `--routing-expression-filter` | `.*` | Regex on routingExpression |
| `--analytics-tier-filter` | `.*` | Regex on analyticsTier |
| `--index-type-filter` | `Partition` | Exact match on indexType. Use `*` for all types |
| `--is-active-filter` | `true` | Filter by isActive (`true`/`false`) |
| `--is-included-in-default-search-filter` | _(none)_ | Filter by isIncludedInDefaultSearch |

### Output arguments

| Argument | Default | Description |
|---|---|---|
| `--output` | `json` | Output format: `json`, `table`, or `list` |
| `--output-properties` | _(all)_ | Space-separated list of fields to include, e.g. `name isActive analyticsTier` |

### Examples

```bash
# All active partitions as JSON
python list_partitions.py --region us1

# Table view of specific columns
python list_partitions.py --region us1 --output table \
  --output-properties name isActive analyticsTier indexType

# Only infrequent or continuous tier
python list_partitions.py --region us1 --analytics-tier-filter "Infrequent|Continuous"

# All index types (partitions + views + default index)
python list_partitions.py --region us1 --index-type-filter "*"

# Partitions matching a name pattern, list format
python list_partitions.py --region us1 --name-filter "prod.*" --output list
```

---

## partition_roles.py

Finds partitions matching filter criteria then creates or updates scoped
[Roles v2](https://api.sumologic.com/docs/beta/#tag/RoleManagementV2) for each one,
or exports them as Terraform HCL.

**Role naming:** `<prefix>-<name>-<tier>-<type>`
Example: `Sumo-my_partition-infrequent-Partition`

### Modes

| Mode | Description |
|---|---|
| `list` _(default)_ | Show matching partitions and report how many roles already exist. No writes. |
| `execute` | Create a role per partition. Uses PUT (update) if a role with that name already exists, preserving existing `users` and `capabilities` unless overridden. |
| `terraform` | Write `terraform/partitions.tf` (or `--terraform-dir`) with a `sumologic_partition` resource block per partition. |

### Usage

```
partition_roles.py --region REGION [filters] [role options] [--mode MODE]
```

### Partition filter arguments

| Argument | Default | Description |
|---|---|---|
| `--name-filter` | `.*` | Regex on partition name |
| `--routing-expression-filter` | `.*` | Regex on routingExpression |
| `--analytics-tier-filter` | `.*` | Regex on analyticsTier |
| `--index-type-filter` | `Partition\|DefaultIndex` | Regex on indexType |
| `--is-active-filter` | `true` | Filter by isActive (`true`/`false`) |

### Role options (execute mode)

| Argument | Default | Description |
|---|---|---|
| `--role-prefix` | `Sumo` | Prefix for generated role names |
| `--log-analytics-filter` | `*` | `logAnalyticsFilter` value on the role |
| `--audit-data-filter` | `*` | `auditDataFilter` value on the role |
| `--security-data-filter` | `*` | `securityDataFilter` value on the role |
| `--capabilities` | _(none)_ | Comma-separated capabilities, e.g. `manageContent,manageDataVolumeFeed` |
| `--dry-run` | — | Print what would happen without making any API calls |

### Terraform options (terraform mode)

| Argument | Default | Description |
|---|---|---|
| `--terraform-dir` | `terraform` | Directory to write `partitions.tf` into |

### Examples

```bash
# List matching partitions and role coverage
python partition_roles.py --region us1

# Only infrequent-tier partitions
python partition_roles.py --region us1 --analytics-tier-filter Infrequent

# Dry-run: preview role creates/updates without touching the API
python partition_roles.py --region us1 --mode execute --dry-run

# Create/update roles with custom prefix and capabilities
python partition_roles.py --region us1 --mode execute \
  --role-prefix MyOrg \
  --capabilities "manageContent,manageDataVolumeFeed"

# Scope log analytics filter to a specific source category
python partition_roles.py --region us1 --mode execute \
  --log-analytics-filter "_sourceCategory=prod/*"

# Export matching partitions as Terraform HCL
python partition_roles.py --region us1 --mode terraform

# Write to a custom directory
python partition_roles.py --region us1 --mode terraform \
  --terraform-dir infra/sumo
```

### Terraform output

The generated `partitions.tf` contains one `sumologic_partition` resource per matched
partition. Read-only fields (`id`, `isActive`, `indexType`, `totalBytes`,
`dataForwardingId`) are omitted. `retention_period = -1` (account default) is also
omitted since the provider treats it as "no diff".

```hcl
resource "sumologic_partition" "my_prod_logs" {
  name               = "my_prod_logs"
  routing_expression = "_sourceCategory=prod/*"
  analytics_tier     = "continuous"
  retention_period   = 30
  is_included_in_default_search = false
}
```

Provider reference: [registry.terraform.io/providers/SumoLogic/sumologic](https://registry.terraform.io/providers/SumoLogic/sumologic/latest/docs/resources/partition)
