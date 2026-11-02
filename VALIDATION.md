# Validation and deployment boundary

Prepared 2 November 2026.

Completed locally in the preparation environment:

- 13 application checks passed against real FastAPI handlers with in-process HTTP routing and an explicit SQLite database adapter. They cover saved assignments, invalid input, duplicate names, Unicode/SQL parameterization, all eight images, readiness and service/database failures.
- All Python source compiled; Bash and frontend entrypoint shell scripts passed syntax checks; frontend JavaScript passed Node syntax checking.
- Terraform files were parsed as HCL. Workflow and platform YAML were parsed. This is syntax inspection, not Terraform provider validation or an AWS apply.

Not executed in this environment: Docker image builds, real MySQL under the Kubernetes security context, Terraform init/validate/plan against the AWS provider, Helm CLI lint/render, AWS IAM authorization, EBS attachment, NLB reconciliation, public smoke test, persistence test, or restore. No AWS resources were created.

The GitHub pipeline runs real Terraform validation and Helm lint/render before provisioning. The first deployment remains a reference implementation that needs validation in your AWS account. IAM boundaries/SCPs, quotas, compatible component versions and network behavior can require account-specific adjustments.

One-time prerequisites are intentionally not fabricated: generate and commit both .terraform.lock.hcl files and terraform/infra/addons.auto.tfvars.json in CloudShell, configure GitHub variables/secrets and bootstrap AWS OIDC roles before enabling delivery. The guide explains each step.

The default uses GitHub-hosted runners and a public NLB URL. No WSL runner, laptop Docker daemon, or local Kubernetes connection is part of delivery. An EC2 self-hosted runner alternative is documented.
