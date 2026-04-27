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

```text
list_partitions.py --region REGION [filters] [--output json|table|list]
```

### Filter arguments

| Argument                                 | Default      | Description                                     |
| ---------------------------------------- | ------------ | ----------------------------------------------- |
| `--name-filter`                          | `.*`         | Regex on partition name                         |
| `--routing-expression-filter`            | `.*`         | Regex on routingExpression                      |
| `--analytics-tier-filter`                | `.*`         | Regex on analyticsTier                          |
| `--index-type-filter`                    | `Partition`  | Exact match on indexType. Use `*` for all types |
| `--is-active-filter`                     | `true`       | Filter by isActive (`true`/`false`)             |
| `--is-included-in-default-search-filter` | _(none)_     | Filter by isIncludedInDefaultSearch             |

### Output arguments

| Argument              | Default  | Description                                                            |
| --------------------- | -------- | ---------------------------------------------------------------------- |
| `--output`            | `json`   | Output format: `json`, `table`, or `list`                              |
| `--output-properties` | _(all)_  | Space-separated fields to include, e.g. `name isActive analyticsTier`  |

### list_partitions.py examples

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

| Mode        | Description                                                                                                                                  |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `list`      | **Default.** Show matching partitions and report how many roles already exist. No writes.                                                    |
| `execute`   | Create a role per partition. Uses PUT (update) if a role with that name already exists, preserving existing `users`/`capabilities`.          |
| `terraform` | Write `partitions.tf` and `roles.tf` into `--terraform-dir` with one `sumologic_partition` and one `sumologic_role_v2` block per partition.  |

### partition_roles.py usage

```text
partition_roles.py --region REGION [filters] [role options] [--mode MODE]
```

### Partition filter arguments

| Argument                      | Default                    | Description                         |
| ----------------------------- | -------------------------- | ----------------------------------- |
| `--name-filter`               | `.*`                       | Regex on partition name             |
| `--routing-expression-filter` | `.*`                       | Regex on routingExpression          |
| `--analytics-tier-filter`     | `.*`                       | Regex on analyticsTier              |
| `--index-type-filter`         | `Partition\|DefaultIndex`  | Regex on indexType                  |
| `--is-active-filter`          | `true`                     | Filter by isActive (`true`/`false`) |

### Role options (execute and terraform modes)

| Argument                 | Default  | Description                                                               |
| ------------------------ | -------- | ------------------------------------------------------------------------- |
| `--role-prefix`          | `Sumo`   | Prefix for generated role names                                           |
| `--log-analytics-filter` | `*`      | `logAnalyticsFilter` value on the role                                    |
| `--audit-data-filter`    | `*`      | `auditDataFilter` value on the role                                       |
| `--security-data-filter` | `*`      | `securityDataFilter` value on the role                                    |
| `--capabilities`         | _(none)_ | Comma-separated capabilities, e.g. `manageContent,manageDataVolumeFeed`   |
| `--dry-run`              | —        | Preview what would happen in execute mode without making any API calls    |

### Terraform options

| Argument          | Default     | Description                                             |
| ----------------- | ----------- | ------------------------------------------------------- |
| `--terraform-dir` | `terraform` | Directory to write `partitions.tf` and `roles.tf` into  |

### partition_roles.py examples

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

# Export matching partitions and roles as Terraform HCL
python partition_roles.py --region us1 --mode terraform

# Write to a custom directory
python partition_roles.py --region us1 --mode terraform \
  --terraform-dir infra/sumo
```

### Terraform output

Two files are written to `--terraform-dir` (default: `terraform/`):

| File             | Resource type          | One block per…    |
| ---------------- | ---------------------- | ----------------- |
| `partitions.tf`  | `sumologic_partition`  | matched partition |
| `roles.tf`       | `sumologic_role_v2`    | matched partition |

`partitions.tf` example — read-only fields (`id`, `isActive`, `indexType`, `totalBytes`,
`dataForwardingId`) are omitted; `retention_period = -1` is omitted since the provider
treats it as "no diff":

```hcl
resource "sumologic_partition" "my_prod_logs" {
  name                          = "my_prod_logs"
  routing_expression            = "_sourceCategory=prod/*"
  analytics_tier                = "continuous"
  retention_period              = 30
  is_included_in_default_search = false
}
```

`roles.tf` example — role name follows `<prefix>-<name>-<tier>-<type>`; filter and
capability values come from the `--log-analytics-filter` / `--audit-data-filter` /
`--security-data-filter` / `--capabilities` args:

```hcl
resource "sumologic_role_v2" "sumo_my_prod_logs_continuous_partition" {
  name                 = "Sumo-my_prod_logs-continuous-Partition"
  description          = "Auto-generated role for partition my_prod_logs"
  selection_type       = "Allow"
  log_analytics_filter = "*"
  audit_data_filter    = "*"
  security_data_filter = "*"
  capabilities         = ["manageContent"]

  selected_views {
    view_name   = "my_prod_logs"
    view_filter = ""
  }
}
```

Provider references:

- [sumologic_partition](https://registry.terraform.io/providers/SumoLogic/sumologic/latest/docs/resources/partition)
- [sumologic_role_v2](https://registry.terraform.io/providers/SumoLogic/sumologic/latest/docs/resources/role_v2)
