# EKS-Persona bootstrap — GitHub runner only

This addition matches the bootstrap main.tf in the uploaded EKS-Persona-main.zip
(commit 032b7caf1d62965e488317b5b031322f1ffb1e25). It adds files; it does not
replace the existing deploy/destroy/maintenance workflows or Terraform resources.
No WSL, local Terraform, AWS access keys, or self-hosted runner is needed.

## 1. Pause automatic deployment

GitHub → EKS-Persona → Actions → Deploy EKS Persona → menu → Disable workflow.
This avoids triggering deployment when you push these files before bootstrap is
ready. Do not run destroy while bootstrapping. All supplied workflows share
concurrency group eks-persona-dev.

## 2. Create the one initial authentication role in AWS Console

A workflow cannot create the very first role it must assume. You already have
GitHub's OIDC provider and an infrastructure role. Keep both.

Use a separate role named **eks-persona-ci-bootstrap** so the usual infra role
does not need permissions to modify its own trust and policies.

1. IAM → Roles → eks-persona-ci-infra → Trust relationships. Copy its existing
   JSON trust policy. This should already restrict access to your GitHub repo's
   main branch and audience sts.amazonaws.com. The duration error in the old run
   did not demonstrate successful authentication; this new run will check it.
2. IAM → Roles → Create role → Custom trust policy. Paste that JSON and name the
   role eks-persona-ci-bootstrap. Do NOT choose EC2 as its trusted service.
3. On the new role, Permissions → Add permissions → Create inline policy → JSON.
   Paste the contents of **docs/bootstrap-role-policy.json** from this ZIP.
   Name it eks-persona-bootstrap. No AdministratorAccess policy is needed.
4. The default one-hour session is sufficient for this bootstrap workflow, which
   requests 3600 seconds. The existing infrastructure role's maximum duration
   will become 7200 seconds when bootstrap applies its Terraform configuration.

The supplied policy is specific to account 407178840502, region eu-north-1,
bucket eks-persona-state-407178840502-eu-north-1, two CI roles, four ECR repos,
and bootstrap state objects. It cannot create EKS or modify its own bootstrap
role. AWS organization policies, permission boundaries, and nonstandard KMS or
bucket policies can further restrict access. AccessDenied stops the script;
it is never treated as proof that a resource is missing.

The bootstrap authentication role stays manually managed. Terraform manages the
infra and deploy roles. Do not import the bootstrap authentication role as infra.

## 3. Set GitHub repository variables

Settings → Secrets and variables → Actions → Variables:

| Variable | Value |
|---|---|
| BOOTSTRAP_ROLE_ARN | arn:aws:iam::407178840502:role/eks-persona-ci-bootstrap |
| AWS_REGION | eu-north-1 |
| STATE_BUCKET | eks-persona-state-407178840502-eu-north-1 |
| INFRA_ROLE_ARN | arn:aws:iam::407178840502:role/eks-persona-ci-infra |
| DEPLOY_ROLE_ARN | arn:aws:iam::407178840502:role/eks-persona-ci-deploy |

Leave OPERATOR_PRINCIPAL_ARN and EXTRA_API_CIDRS as previously configured.
Your database passwords remain GitHub secrets and are not used by bootstrap.
Do not add an environment to this workflow without updating OIDC trust: the
subject changes when a job uses a GitHub environment.

## 4. Add these files to the repository

Copy the ZIP contents into your EKS-Persona repo root, preserving paths:

- .github/workflows/bootstrap.yaml
- scripts/cloud/bootstrap.py
- docs/bootstrap-role-policy.json
- docs/BOOTSTRAP_PIPELINE.md
- tests/test_bootstrap_workflow.py

Keep your existing terraform/bootstrap/main.tf. Do NOT copy backend.tf.example
to backend.tf or commit a generated backend.tf: the script generates it at run
 time after deciding whether the bucket exists. A committed backend.tf causes a
