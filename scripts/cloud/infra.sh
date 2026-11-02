#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${STATE_BUCKET:?Set STATE_BUCKET}"
: "${AWS_REGION:?Set AWS_REGION}"
terraform -chdir=terraform/infra init -input=false -lockfile=readonly \
  -backend-config="bucket=$STATE_BUCKET" \
  -backend-config="key=infra/terraform.tfstate" \
  -backend-config="region=$AWS_REGION" \
  -backend-config="use_lockfile=true"
terraform -chdir=terraform/infra validate
plan_file="${RUNNER_TEMP:-/tmp}/persona-${GITHUB_RUN_ID:-manual}.tfplan"
trap 'rm -f "$plan_file"' EXIT
terraform -chdir=terraform/infra plan -input=false -out="$plan_file"
terraform -chdir=terraform/infra apply -input=false "$plan_file"
