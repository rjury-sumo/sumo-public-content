#!/bin/bash
set -e

# Cloud SIEM Executive KPI Dashboard - Automated Deployment Script
# This script runs all three Terraform projects in sequence

echo "=========================================="
echo "Cloud SIEM Executive KPI Dashboard Deploy"
echo "=========================================="
echo ""

# Check required environment variables
if [ -z "$TF_VAR_access_id" ] || [ -z "$TF_VAR_access_key" ] || [ -z "$TF_VAR_environment" ]; then
    echo "ERROR: Required environment variables not set!"
    echo ""
    echo "Please set the following environment variables:"
    echo "  export SUMO_ACCESS_ID=\"your-access-id\""
    echo "  export SUMO_ACCESS_KEY=\"your-access-key\""
    echo "  export SUMO_ENDPOINT=\"au\""
    echo ""
    echo "  export TF_VAR_access_id=\"\$SUMO_ACCESS_ID\""
    echo "  export TF_VAR_access_key=\"\$SUMO_ACCESS_KEY\""
    echo "  export TF_VAR_environment=\"\$SUMO_ENDPOINT\""
    echo ""
    echo "Or source the .envrc file:"
    echo "  source .envrc"
    exit 1
fi

echo "Environment variables verified ✓"
echo ""

# Step 1: Create Folder and Permissions
echo "=========================================="
echo "STEP 1: Creating Folder and Permissions"
echo "=========================================="
cd 1-folder

if [ ! -d ".terraform" ]; then
    echo "Initializing Terraform..."
    terraform init
fi

echo "Running terraform plan..."
terraform plan

echo ""
read -p "Apply Step 1? (yes/no): " apply_step1
if [ "$apply_step1" != "yes" ]; then
    echo "Deployment cancelled."
    exit 0
fi

terraform apply -auto-approve

# Get folder ID from output
FOLDER_ID=$(terraform output -raw folder_id)
export TF_VAR_folder_id="$FOLDER_ID"

echo ""
echo "✓ Step 1 Complete"
echo "  Folder ID: $FOLDER_ID"
echo ""

# Step 2: Create Lookup Table
echo "=========================================="
echo "STEP 2: Creating Lookup Table"
echo "=========================================="
cd ../2-lookup

if [ ! -d ".terraform" ]; then
    echo "Initializing Terraform..."
    terraform init
fi

echo "Running terraform plan..."
terraform plan

echo ""
read -p "Apply Step 2? (yes/no): " apply_step2
if [ "$apply_step2" != "yes" ]; then
    echo "Deployment stopped after Step 1."
    exit 0
fi

terraform apply -auto-approve

echo ""
echo "✓ Step 2 Complete"
echo ""

# Step 3: Create Scheduled Search and Dashboard
echo "=========================================="
echo "STEP 3: Creating Scheduled Search & Dashboard"
echo "=========================================="
cd ../3-content

if [ ! -d ".terraform" ]; then
    echo "Initializing Terraform..."
    terraform init
fi

echo "Running terraform plan..."
terraform plan

echo ""
read -p "Apply Step 3? (yes/no): " apply_step3
if [ "$apply_step3" != "yes" ]; then
    echo "Deployment stopped after Step 2."
    exit 0
fi

terraform apply -auto-approve

echo ""
echo "✓ Step 3 Complete"
echo ""

# Return to root directory
cd ..

# Summary
echo "=========================================="
echo "DEPLOYMENT COMPLETE! ✓"
echo "=========================================="
echo ""
echo "Resources created in: /Library/Admin Recommended/CSIEM_Exec_View/"
echo ""
echo "Next steps:"
echo "  1. Navigate to the scheduled search in Sumo Logic UI"
echo "  2. Run it manually for a historical time period (e.g., -7days)"
echo "  3. Accept the dialog to save to lookup"
echo "  4. Wait a few minutes and verify the lookup contains data"
echo "  5. Open the dashboard to view your SIEM metrics"
echo ""
