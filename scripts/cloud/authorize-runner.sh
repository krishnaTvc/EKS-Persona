#!/usr/bin/env bash
set -euo pipefail
: "${GITHUB_ENV:?Run this script in GitHub Actions}"
runner_ip="$(curl -fsS --retry 3 https://checkip.amazonaws.com | tr -d '\n')"
python3 - "$runner_ip" <<'PY'
import ipaddress,json,os,sys
address=ipaddress.IPv4Address(sys.argv[1])
extras=json.loads(os.environ.get('EXTRA_API_CIDRS') or '[]')
cidrs=[str(address)+'/32']+extras
for item in cidrs:
    assert ipaddress.IPv4Network(item,strict=False).prefixlen>0, 'Do not allow 0.0.0.0/0'
with open(os.environ['GITHUB_ENV'],'a') as file:
    file.write('TF_VAR_api_allowed_cidrs='+json.dumps(cidrs)+'\n')
PY
