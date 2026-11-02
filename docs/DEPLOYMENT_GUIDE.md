# EKS Persona Deployment Guide

GitHub Actions Terraform Helm and persistent MySQL

Prepared 2 November 2026

## 1 What you will build

You already proved that the application works in Docker. This guide moves the same four application services to Amazon EKS and makes GitHub the delivery entry point. A push to the main branch runs tests, provisions infrastructure, builds images, and deploys the application. Your browser opens an AWS load balancer URL when the workflow succeeds.

The default route uses GitHub-hosted Ubuntu runners. There is no WSL runner, laptop Docker daemon, local Terraform execution, local kubeconfig, or local port-forward in the delivery path. The one-time AWS setup runs in AWS CloudShell. You can push source with your normal Git client or GitHub's web interface; that is the only source-upload step outside AWS and GitHub Actions.

The package includes the application, four Dockerfiles, Terraform, one Helm chart, deployment scripts, a deployment workflow, pull-request checks, and a manual maintenance workflow. This is a small deployment lab with production-informed practices. It is not a claim of production database high availability or a completed AWS deployment.

Important scope: the Terraform creates a NEW VPC and cluster named `eks-persona-dev`. It does not automatically reuse, replace, or import the cluster from your earlier `eks-practice` project. If the old cluster still runs, both clusters are billed. Do not point this new state at existing resources without an explicit import/reuse design.

## 2 Understand the delivery sequence

| Stage | Where it runs | What actually happens |
| --- | --- | --- |
| Git push | GitHub repository | A commit updates main and produces a Git commit SHA. |
| Actions | GitHub service | GitHub reads `.github/workflows/deploy.yaml` and schedules jobs. |
| Validation runner | GitHub-hosted Ubuntu VM | Tests the app, checks Terraform configuration and renders Helm YAML before cloud changes. |
| Deployment runner | A second GitHub-hosted Ubuntu VM | Runs all AWS infrastructure, image and deployment steps in the same job. |
| AWS OIDC | Runner and AWS STS | Exchanges a short-lived GitHub identity token for temporary role credentials. |
| Terraform | Deployment runner | Calls AWS APIs to create or reconcile networking, EKS, nodes, add-ons and access entries. |
| Scripts | Same runner | Prepare cluster-level resources, install the load balancer controller, build/push images and supply the database Secret. |
| Helm | Same runner | Renders the application chart and sends Kubernetes resources to the EKS API. |
| EKS nodes | EC2 in private subnets | Pull images from ECR, run pods and mount MySQL's persistent disk. |
| Smoke test | Deployment runner | Calls the public application URL and verifies registration, retrieval and image delivery. |

Scripts are not another server between Terraform and Helm. They are files executed by the runner. Terraform creates AWS infrastructure. Helm installs application resources into Kubernetes. Neither runs your application traffic after the job finishes.

The validation and deployment jobs have different hosted runners. Within the deployment job, Terraform and Helm deliberately share ONE runner. This matters because the EKS API allowlist includes that runner's current public IPv4 address. Moving Helm into a separate hosted job without updating the allowlist would break connectivity.

## 3 Understand the running application

| Component | Kubernetes resource | Purpose |
| --- | --- | --- |
| Frontend | Deployment and public LoadBalancer Service | Nginx serves the UI and proxies API/image requests. |
| Registration | Deployment and ClusterIP Service | Validates name/age, requests a persona, and stores the registration. |
| Persona | Deployment and ClusterIP Service | Selects an animal from the seeded catalogue. |
| Media | Deployment and ClusterIP Service | Serves the included animal SVG pictures. |
| MySQL | One-replica StatefulSet | Stores catalogue rows and registrations. |
| MySQL disk | PVC and dynamically provisioned PV | Provides persistent storage backed by encrypted EBS gp3. |

A visitor reaches the public NLB, which forwards to the frontend pod. Nginx forwards `/api/` to Registration and `/media/` to Media. Registration calls Persona and Media internally; only Registration and Persona connect to MySQL. The database and internal APIs have no public LoadBalancer Services.

The database is shared physically to keep this lab small, but the APIs use separate MySQL accounts. Registration can SELECT/INSERT registration rows. Persona can SELECT the animal catalogue. The SQL initialization account creates these grants; the application does not use MySQL root.

## 4 The pip root warning

Your original Python Dockerfile installed packages before the `USER 10001:10001` instruction. Docker builds use root by default, so pip reported a warning while installing system-wide inside that image. That message did not mean the running API container used root. It was a build-time warning, not an EKS failure. [S1]

The EKS edition now creates `/opt/venv` and installs packages into that virtual environment, then retains the non-root runtime user:

```dockerfile
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt
# Account creation and application copy occur in the complete Dockerfile.
USER 10001:10001
```

The complete Dockerfiles create the account before switching to it. The Helm chart additionally enforces a numeric runtime UID, `runAsNonRoot`, dropped capabilities, no privilege escalation, a default seccomp profile and a read-only root filesystem. Small writable `/tmp` volumes are supplied where needed.

Do not add `sudo pip install` to the application startup command or an init container. Packages belong in the image build. `PIP_ROOT_USER_ACTION=ignore` merely suppresses a warning; it does not change the user or improve isolation. This package uses a virtual environment instead of that suppression.

