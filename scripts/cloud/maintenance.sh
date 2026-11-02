#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
case "${OPERATION:?Set OPERATION}" in
  status)
    bash scripts/cloud/diagnostics.sh
    ;;
  persistence)
    app_host="$(kubectl -n persona get service frontend -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
    python3 scripts/cloud/persistence-test.py "http://$app_host"
    ;;
  backup)
    : "${STATE_BUCKET:?Set STATE_BUCKET}"
    backup_file="$(mktemp)"
    trap 'rm -f "$backup_file"' EXIT
    kubectl -n persona exec mysql-0 -- sh -c 'MYSQL_PWD="$(cat /run/secrets/mysql_root_password)" exec mysqldump -uroot --single-transaction --no-tablespaces animal_persona' > "$backup_file"
    key="backups/${GITHUB_RUN_ID}/animal-persona.sql"
    aws s3 cp "$backup_file" "s3://$STATE_BUCKET/$key" --sse AES256 --only-show-errors
    printf 'Database backup: `s3://%s/%s`\n' "$STATE_BUCKET" "$key" >> "$GITHUB_STEP_SUMMARY"
    ;;
  rollback)
    [[ "${HELM_REVISION:-}" =~ ^[1-9][0-9]*$ ]] || { echo 'Supply a positive numeric Helm revision'; exit 1; }
    helm rollback persona "$HELM_REVISION" --namespace persona --wait --timeout 10m
    bash scripts/cloud/smoke.sh
    ;;
  *) echo 'Unknown maintenance operation' >&2; exit 1 ;;
esac
