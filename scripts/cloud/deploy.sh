#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${AWS_REGION:?Set AWS_REGION}"
: "${CLUSTER_NAME:?Set CLUSTER_NAME}"
: "${IMAGE_REGISTRY:?Set IMAGE_REGISTRY}"
: "${IMAGE_TAG:?Set IMAGE_TAG}"
aws eks update-kubeconfig --region "$AWS_REGION" --name "$CLUSTER_NAME"
python3 scripts/cloud/database-secret.py
bash scripts/cloud/sync-chart-files.sh
helm lint charts/persona
helm upgrade --install persona charts/persona --namespace persona \
  --set-string "image.registry=$IMAGE_REGISTRY" \
  --set-string "image.tag=$IMAGE_TAG" \
  --rollback-on-failure --wait --timeout 10m --history-max 10
kubectl -n persona get pods,services,pvc
for app in frontend registration persona media; do
  kubectl -n persona rollout status "deployment/$app" --timeout=3m
done
kubectl -n persona rollout status statefulset/mysql --timeout=5m
