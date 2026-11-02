#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
hostname=""
for attempt in {1..60}; do
  hostname="$(kubectl -n persona get service frontend -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
  if [[ -n "$hostname" ]]; then break; fi
  sleep 5
done
[[ -n "$hostname" ]] || { echo 'NLB hostname was not assigned'; exit 1; }
base="http://$hostname"
ready=false
for attempt in {1..60}; do
  if curl --silent --fail --connect-timeout 3 --max-time 5 "$base/healthz" >/dev/null; then ready=true; break; fi
  sleep 5
done
[[ "$ready" == true ]] || { echo 'NLB endpoint did not become healthy'; exit 1; }
python3 scripts/smoke-test.py "$base"
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  printf '## EKS Persona deployed\n\nApplication: [%s](%s)\n\nImage commit: `%s`\n' "$base" "$base" "${IMAGE_TAG:-unknown}" >> "$GITHUB_STEP_SUMMARY"
fi
printf 'Application URL: %s\n' "$base"
