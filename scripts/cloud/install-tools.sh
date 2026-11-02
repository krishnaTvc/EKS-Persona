#!/usr/bin/env bash
set -euo pipefail
: "${RUNNER_TEMP:?Run this script in GitHub Actions}"
: "${GITHUB_PATH:?Run this script in GitHub Actions}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"
mkdir -p "$RUNNER_TEMP/persona-bin"
helm_version=v4.3.0
curl -fsSL --retry 3 "https://get.helm.sh/helm-$helm_version-linux-amd64.tar.gz" -o "helm-$helm_version-linux-amd64.tar.gz"
curl -fsSL --retry 3 "https://get.helm.sh/helm-$helm_version-linux-amd64.tar.gz.sha256sum" -o helm.sha256sum
sha256sum --check helm.sha256sum
tar -xzf "helm-$helm_version-linux-amd64.tar.gz"
install -m 0755 linux-amd64/helm "$RUNNER_TEMP/persona-bin/helm"
kubectl_version=v1.36.1
curl -fsSL --retry 3 "https://dl.k8s.io/release/$kubectl_version/bin/linux/amd64/kubectl" -o kubectl
curl -fsSL --retry 3 "https://dl.k8s.io/release/$kubectl_version/bin/linux/amd64/kubectl.sha256" -o kubectl.sha256
printf '%s  kubectl\n' "$(cat kubectl.sha256)" | sha256sum --check
install -m 0755 kubectl "$RUNNER_TEMP/persona-bin/kubectl"
echo "$RUNNER_TEMP/persona-bin" >> "$GITHUB_PATH"