## 5 Costs and practical limits

This setup contains one EKS cluster, two on-demand t3.medium workers, one NAT Gateway, an NLB, a 5 GiB database disk, node disks, ECR images, S3 state/backups and short-retention control-plane logs. A single NAT serves the private subnets for this lab; it is a cost/availability compromise rather than a resilient multi-AZ egress design.

AWS lists standard-support EKS control-plane pricing at USD 0.10 per cluster-hour, approximately USD 73 for 730 hours, before all other resources. Your USD 10 budget alert will not cover a month of this cluster. Alerts do not stop resources automatically. Check the pricing pages and your regional calculator before leaving the lab running. [S17]

The application starts with one replica per service and one database replica. MySQL persistence survives pod recreation; it does not provide replication, cross-AZ failover or protection from a deleted disk. The default NLB exposes HTTP for demonstration. Add a domain, certificate and HTTPS listener before using real personal data or treating the public app as a production service.

## 6 Files to recognize

| Path | Responsibility |
| --- | --- |
| `services/*/Dockerfile` | Four custom application images. |
| `services/frontend/entrypoint.sh` | Reads the container's DNS resolver and generates Nginx configuration. |
| `database/init/` | Creates tables, seeds animals and creates restricted database users on a fresh database. |
| `terraform/bootstrap/` | One-time state bucket, ECR repositories, GitHub OIDC and CI roles. |
| `terraform/infra/` | VPC, routes, NAT, EKS, workers, IAM workload roles, access and add-ons. |
| `platform/` | Namespace security labels and the EBS StorageClass. |
| `charts/persona/` | Application Deployments/Services, MySQL StatefulSet, database init ConfigMap and NetworkPolicies. |
| `scripts/cloud/` | Small named steps invoked by workflows. |
| `.github/workflows/deploy.yaml` | Push-to-main delivery pipeline. |
| `.github/workflows/maintenance.yaml` | Manual status, persistence, backup and rollback operations. |

The local Compose file is intentionally absent from this cloud project. Keep your earlier local ZIP separately if you want that lab. The cloud scripts do not use its `.env`, secrets directory, networks or Docker volume.

## 7 Prepare the GitHub repository

Create a repository named **EKS-Persona** under your GitHub username or organization. Use the spelling and capitalization consistently in the AWS trust policy. A private repository is suitable; the provided PR checks run only on GitHub-hosted runners.

Upload or push the CONTENTS of the `EKS-Persona` folder, so `.github`, `terraform`, `charts` and `services` are at the repository root. Do not upload only the ZIP as one repository file, and do not create an extra nested `EKS-Persona/EKS-Persona` directory.

Before the bootstrap is ready, disable the Deploy EKS Persona workflow from its Actions menu. This prevents an initial push from trying to deploy with missing roles/variables. Re-enable it after the setup steps below. This is a one-time configuration step, not an approval required on every deployment.

Before AWS bootstrap, run Actions → OIDC identity info → Run workflow on main. This workflow needs no AWS credentials. It prints only selected identity metadata, including `repository_owner_id`, `repository_id` and the exact `sub`; it never prints the JWT. Copy both numeric IDs for the bootstrap variables. New repositories created after 15 July 2026 use an immutable default subject containing these IDs. A trust policy built only from owner/repository names will not match that default. [S21]

Keep `.gitignore`. Never commit database passwords, AWS access keys, Terraform state, saved plans, a `.terraform` directory, kubeconfig files or database dumps. Commit Terraform dependency lock files and the non-sensitive add-on version pin file generated below.

## 8 Open AWS CloudShell for one-time bootstrap

Sign in to the AWS console with a trusted IAM/SSO administrator identity and open CloudShell in `eu-north-1`. CloudShell uses your console identity; you do not need to place AWS keys in GitHub. The initial operator must be able to create IAM roles/OIDC, S3 and ECR. The infrastructure policy is a lab policy with region-wide EC2 networking operations; review `terraform/bootstrap/main.tf` before using a shared account.

