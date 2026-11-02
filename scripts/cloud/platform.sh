#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${AWS_REGION:?Set AWS_REGION}"
: "${CLUSTER_NAME:?Set CLUSTER_NAME}"
aws eks update-kubeconfig --region "$AWS_REGION" --name "$CLUSTER_NAME"
# New access entries may take a short time to become usable.
for attempt in {1..30}; do
  if kubectl auth can-i create namespaces 2>/dev/null | grep -qx yes; then break; fi
  sleep 2
done
kubectl apply --server-side --field-manager=eks-persona-platform -f platform/namespace.yaml
kubectl apply --server-side --field-manager=eks-persona-platform -f platform/storageclass.yaml
kubectl wait --for=condition=Ready nodes --all --timeout=10m
kubectl -n kube-system rollout status daemonset/aws-node --timeout=10m
kubectl -n kube-system rollout status deployment/ebs-csi-controller --timeout=10m
kubectl -n kube-system rollout status daemonset/eks-pod-identity-agent --timeout=10m
vpc_id="$(terraform -chdir=terraform/infra output -raw vpc_id)"
helm repo add eks https://aws.github.io/eks-charts --force-update
helm repo update eks
helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
  --namespace kube-system --version 1.14.0 \
  --set-string image.tag=v2.14.1 \
  --set-string "clusterName=$CLUSTER_NAME" \
  --set-string "region=$AWS_REGION" \
  --set-string "vpcId=$vpc_id" \
  --set serviceAccount.create=true \
  --set-string serviceAccount.name=aws-load-balancer-controller \
  --set featureGates.ALBGatewayAPI=false \
  --set featureGates.NLBGatewayAPI=false \
  --rollback-on-failure --wait --timeout 5m
kubectl -n kube-system rollout status deployment/aws-load-balancer-controller --timeout=5m
