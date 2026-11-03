#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

: "${AWS_REGION:?Set AWS_REGION}"
: "${IMAGE_REGISTRY:?Set IMAGE_REGISTRY}"
: "${IMAGE_TAG:?Set IMAGE_TAG to the Git commit SHA}"

export AWS_PAGER=""

aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$IMAGE_REGISTRY"

# Verify compatibility with the MySQL StatefulSet security context.
mysql_uid="$(docker run --rm --entrypoint id mysql:8.4 -u mysql)"
mysql_gid="$(docker run --rm --entrypoint id mysql:8.4 -g mysql)"

if [[ "$mysql_uid:$mysql_gid" != "999:999" ]]; then
  echo "MySQL UID/GID changed. Review chart mysql.uid/gid." >&2
  exit 1
fi

scan_error="$(mktemp)"
scan_result="$(mktemp)"
trap 'rm -f "$scan_error" "$scan_result"' EXIT

for service in frontend registration persona media; do
  repo="eks-persona/$service"
  image="$IMAGE_REGISTRY/$repo:$IMAGE_TAG"

  if aws ecr describe-images \
    --region "$AWS_REGION" \
    --repository-name "$repo" \
    --image-ids "imageTag=$IMAGE_TAG" \
    >/dev/null 2>"$scan_error"; then
    echo "Reusing immutable image: $repo:$IMAGE_TAG"
  elif grep -q 'ImageNotFoundException' "$scan_error"; then
    docker build --pull \
      --label "org.opencontainers.image.revision=$IMAGE_TAG" \
      -t "$image" "services/$service"

    uid="$(docker run --rm --entrypoint id "$image" -u)"

    if [[ "$uid" == "0" ]]; then
      echo "Refusing to push a root runtime image: $service" >&2
      exit 1
    fi

    docker push "$image"
  else
    cat "$scan_error" >&2
    exit 1
  fi

  if aws ecr start-image-scan \
    --region "$AWS_REGION" \
    --repository-name "$repo" \
    --image-id "imageTag=$IMAGE_TAG" \
    >/dev/null 2>"$scan_error"; then
    echo "Scan requested for $repo:$IMAGE_TAG"
  elif grep -q 'LimitExceededException' "$scan_error"; then
    echo "Scan limit reached; checking existing scan results."
  else
    cat "$scan_error" >&2
    exit 1
  fi

  aws ecr wait image-scan-complete \
    --region "$AWS_REGION" \
    --repository-name "$repo" \
    --image-id "imageTag=$IMAGE_TAG"

  aws ecr describe-image-scan-findings \
    --region "$AWS_REGION" \
    --repository-name "$repo" \
    --image-id "imageTag=$IMAGE_TAG" \
    --output json > "$scan_result"

  python3 - "$service" "$scan_result" <<'PY'
import json
import sys

service, result_path = sys.argv[1:3]

try:
    with open(result_path, encoding="utf-8") as stream:
        result = json.load(stream)
except (OSError, ValueError) as error:
    raise SystemExit(f"{service}: cannot read scan results: {error}")

if not isinstance(result, dict):
    raise SystemExit(f"{service}: invalid scan response")

status = result.get("imageScanStatus", {}).get("status")
if status != "COMPLETE":
    raise SystemExit(f"{service}: scan is not complete: {status}")

findings = result.get("imageScanFindings")
if not isinstance(findings, dict):
    raise SystemExit(f"{service}: scan findings missing; refusing deployment")

counts = findings.get("findingSeverityCounts")
if counts is None:
    counts = {}

if not isinstance(counts, dict) or any(
    type(value) is not int or value < 0
    for value in counts.values()
):
    raise SystemExit(f"{service}: invalid severity counts")

print(f"{service} scan counts: {json.dumps(counts, sort_keys=True)}")

if counts.get("CRITICAL", 0):
    raise SystemExit(
        f"{service}: critical vulnerabilities block this release. "
        "Patch the base image or dependencies."
    )
PY
done