Clone the repository in CloudShell:

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/EKS-Persona.git
cd EKS-Persona
aws sts get-caller-identity
```

For a private repository, authenticate Git over HTTPS with GitHub CLI/device login or a fine-grained token at Git's password prompt. Give it access only to this repository. Do not embed a token in the URL or source files. The later CloudShell push uses the same GitHub authentication, which is distinct from AWS console authentication.

CloudShell includes AWS CLI, Git and Python. Install Terraform if it is absent. These commands install the same pinned CLI used by Actions:

```bash
mkdir -p "$HOME/.local/bin"
work="$(mktemp -d)"
cd "$work"
curl -fsSLO https://releases.hashicorp.com/terraform/1.15.8/terraform_1.15.8_linux_amd64.zip
curl -fsSLO https://releases.hashicorp.com/terraform/1.15.8/terraform_1.15.8_SHA256SUMS
grep ' terraform_1.15.8_linux_amd64.zip$' terraform_1.15.8_SHA256SUMS | sha256sum --check
unzip terraform_1.15.8_linux_amd64.zip
install -m 0755 terraform "$HOME/.local/bin/terraform"
export PATH="$HOME/.local/bin:$PATH"
cd "$HOME/EKS-Persona"
terraform version
```

If you cloned elsewhere, return to that actual project directory instead of `$HOME/EKS-Persona`. Checksums verify download integrity; organizational release verification can additionally validate HashiCorp's signed checksum file. All these commands run in CloudShell, not on your laptop.

## 9 Create bootstrap resources

Copy the example and edit it in CloudShell's editor:

```bash
cp terraform/bootstrap/terraform.tfvars.example terraform/bootstrap/terraform.tfvars
```

Set `github_owner` to your exact GitHub owner, `github_owner_id` and `github_repository_id` to the numeric IDs from OIDC identity info, `repository` to `EKS-Persona`, and `region` to `eu-north-1`. Set `state_bucket` to a globally unique name such as `eks-persona-state-123456789012-eu-north-1`, using YOUR account number.

AWS allows only one OIDC provider per URL in an account. Check whether GitHub's provider already exists:

```bash
account_id="$(aws sts get-caller-identity --query Account --output text)"
aws iam get-open-id-connect-provider --open-id-connect-provider-arn "arn:aws:iam::$account_id:oidc-provider/token.actions.githubusercontent.com"
```

If that succeeds, set `create_github_oidc = false`. If it returns NoSuchEntity, leave it true. Do not create a duplicate provider or delete an existing shared provider.

```bash
terraform -chdir=terraform/bootstrap init
terraform -chdir=terraform/bootstrap fmt
terraform -chdir=terraform/bootstrap validate
terraform -chdir=terraform/bootstrap plan
terraform -chdir=terraform/bootstrap apply
terraform -chdir=terraform/bootstrap output
```

Review the plan and approve the local CloudShell apply when it matches the intended bootstrap. It creates a private/versioned/encrypted state bucket, four immutable-tag ECR repositories, two CI roles and optionally the GitHub OIDC provider. The protected bucket and repositories are intentionally kept separate from disposable EKS infrastructure.

The outputs provide `state_bucket`, `infra_role_arn`, `deploy_role_arn` and `ecr_registry`. Record them in GitHub variables next. Terraform has not created EKS yet.

## 10 Move bootstrap state to S3

The bucket could not hold its own Terraform state before it existed. The first bootstrap apply therefore uses CloudShell local state. Immediately migrate it to the newly created bucket:

```bash
state_bucket="$(terraform -chdir=terraform/bootstrap output -raw state_bucket)"
cp terraform/bootstrap/backend.tf.example terraform/bootstrap/backend.tf
terraform -chdir=terraform/bootstrap init -migrate-state \
  -backend-config="bucket=$state_bucket" \
  -backend-config="key=bootstrap/terraform.tfstate" \
  -backend-config="region=eu-north-1" \
  -backend-config="use_lockfile=true"
