#!/usr/bin/env bash
set -u
# Does not print Secret values or process environments.
kubectl -n persona get pods,services,pvc || true
kubectl -n persona get events --sort-by=.lastTimestamp | tail -50 || true
for component in mysql frontend registration persona media; do
  kubectl -n persona logs -l "app=$component" --all-containers --tail=70 --prefix || true
done
