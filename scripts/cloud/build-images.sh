#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${AWS_REGION:?Set AWS_REGION}"
: "${IMAGE_REGISTRY:?Set IMAGE_REGISTRY}"
: "${IMAGE_TAG:?Set IMAGE_TAG to the Git commit SHA}"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$IMAGE_REGISTRY"
# Detect an upstream MySQL UID change before applying the restricted StatefulSet.
mysql_uid="$(docker run --rm --entrypoint id mysql:8.4 -u mysql)"
mysql_gid="$(docker run --rm --entrypoint id mysql:8.4 -g mysql)"
[[ "$mysql_uid:$mysql_gid" == 999:999 ]] || { echo 'MySQL image UID/GID changed. Review chart mysql.uid/gid before deployment.' >&2; exit 1; }
for service in frontend registration persona media; do
  repo="eks-persona/$service"
  image="$IMAGE_REGISTRY/$repo:$IMAGE_TAG"
  if aws ecr describe-images --repository-name "$repo" --image-ids "imageTag=$IMAGE_TAG" >/dev/null 2>&1; then
    echo "Reusing immutable image: $repo:$IMAGE_TAG"
  else
    docker build --pull --label "org.opencontainers.image.revision=$IMAGE_TAG" -t "$image" "services/$service"
    uid="$(docker run --rm --entrypoint id "$image" -u)"
    [[ "$uid" != 0 ]] || { echo "Refusing to push a root runtime image: $service" >&2; exit 1; }
    docker push "$image"
  fi
    scan_error="$(mktemp)"

  if aws ecr start-image-scan \
    --region "$AWS_REGION" \
    --repository-name "$repo" \
    --image-id "imageTag=$IMAGE_TAG" \
    >/dev/null 2>"$scan_error"; then
    echo "Scan requested for $repo:$IMAGE_TAG"
  elif grep -q 'LimitExceededException' "$scan_error"; then
    echo "Scan limit reached; checking for an existing completed scan."
  else
    cat "$scan_error" >&2
    rm -f "$scan_error"
    exit 1
  fi

  rm -f "$scan_error"
  aws ecr wait image-scan-complete --repository-name "$repo" --image-id "imageTag=$IMAGE_TAG"
  findings="$(aws ecr describe-image-scan-findings --repository-name "$repo" --image-id "imageTag=$IMAGE_TAG" --query imageScanFindings.findingSeverityCounts --output json)"
  printf '%s scan counts: %s\n' "$service" "$findings"
  python3 - "$findings" <<'PY'
import json,sys
counts=json.loads(sys.argv[1]) or {}
if counts.get('CRITICAL',0):
    raise SystemExit('Critical image findings block this release. Patch dependencies/base image; do not disable the gate to bypass it.')
PY
done