```

Answer yes when Terraform asks to copy existing state to the new backend. The bootstrap state uses `bootstrap/terraform.tfstate`; the delivery pipeline uses `infra/terraform.tfstate`. They share a bucket but have different keys. The CI infrastructure role can access only the `infra/` state prefix, not the bootstrap state. [S9]

Native S3 lock files prevent concurrent Terraform writers. Bucket versioning helps recover a prior state version, and pipeline concurrency prevents two delivery jobs from racing. These protections do not make a Terraform state file safe to publish in Git.

## 11 Pin provider and EKS add-on versions

Still in the CloudShell project directory:

```bash
export AWS_REGION=eu-north-1
python3 scripts/cloud/resolve-addon-versions.py
terraform -chdir=terraform/infra init -backend=false
terraform -chdir=terraform/infra fmt
terraform -chdir=terraform/infra validate
```

The Python script asks AWS for EKS 1.36-compatible versions in this region, prefers recommended versions, and writes `terraform/infra/addons.auto.tfvars.json`. The pipeline consumes those pins. It does not silently select a new add-on release on every push.

Terraform init generates each directory's `.terraform.lock.hcl`. These lock files fix provider selections and checksums. Review and commit them along with the generated public version pins and backend configuration:

```bash
git add terraform/bootstrap/backend.tf
git add terraform/bootstrap/.terraform.lock.hcl terraform/infra/.terraform.lock.hcl
git add terraform/infra/addons.auto.tfvars.json
git add terraform/bootstrap/main.tf terraform/infra
git diff --cached --stat
git commit -m "Configure Terraform backend and pin EKS providers and addons"
git push origin main
```

The `.tfvars` files containing account-specific setup remain ignored. `addons.auto.tfvars.json` contains only public component version names and is intentionally committed. Keep deployment disabled until the GitHub settings are complete. EKS 1.36 is the chosen reference minor version; check current AWS support before changing it, and keep kubectl, namespace policy version and add-on pins aligned. [S14]

## 12 Configure repository variables

In GitHub, open Settings → Secrets and variables → Actions → Variables. Add repository variables exactly as shown:

| Variable | Value |
| --- | --- |
| `AWS_REGION` | `eu-north-1` |
| `STATE_BUCKET` | The bootstrap bucket output |
| `INFRA_ROLE_ARN` | The bootstrap infrastructure role output |
| `DEPLOY_ROLE_ARN` | The bootstrap deployment role output |
| `OPERATOR_PRINCIPAL_ARN` | Your trusted operator's permanent IAM role/user ARN |
| `EXTRA_API_CIDRS` | `[]` for the default hosted-runner-only API access |

Use an IAM ARN such as `arn:aws:iam::123456789012:role/YourAdminRole`, including any actual role path. Do not use an STS assumed-role session ARN from a temporary session, and do not use an account root ARN. Find the permanent role ARN in IAM if `get-caller-identity` reports an assumed-role session.

The operator access entry allows that IAM principal to administer Kubernetes when its network path is allowed; it does not grant new AWS IAM permissions to the principal. The automatic deployment itself uses the CI roles, not that operator's credentials.

## 13 Configure database password secrets

Generate three values once in CloudShell:

```bash
python3 scripts/cloud/generate-passwords.py
```

The output contains three `NAME=value` lines. In GitHub's Actions Secrets tab, create a repository secret for each NAME and paste only its value:

- `MYSQL_ROOT_PASSWORD`
- `REGISTRATION_PASSWORD`
- `PERSONA_PASSWORD`

Each is a 48-character hexadecimal string. This matches the SQL initialization script's validation. Keep the original values in your password manager. Do not rerun the generator and overwrite the secrets on every deployment.

During deployment, a Python script creates the Kubernetes `persona-db` Secret from these environment inputs. Plaintext passwords are not passed through Helm values or Terraform, so they are not stored in Terraform state or Helm release values. Kubernetes Secret data is base64-encoded; base64 is not encryption. Namespace access still matters because an editor with sufficient workload/exec permissions can reach application secrets.

If the Kubernetes Secret already exists, the script checks that the supplied values match and preserves it. It fails if they differ. Changing a secret file alone does not change the MySQL password stored on a retained disk; rotation requires an explicit coordinated database-and-secret change.

## 14 Understand OIDC and the role boundaries

GitHub grants this deployment job `id-token: write`, which lets the AWS credentials action request a GitHub OIDC token. AWS STS evaluates its audience and subject against the role trust policy. The reference subject is exactly:

```text
repo:YOUR_GITHUB_USERNAME@OWNER_ID/EKS-Persona@REPOSITORY_ID:ref:refs/heads/main
```

The audience is `sts.amazonaws.com`. Compare the complete constructed subject against the OIDC identity info output. A different repository, numeric ID, branch, or owner does not match this trust policy. No AWS access-key/secret-key pair is stored in GitHub. If you later add a GitHub Environment to the job, its OIDC subject changes; update the trust policy to the documented environment form at the same time. [S2]

The infrastructure role can reconcile this lab's EKS/VPC resources, manage prefixed workload roles, prepare cluster-level Kubernetes resources and push ECR images. It has cluster-admin access for platform preparation. Its EC2 networking permissions are region-wide, so it is a high-trust lab role, not a universal least-privilege production policy.

The deployment role can describe the EKS cluster, access application resources through namespace-scoped `AmazonEKSEditPolicy`, and read/write only the `backups/` prefix for maintenance backups. It cannot create IAM roles, networking, namespaces or StorageClasses. EKS access entries connect AWS IAM identities to Kubernetes permissions. Possessing an AWS role alone is not sufficient Kubernetes authorization. [S3, S4]

Both roles trust main because the same protected delivery workflow uses both. Switching roles reduces accidental use of infrastructure permissions during Helm operations; it is not a hard isolation boundary against malicious code merged into main. Protect main and review workflow/IAM changes. Stronger production separation uses protected environments and independent runners/jobs with appropriate private networking.

## 15 Understand the runner network path

GitHub-hosted runner addresses change. The script reads the current runner's IPv4 address from AWS's check-IP endpoint, validates it, and supplies a `/32` to Terraform. EKS permits public API traffic from that address, plus any explicitly configured extra CIDRs. The private API endpoint remains enabled for cluster-internal traffic.

All cloud steps stay on that same runner so the allowlist remains valid through Helm deployment. The application URL is separate: visitors reach the NLB, not the EKS control-plane API. MySQL does not become public when the API endpoint is enabled.

The final runner CIDR remains configured after the workflow finishes. A later deployment/maintenance run replaces it through Terraform with the new runner address. This is not a persistent network identity or a permanent laptop dependency; AWS authentication still applies even from an allowed address. For a strict private-only control plane, use the EC2-in-VPC runner option in section 29 rather than relying on hosted-runner IP updates.

## 16 Start the first deployment

Re-enable Deploy EKS Persona in GitHub Actions. Use Run workflow on main, or push a small source/documentation change to main after settings and pins are ready.

Watch the two jobs in Actions. Validation should finish before any AWS creation. The first infrastructure deployment can take tens of minutes while EKS, nodes and add-ons become ready. Subsequent pushes usually reconcile existing resources and roll out new image tags.

The runner automatically installs the pinned Terraform CLI and checksum-verified Helm 4/kubectl binaries. You do not install those tools on your laptop. GitHub's Ubuntu hosted runner already supplies Docker, AWS CLI and standard shell tools; `check-tools.sh` verifies availability before provisioning.

## 17 What Terraform creates

Terraform initializes the S3 backend, validates configuration, calculates a plan, saves that exact plan to a temporary runner file and applies it. The plan file is deleted afterward. The workflow is serialized so pushes cannot run competing applies against the same environment.

The network contains a VPC, public/private subnets across two Availability Zones, an internet gateway and one NAT Gateway. Worker nodes receive no public subnet placement. Their outbound pulls and API calls use NAT. Public subnets provide the NLB's internet-facing placement.

EKS creates the managed control plane. A managed node group supplies two on-demand AL2023 t3.medium workers. EKS access entries grant the infrastructure and operator roles platform access and the deployment role application namespace access. The Terraform config requests standard support rather than intentionally keeping an old minor version on extended support.

The selected add-ons provide VPC pod networking, Kubernetes Service networking, DNS, Pod Identity and EBS storage provisioning. VPC CNI network policy support is explicitly enabled; creating NetworkPolicy objects without an enforcing network implementation would not isolate traffic. [S13]

The infrastructure and application are deliberately separate layers. Terraform's AWS provider can create EKS before a Kubernetes provider exists. The later scripts/Helm connect after the cluster is ready, avoiding a same-apply Kubernetes-provider initialization dependency.

## 18 What the platform script does

After Terraform apply, `platform.sh` creates a temporary kubeconfig for the infrastructure role. It waits for access propagation and ready workers, then applies the `persona` Namespace and `eks-persona-gp3` StorageClass. These cluster-level objects are outside the application chart because the Helm role is namespace-scoped.

The namespace enforces the Kubernetes restricted pod-security profile. Application pods and MySQL declare numeric non-root users, no privilege escalation, dropped capabilities and a default seccomp profile. The official MySQL image uses UID/GID 999 in the chart; check the actual image user when changing its tag.

The script installs AWS Load Balancer Controller through a separately pinned Helm release in `kube-system`. Terraform supplies its own Pod Identity role and the official versioned IAM policy. Region and VPC ID are passed explicitly rather than relying on metadata discovery. Gateway API features are disabled because this project uses an ordinary LoadBalancer Service. No ingress or Gateway object is needed for this NLB example. [S20]

On a later controller/chart upgrade, review the corresponding IAM policy and CRDs. Helm installs chart CRDs on first installation, but controller CRD upgrades require deliberate handling; do not assume an ordinary Helm upgrade updates them.

## 19 What image building does

For each of frontend, registration, persona and media, the build script builds a Docker image from that service's directory and tags it with the exact Git commit SHA. It verifies that the image's configured runtime UID is not zero before pushing.

ECR repositories use immutable tags. Re-running the same commit reuses the already-pushed image instead of attempting to overwrite that SHA. A source change produces a new commit and therefore a new tag. This gives you a concrete link from running image to source revision.

ECR scan-on-push is enabled. The script waits for a scan result, logs severity counts and blocks a release with CRITICAL findings. HIGH findings remain visible and need review. A scan is one check, not proof that the image is secure; base images and dependencies still need regular patching. Exact base-image digest pinning and reviewed Action commit SHA pins are sensible production hardening steps beyond this readable lab recipe.

EKS worker roles need ECR pull permissions. The pipeline's ECR login credentials do not get copied into Kubernetes, and same-account ECR pulls use the node's AWS role. Application pods receive no AWS role merely because the node can pull images.

## 20 What Helm installs

The workflow switches to the deployment role, updates its temporary kubeconfig, supplies the existing-or-new database Secret, synchronizes chart SQL initialization files and lints the chart. It then runs the equivalent of:

```bash
helm upgrade --install persona charts/persona --namespace persona \
  --set-string "image.registry=$IMAGE_REGISTRY" \
  --set-string "image.tag=$IMAGE_TAG" \
  --rollback-on-failure --wait --timeout 10m --history-max 10
