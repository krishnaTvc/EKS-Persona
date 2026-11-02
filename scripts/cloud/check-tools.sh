#!/usr/bin/env bash
set -euo pipefail
for tool in aws terraform helm kubectl docker python3 curl git; do
  command -v "$tool" >/dev/null || { echo "Missing tool: $tool. See docs/DEPLOYMENT_GUIDE.md." >&2; exit 1; }
done
python3 - <<'PY'
import json, subprocess
version=json.loads(subprocess.check_output(['terraform','version','-json']))['terraform_version']
major,minor=map(int,version.split('.')[:2])
assert major==1 and minor>=10, 'Use Terraform >=1.10 and <2'
helm=subprocess.check_output(['helm','version','--short'],text=True)
assert helm.startswith('v4.'), 'This guide uses Helm 4 flags; install Helm 4'
PY
aws --version
terraform version
helm version --short
kubectl version --client
docker info --format '{{.ServerVersion}}'
