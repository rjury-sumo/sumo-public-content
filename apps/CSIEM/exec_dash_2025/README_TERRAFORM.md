# Cloud SIEM Executive KPI Dashboard - Terraform Deployment

Automated deployment of the Cloud SIEM Executive KPI Dashboard solution using Terraform.

## What Gets Deployed

- **Folder**: `CSIEM_Exec_View` in `/Library/Admin Recommended/`
- **Lookup table**: `siem_metrics` for tracking insight metrics
- **Scheduled search**: Populates the lookup every 15 minutes
- **Dashboard**: Executive view with KPI metrics

## Prerequisites

- [Terraform](https://www.terraform.io/downloads) >= 1.6
- Sumo Logic account with admin permissions
- Sumo Logic Access ID and Access Key

## Quick Start

### 1. Set Environment Variables

```bash
export SUMO_ACCESS_ID="your-access-id"
export SUMO_ACCESS_KEY="your-access-key"
export SUMO_ENDPOINT="au"  # e.g., au, us2, eu, etc.

export TF_VAR_access_id="$SUMO_ACCESS_ID"
export TF_VAR_access_key="$SUMO_ACCESS_KEY"
export TF_VAR_environment="$SUMO_ENDPOINT"
```

Or use the provided template:
```bash
cp .envrc.example .envrc
# Edit .envrc with your credentials
source .envrc
```

### 2. Deploy

```bash
./deploy.sh
```

The script will:
1. Create the folder and set permissions
2. Create the lookup table
3. Create the scheduled search and dashboard

Confirm each step when prompted.

## After Deployment

1. Navigate to `/Library/Admin Recommended/CSIEM_Exec_View/` in Sumo Logic UI
2. Open the scheduled search and run it manually for historical data (e.g., -7days)
3. Accept the dialog to save to lookup
4. Wait a few minutes for data to populate
5. Open the dashboard to view your SIEM metrics

## Manual Deployment (3 Stages)

If you prefer to run each stage separately:

```bash
# Stage 1: Folder
cd 1-folder
terraform init && terraform apply
export FOLDER_ID=$(terraform output -raw folder_id)
export TF_VAR_folder_id="$FOLDER_ID"

# Stage 2: Lookup
cd ../2-lookup
terraform init && terraform apply

# Stage 3: Content
cd ../3-content
terraform init && terraform apply
```

## Cleanup

To remove all resources:

```bash
cd 3-content && terraform destroy
cd ../2-lookup && terraform destroy
cd ../1-folder && terraform destroy
```

## Troubleshooting

**Authentication errors**: Verify `TF_VAR_access_id`, `TF_VAR_access_key`, and `TF_VAR_environment` are set

**Permission errors**: Ensure your Sumo Logic account has admin permissions

**Folder not found**: Make sure `FOLDER_ID` was exported after Stage 1