```

Helm renders values into YAML and submits resources to the EKS API. Kubernetes schedules pods and reconciles them afterward. Readiness probes prevent traffic reaching unready APIs; liveness probes check the process without turning a database outage into restarts of every dependency. Startup probes allow initialization time.

The chart creates four application Deployments, their Services, MySQL's StatefulSet and Services, one init ConfigMap and NetworkPolicies. Each app uses a read-only root filesystem and a small writable temporary volume. The app source and pictures are inside images. The SQL ConfigMap is a first-initialization input, not a way to run Python/HTML source from ConfigMaps.

Helm 4 uses `--rollback-on-failure`. Older Helm 3 examples often show `--atomic`. The package deliberately checks for Helm 4 so those command-line differences do not surprise the runner. Rollback can restore a prior application release; it cannot undo arbitrary database schema/data changes. [S15]

## 21 Understand PV PVC and EBS provisioning

MySQL's StatefulSet contains a `volumeClaimTemplates` entry named `data`. Its single pod is `mysql-0`; the resulting claim is `data-mysql-0`. The claim requests 5 GiB from `eks-persona-gp3` and uses `ReadWriteOncePod` to constrain the volume to one pod. [S7, S8]

`WaitForFirstConsumer` delays disk provisioning until scheduling can select an appropriate Availability Zone. The EBS CSI driver then creates the encrypted gp3 disk, exposes it as a PV, binds the PVC, and mounts it into the MySQL pod. You do not create a second manual EBS disk or a hand-written static PV for this path. [S5]

The physical mount is `/var/lib/mysql`; MySQL's data directory is `/var/lib/mysql/data`. The extra subdirectory avoids initializing into the filesystem root, which can contain `lost+found`. A writable socket directory and `/tmp` are supplied separately. `fsGroup` allows the non-root MySQL UID to write the mounted storage.

EBS is Availability-Zone scoped. A replacement MySQL pod must run on compatible capacity in the disk's zone. If no node is available there, it waits rather than attaching the disk across zones. With only two lab workers, a node outage can therefore interrupt database availability.

PVC retention is Retain for StatefulSet deletion/scaling, and the StorageClass reclaim policy is Retain. These are two different controls: one preserves the claim; the other preserves the backing storage when a claim is deleted. They help avoid accidental loss but also leave billable storage that requires intentional cleanup. [S7, S8]

## 22 Understand database initialization

On a fresh disk, the official entrypoint initializes MySQL, creates the `animal_persona` database and runs `01-schema.sql` followed by `02-users.sh`. The SQL seeds eight persona rows; the shell script creates the two application accounts and grants. The mounted Secret supplies the three passwords. [S16]

On a retained disk, MySQL starts with the existing tables, users and records. It does not rerun the initialization files. Updating the seed SQL in Git and pushing will not migrate an existing database.

For a future table change, write a versioned migration, test it on a backup copy and run it explicitly with suitable schema permissions. Prefer backward-compatible changes so application rollback remains possible. Do not delete the PVC just to apply a new schema to data you want to keep.

Your local Docker registrations do not automatically appear in this new EBS database. This deployment starts with the same seeded animals but fresh registration data. To move earlier records, make a logical SQL dump from the source database and restore it into the cloud database as a separate intentional migration.

## 23 Open and verify the application

When deployment succeeds, the workflow summary contains an application URL like:

```text
http://k8s-persona-frontend-EXAMPLE.elb.eu-north-1.amazonaws.com
```

Open the actual URL from YOUR workflow summary in your browser. There is no `localhost:8080`, `localhost:8081`, or laptop port-forward in this path. NLB allocation, DNS propagation and target health may take a few minutes; the script waits before testing.

Register a sample name and age. You should see an animal picture and funny description. Refreshing restores that browser's saved registration ID and fetches the saved result from MySQL. The assignment is a playful random match, not an assessment inferred from personal information.

The smoke test creates a sample record through the public frontend, reads it back, loads the selected picture and checks invalid input rejection. This proves more than a pod merely showing Running: it exercises the actual application route through NLB, frontend, APIs and MySQL.

## 24 Operate entirely through GitHub Actions

Open Actions → EKS Persona maintenance → Run workflow, select main and choose one operation. It uses a new GitHub-hosted runner, updates the API allowlist through the same Terraform state, and then switches to the namespace role.

| Operation | Result |
| --- | --- |
| status | Lists pods/Services/PVCs and recent events/application logs without printing Secret values. |
| persistence | Saves a record, restarts the MySQL StatefulSet and verifies the same record/animal afterward. |
| backup | Creates a logical SQL dump and uploads it to the private S3 `backups/` prefix. |
| rollback | Restores a chosen existing Helm revision and reruns the public smoke test. |

Persistence intentionally interrupts the single MySQL instance briefly. It recreates the pod, not the PVC or disk. Run it when you can tolerate a short lab outage. It verifies retained storage across a pod restart; it is not a simulated disk-loss or cross-zone recovery test.

The maintenance workflow first confirms that the cluster exists. It will not intentionally create a missing cluster as a side effect of asking for status. Normal Terraform reconciliation still runs for the existing cluster so that the new runner's network access matches state.

You can also inspect EKS resources, EBS disks, NLB target health and CloudWatch control-plane logs through the AWS console. No laptop CLI connection is required for these operations.

## 25 Back up and restore

Choose backup in the maintenance workflow. It runs `mysqldump --single-transaction` inside MySQL, uploads the SQL file to `s3://STATE_BUCKET/backups/RUN_ID/animal-persona.sql` with server-side encryption, and removes the runner's temporary file. The workflow summary identifies the exact private object key.

