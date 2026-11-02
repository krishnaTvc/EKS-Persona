# Separate destroy workflow for EKS Persona

This addition was prepared against your uploaded EKS-Persona-main repository. It adds a manual workflow and helper; it does not execute a teardown or change AWS resources during installation.

## Why a separate workflow

Every YAML file under `.github/workflows/` is an independent GitHub Actions workflow. Keep normal deployment in `deploy.yaml`, and manual teardown in `destroy.yaml`. The new workflow has `workflow_dispatch` only, so it does not destroy anything on a push.

It uses the same repository variables and existing OIDC roles as deployment. No new repository, database password secret or GitHub Environment is required. The main-branch condition also matches your current IAM OIDC trust policy. Adding a protected Environment later requires a matching trust-policy update.

## Install and run

1. Before committing the addition, open GitHub Actions -> Deploy EKS Persona -> three-dot menu -> Disable workflow. This prevents the commit that adds these files, or a later push, from provisioning/recreating the cluster while you are trying to remove it. Let any active deployment finish or safely cancel it before teardown.
2. Extract this ZIP into the root of your existing repository. It adds `.github/workflows/destroy.yaml`, `scripts/cloud/destroy.py`, `tests/test_destroy_workflow.py`, and this document. Keep your existing files and account configuration.
3. Commit and push these additions to `main`. The new manual workflow must be present on the repository's default branch to appear in Actions.
4. Open Actions -> Destroy EKS Persona -> Run workflow. Choose `main`.
5. First select `plan-only`. Review the log and summary. This reads your existing infra state and prepares a destroy plan; it does not uninstall Helm releases, change the API allowlist or apply the plan.
6. When you intend to tear down, run it again with mode `destroy`, type `eks-persona-dev` exactly in `confirm_cluster`, and leave `backup_database` checked.
7. Read the resulting workflow summary for the private S3 backup and retained EBS inventory keys. Keep deployment disabled until you intentionally want to rebuild.

The shared concurrency group `eks-persona-dev` serializes this workflow with your existing deployment and maintenance workflows. It does not prevent a FUTURE deployment from rebuilding the cluster. That is why disabling deployment before teardown matters.

## What happens in destroy mode

1. GitHub checks your explicit cluster-name confirmation before requesting AWS credentials.
2. A hosted runner assumes the existing infrastructure role through OIDC.
3. The helper checks the backend bucket and ONLY the key `infra/terraform.tfstate`, in Terraform workspace `default`. Missing/empty infra state is reported as a no-op. It never falls back to local state or to the bootstrap key.
4. Terraform initializes the existing backend. Init uses an existing provider lock if present and may create one on the temporary runner if absent; it does not use `-upgrade`. The helper refuses state containing the S3/ECR/OIDC bootstrap resources, a different cluster, CI roles, or resources tagged for another project.
5. If an ACTIVE cluster owned by the infra state exists, its existing public API allowlist is extended with this runner's current address. This is a limited teardown-only AWS API update so Kubernetes cleanup can run. It avoids calling the normal provisioning script, which might recreate missing resources. A private-only endpoint is not automatically opened; use a VPC-connected runner in that case.
6. The infrastructure role records the MySQL PVC/PV/EBS identifier and enforces Retain for its disk and StatefulSet claim lifecycle.
7. The workflow switches to the application role. It uploads the inventory, takes a logical MySQL dump when MySQL is deployed/Ready, and uploads it to the private S3 backup prefix. Backup failures stop teardown before application uninstall.
8. Helm uninstalls the application release using foreground deletion and waits for the frontend Service to disappear. This leaves the AWS Load Balancer Controller running to process the Service finalizer and remove its NLB resources.
9. The workflow switches back to the infrastructure role and removes the controller Helm release only after the frontend Service is gone.
10. Terraform generates a fresh `plan -destroy` saved plan. The helper checks its JSON and refuses create/update/replacement actions. It applies only that saved destroy plan to the infra state.

The final CLI command is `terraform apply <saved-destroy-plan>`, which is the supported way to execute the previously calculated destroy plan. It is not a normal provisioning apply. No `scripts/cloud/infra.sh` command runs in this workflow.

## What is deleted or retained