clear refusal so a first-run migration cannot accidentally overwrite state.
Do not upload terraform.tfstate, .terraform, or plan files to GitHub.
The script requires a fresh checkout and assumes resources are not already
managed in another Terraform project's state. Do not import the same AWS object
into two independent states.

Commit and push using your usual Git workflow. Deployment should still be disabled.

## 5. Start bootstrap

GitHub → Actions → Bootstrap EKS Persona → Run workflow → branch main.

- **Bucket already exists:** choose plan first. It initializes S3 state, imports
  existing resources, and shows proposed changes without applying those changes.
  Imports themselves are saved to state. Review role trust, policies, bucket
  policy, and tags in the log; rerun with apply when they match your intent.
- **Bucket does not exist:** choose apply. A plan-only run deliberately stops
  before creating anything. The apply run first prints and applies the plan for
  only the five S3 resources, immediately migrates state into the new bucket,
  then imports other existing resources and applies the full bootstrap plan.
  This manual apply run authorizes creation/configuration changes; it has no
  separate pause between printing the plan and applying it.

Existing resources in the expected account and names are imported, not recreated:
state bucket, separately managed S3 settings/policy, infra/deploy IAM roles and
named inline policies, and four ECR repositories. Missing resources are created.
Existing OIDC provider is referenced, not modified. Every Terraform plan is
checked; a deletion or replacement stops the run before apply.

Importing is adoption, not merely reading: Terraform will enforce the settings
in main.tf. For example, it can update an imported role's trust, replace the named
inline policy, set maximum session duration, and replace an existing bucket
policy with the project's TLS-only policy. Existing extra managed IAM policies
are not removed by this addition; review them separately if the manually created
infra role currently has broad permissions.

## 6. What success looks like

- IAM: eks-persona-ci-infra and eks-persona-ci-deploy both exist; maximum session
  duration is 2 hours for each.
- S3: private, encrypted, versioned state bucket with bootstrap/terraform.tfstate.
- ECR: eks-persona/frontend, registration, persona, media repositories.
- Terraform outputs show the two CI role ARNs and ECR registry.
- No VPC, EKS cluster, or application is created by bootstrap.

Set DEPLOY_ROLE_ARN to the actual deploy role ARN (not infra). Re-enable Deploy
EKS Persona and run it manually. It creates EKS/networking using separate state
at infra/terraform.tfstate, builds and pushes images to ECR, and deploys via Helm.
Keep the bootstrap role and its GitHub variable for future bootstrap changes;
only main-branch jobs matching its OIDC trust can assume it.

## 7. Failures and recovery

- AccessDenied: inspect the exact denied action in the run. Do not delete the
  existing resource or silently ignore the error.
- Bucket region/account mismatch: fix STATE_BUCKET/AWS_REGION; do not reuse an
  unrelated bucket. Existing bucket must belong to the expected account.
- First bucket creation/migration failure: the script tries to save remaining
  local state privately, with AES256 encryption, at
  bootstrap/recovery/<GitHub-run-id>.tfstate in the same bucket. It never
  publishes state as an Actions artifact. If the runner is forcibly terminated,
  recovery upload may not run. The next run can rediscover/import created S3
  resources. Review recovery state if the log says migration failed; do not use
  terraform state push -force or overwrite an existing remote state blindly.
- A successful plan-only run with no existing state leaves imported resources
  recorded in S3. That is expected and makes the later apply repeatable.
- Do not run bootstrap concurrently from another repository or CLI; the GitHub
  concurrency lock covers this repository, and Terraform's S3 lock protects
  state operations after remote initialization.

## Validation performed for this addition

GitHub Actions syntax checked using actionlint. Seven offline Python tests cover
idempotent import, resource discovery, distinguishing missing resources from
permission/network failures, and rejecting destructive Terraform plans. No AWS
API calls, Terraform apply, or live imports were executed during preparation.
First-run creation and migration still need validation in your AWS account.