The same private bucket stores state and backups under different prefixes with different IAM access. This keeps the lab small. A production system would normally separate backup ownership, retention, recovery objectives and potentially the account. The backup contains application tables, not a transferable replacement for MySQL user/password configuration.

For a restore, first make a current backup and stop new registrations. Restore is a data-changing operation. Use CloudShell with the operator identity and an allowed network path, or add a reviewed, explicitly confirmed restore workflow. A CloudShell session must be added to `EXTRA_API_CIDRS` before it can reach the restricted public EKS API; run the deployment/maintenance workflow to apply that change.

With an authorized CloudShell kubeconfig, the restore commands are:

```bash
aws s3 cp s3://YOUR_STATE_BUCKET/backups/YOUR_RUN_ID/animal-persona.sql restore.sql
kubectl -n persona exec -i mysql-0 -- sh -c 'MYSQL_PWD="$(cat /run/secrets/mysql_root_password)" exec mysql -uroot animal_persona' < restore.sql
rm -f restore.sql
```

Use a real verified backup key. Afterwards rerun the smoke test and inspect the expected records. A restore drill is necessary before relying on backups; simply seeing a SQL object in S3 is insufficient evidence of recoverability.

## 26 Troubleshoot by the failing stage

| Symptom | Likely cause and check |
| --- | --- |
| Validation fails before AWS | Missing committed provider lock/add-on pins, invalid chart/YAML, missing dependency or application test failure. Fix this first; infrastructure has not started. |
| OIDC AssumeRoleWithWebIdentity denied | Owner/repository IDs or main subject/audience mismatch, wrong role ARN, or missing `id-token: write`. Adding an Environment also changes the subject. |
| Terraform state AccessDenied | Wrong bucket/region, role lacks the `infra/` object/lock permissions, or bootstrap migration/settings are incomplete. |
| IAM/EC2 AccessDenied during apply | Organization SCP/boundary restriction or an AWS operation outside the lab policy. Identify the exact denied action; do not attach AdministratorAccess to the delivery role as a shortcut. |
| EKS API timeout | Terraform/Helm ran on different hosted IPs, current-IP lookup failed, an extra CIDR is malformed, or a restricted/private endpoint has no network path. |
| Kubernetes Unauthorized or Forbidden | Check the EKS access entry and namespace access policy, not just AWS IAM. Infrastructure prepares Namespace/StorageClass; deploy role cannot create them. |
| Workers not Ready | Inspect node group health, subnet routes/NAT, address availability and node role permissions in AWS. |
| EBS PVC Pending | Check EBS CSI readiness and Pod Identity permissions. Before the first consumer is schedulable, WaitForFirstConsumer waiting can be expected. |
| MySQL pod Pending after a node problem | The EBS volume's AZ has no suitable node capacity, or a previous attachment/pod has not released the single-pod claim. |
| MySQL permission denied | Verify image UID/GID, fsGroup and the writable data/socket mounts. Do not remove all pod security controls without locating the failing path. |
| MySQL initialization directory error | Verify `--datadir=/var/lib/mysql/data`; do not initialize into an EBS filesystem root containing lost+found. |
| MySQL access denied after changing GitHub Secrets | Passwords on the existing disk were not rotated. Restore matching inputs or perform coordinated SQL and Secret rotation. |
| ImagePullBackOff | Wrong ECR URI/tag, missing node pull permission or broken NAT/registry connectivity. The pipeline ECR login is not the worker's identity. |
| NLB address remains pending | Check controller logs, Pod Identity/IAM permissions, public-subnet role tags and Service events. |
| NLB target unhealthy | Check frontend readiness, container port 8080, health path, security-group rules and frontend ingress NetworkPolicy. |
| API returns 503 | Inspect Registration/Persona readiness, MySQL and allowed internal network paths. |
| Nginx cannot resolve backend | Check the generated resolver from pod resolv.conf, CoreDNS and DNS NetworkPolicy; Docker's 127.0.0.11 is not an EKS resolver. |
| ECR scan blocks release | Patch the base/dependency source, commit and rebuild. Scan quota/errors or unsupported scanning mode need registry configuration review. |
| Helm timeout | Read events and pod logs. Fix scheduling/storage/readiness; merely increasing timeout will not fix a missing IAM permission. |