| Item | Behavior |
| --- | --- |
| Four app Deployments and Services | Removed by Helm |
| MySQL pod and StatefulSet | Removed by Helm |
| Frontend NLB resources | Cleaned up by the running load balancer controller before controller removal |
| EKS workers, cluster, project networking/NAT, workload roles, add-ons and control-plane log group | Destroyed through the existing infra state |
| MySQL EBS data disk | Retained; no delete-volume command is included |
| MySQL PVC object | Retained during Helm uninstall; Kubernetes objects disappear when the entire cluster is deleted |
| Backend S3 bucket and bootstrap state | Retained |
| S3 database backups and inventory | Retained |
| ECR repositories/images | Retained |
| GitHub OIDC provider and CI infrastructure/deploy roles | Retained; these belong to the bootstrap layer |
| Other clusters or infrastructure absent from this infra state | Not targeted |

Retained EBS and ECR/S3 storage can still incur charges after the cluster is gone. Keep the EBS volume ID from the inventory. A newly created cluster will not automatically discover and adopt the old disk; use an explicit restore/static-volume recovery procedure. Delete a retained disk manually only after you have deliberately decided the data is no longer needed.

## Partial deployments and failures

- If infra state is absent or empty, there is nothing for this workflow to destroy. This does not establish that no other AWS resources exist elsewhere.
- If the state contains partial networking but no cluster, Kubernetes steps are skipped and Terraform can remove those managed resources.
- A missing backend bucket, permission error, an in-progress cluster operation or unexpected state fails the workflow rather than guessing a different backend.
- If a MySQL claim exists but its pod is absent/unready, the checked backup option stops teardown. Repair MySQL first. For an incomplete disposable lab, you may deliberately uncheck backup; the disk is still retained, but no fresh logical backup is guaranteed.
- Do not force-remove Service finalizers to get past NLB cleanup. Investigate controller/IAM/Service events first. AWS can also take time to finish deleting network interfaces/security groups after a controller reports deletion; check the EC2 console if VPC deletion reports a dependency.
- If a partial Terraform teardown has already removed the CI access entry while the cluster still exists, Kubernetes cleanup may be unavailable on a retry. Restore access using your authorized operator before retrying; the workflow does not silently bypass cleanup.
- Stop new writes/registrations before the final backup if you need all records up to the cutover. A dump taken while the public app is still accepting requests is a snapshot, not a zero-data-loss migration.

The existing infrastructure role can perform scoped EKS updates/deletes and networking deletes; the deployment role in your uploaded bootstrap includes GetObject/PutObject for the bucket's `backups/` prefix. If those roles were created differently in AWS, align their actual policies with the repository before running this workflow. Do not attach AdministratorAccess just to bypass an unexplained error.

## Existing deployment prerequisites still apply

Your uploaded repository does not include `.terraform.lock.hcl` files or `terraform/infra/addons.auto.tfvars.json`. Its validation job no longer requires a read-only lock, but `scripts/cloud/infra.sh` still does. Resolve those deployment prerequisites separately. The destroy helper can resolve compatible add-on input pins on its temporary runner if missing; this is read-only AWS discovery and does not upgrade or create add-ons.

The earlier uploaded run logs stopped in validation at a provider-lock error. Those logs do not show S3 backend initialization, an AWS apply or a created state object. Successful deployment later stores infra state at `s3://STATE_BUCKET/infra/terraform.tfstate`; one-time bootstrap state uses a different key.

## Validation performed

The addition is checked with actionlint and offline tests for manual confirmation, shared-state protection, refusal of unsafe plans, preview behavior and missing-state handling. No AWS destroy, Helm uninstall, database dump or EBS operation was executed in preparing these files. Test the plan-only route and review your actual account state before teardown.

## Official references

- Workflow dispatch and multiple workflows: https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow
- Cross-workflow concurrency: https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency
- Saved Terraform destroy plans: https://developer.hashicorp.com/terraform/cli/commands/plan
- Helm uninstall and foreground deletion: https://docs.helm.sh/docs/helm/helm_uninstall/
- EKS endpoint updates: https://docs.aws.amazon.com/cli/latest/reference/eks/update-cluster-config.html