The automatic diagnostics intentionally avoid dumping Secret objects or environments. Never add `set -x`, `printenv` or `kubectl get secret -o yaml` to the workflow while debugging credentials.

## 27 Make and roll back a normal change

Edit application source, commit and push to main. Validation runs first. Terraform usually keeps the same infrastructure, except for the hosted runner API CIDR. The four SHA-tagged images are built or reused, Helm updates the Deployments, Kubernetes performs rolling updates, and the public smoke test runs.

The MySQL StatefulSet continues mounting the same claim. A new API image does not intentionally recreate the database or erase records. However, changing an image or manifest can still restart pods; a one-replica database has an outage during its restart.

Prefer reverting a faulty source commit and pushing the revert, which makes Git match the desired running release. For emergency application rollback, use the maintenance rollback option with an existing positive Helm revision. The next normal deployment reapplies Git's desired version. Database migrations and restore decisions remain separate.

## 28 Where images belong and when to use S3

This edition keeps eight static SVG animal pictures inside the Media image. It requires no image volume, no EFS and no S3 mount. The pictures are reproducible assets, while user registrations are changing data on EBS.

S3 remains the appropriate next store when you want to update pictures independently, upload new animals or practise pod-level AWS access. Store an object key such as `animals/panda.svg` in MySQL. Move the assets to a private S3 bucket, give only Media an S3-read Pod Identity role, and change its URL endpoint to return short-lived presigned URLs. The browser downloads the object directly; the service does not mount S3 as a database filesystem.

Also update frontend Content Security Policy to permit the chosen S3/CloudFront image origin. A private bucket's plain object URL will not load without authorization. CloudFront with origin access control can be a later caching/stable-URL enhancement. EBS remains MySQL's disk; S3 images and MySQL PV/PVC solve different storage needs.

## 29 Optional EC2 self-hosted runner

The default workflow is already fully cloud-based and needs no self-hosted runner. Move to EC2 when you want predictable networking, private API access or controlled build capacity. You do not need to go back to WSL.

After the hosted workflow creates the VPC, launch a dedicated Ubuntu EC2 runner in its private subnet with NAT egress. Attach a minimal instance profile for Systems Manager, enforce IMDSv2, and use Session Manager rather than opening SSH. This host role is for managing the machine; do not attach the infrastructure CI role as its instance profile. The Actions job can continue using OIDC for its separate CI credentials.

Install Docker Engine, Git, Python/venv, curl and AWS CLI on the instance. In GitHub, go to repository Settings → Actions → Runners → New self-hosted runner → Linux x64. Follow the CURRENT generated download, checksum and registration commands on that page. The registration token is short-lived, so do not put it into a committed script. Register a dedicated label `eks-persona` and start the runner as an ordinary user with required Docker access. [S10, S11]

For persistence across reboots, install the runner's supplied Linux service after registration. Keep it patched. Docker access on a runner is high trust; do not use a personal/shared host or send untrusted fork PR code to it. Keep PR checks on GitHub-hosted runners. [S12]

Change only the cloud deployment and maintenance job runner selection:

```yaml
runs-on: [self-hosted, linux, x64, eks-persona]
```

Validation may remain hosted. The installer writes tools into Actions runner temporary directories, so it does not need to change a user's shell profile. The reference installer expects Linux x64. A runner in the same VPC can reach the private EKS endpoint. For a private-only endpoint, deliberately update Terraform to disable public access and remove the hosted-IP authorization step. A GitHub-hosted runner will then be unable to deploy unless you separately provide private connectivity.

Keep this EC2 host's lifecycle separate from the resources it destroys. A runner cannot reliably tear down its own network/instance and continue reporting results. Ephemeral EC2 runners or a managed runner pool are preferable for a larger production delivery system.

## 30 Cleanup without losing track of data

Stopping the GitHub runner or finishing a workflow does not stop EKS billing. Scaling workers to zero does not remove the EKS control-plane charge or NAT/NLB/storage charges. Use a planned teardown when the lab is finished.

First run the backup maintenance operation and record its S3 key. Inspect the PVC's bound PV and EBS volume ID before deleting the cluster. Because retention is intentional, a Terraform destroy does not automatically erase the dynamically provisioned database disk.

For a teardown from CloudShell, allow that CloudShell session's current public IP through the `EXTRA_API_CIDRS` repository variable and run maintenance to reconcile the allowlist. Use the operator IAM identity, install kubectl/Helm from their official verified distributions, and create a kubeconfig there. These are cloud administration commands, not laptop setup:

```bash
aws eks update-kubeconfig --region eu-north-1 --name eks-persona-dev
kubectl -n persona get pvc
pv_name="$(kubectl -n persona get pvc data-mysql-0 -o jsonpath='{.spec.volumeName}')"
volume_id="$(kubectl get pv "$pv_name" -o jsonpath='{.spec.csi.volumeHandle}')"
printf 'Retained database disk: %s\n' "$volume_id"
helm uninstall persona --namespace persona
```

Wait for the frontend Service deletion to remove the NLB and target groups before removing the controller or VPC. Confirm through the EC2 load-balancer console. Deleting the controller first can leave load-balancer resources/finalizers behind.

If you intend to keep the database disk, retain the EBS volume ID and backup key. The disk alone is not automatically reattached by a newly created cluster; recovery needs an explicit PV binding/import or a logical restore. If you intend to erase it, first verify the backup, delete the released claim/PV as appropriate and manually delete the correctly identified detached disk in the EC2 console. This is a deliberate data deletion step, not part of normal application redeployment.

Prepare the infra backend in CloudShell with the same bucket/key/region, supply the same account-specific values from `terraform/infra/terraform.tfvars.example`, and use the committed add-on pins. Then review the destroy plan:

```bash
terraform -chdir=terraform/infra init \
  -backend-config="bucket=YOUR_STATE_BUCKET" \
  -backend-config="key=infra/terraform.tfstate" \
  -backend-config="region=eu-north-1" \
  -backend-config="use_lockfile=true"
terraform -chdir=terraform/infra plan -destroy
terraform -chdir=terraform/infra destroy
```

Disable deployment/maintenance workflows before teardown or avoid new pushes, so an automatic push cannot recreate the cluster while you remove it. Do not destroy the separate bootstrap stack or its state bucket casually; it contains remote state, backups and shared delivery identities. Check the console for retained EBS volumes, ECR storage and old lab clusters afterward. Remove a temporary CloudShell CIDR from repository settings when administration is finished.

## 31 Completion checklist and interview explanation

You have completed the deployment when the GitHub pipeline succeeds, its public URL loads, a registration is saved/read back, the selected picture loads, and the manual persistence test passes. You should also create a backup and practise a restore before describing recovery as tested.

A concise interview explanation is: "I containerized four services, built immutable images in GitHub Actions and pushed them to ECR. Terraform provisioned a private-node EKS environment with controlled API access and Pod Identity. Helm deployed the app, and a MySQL StatefulSet used an encrypted EBS-backed PVC. I validated the public request path and record persistence across database pod recreation, and automated logical backups to private S3."

Use that explanation only for steps you actually execute and verify. The supplied code and this guide are preparation, not evidence that AWS resources have already been provisioned. Read `VALIDATION.md` for the checks completed before packaging.

## 32 Official references

Reference labels S1 through S23 point to `docs/SOURCES.md`. These sources cover pip behavior, OIDC, EKS permissions, EBS/StatefulSets, state locking, runner configuration, network policy, supported versions, Helm, MySQL initialization, pricing and load balancing. Recheck current releases and regional availability before an upgrade or a fresh deployment.
