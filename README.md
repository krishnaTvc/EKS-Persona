# EKS Persona

Four Dockerized application services and one persistent MySQL StatefulSet on Amazon EKS.

Read **[docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)** for the complete deployment sequence.

Git push to main → GitHub Actions → GitHub-hosted Ubuntu runner → Terraform → scripts → Helm → EKS → public NLB application URL.

One-time AWS bootstrap runs in AWS CloudShell. The build and deployment need no WSL, laptop Docker installation, local runner, or local kubectl connection. The reference pipeline uses one hosted runner for all cloud steps and authorizes that runner's current public IPv4 /32 in the EKS API allowlist. A later run replaces this address through Terraform. AWS IAM authentication and namespace authorization still apply. An EC2 self-hosted runner alternative is documented separately.

This creates a NEW VPC and cluster named `eks-persona-dev`; it does not adopt the old EKS lab. MySQL uses an encrypted gp3 EBS volume. Animal pictures are baked into the Media image; optional S3 migration is explained in the guide.

See [VALIDATION.md](VALIDATION.md) for checks actually performed. No AWS deployment has been executed in preparing this bundle. The bootstrap needs trusted AWS administrator permissions. The lab infrastructure IAM policy allows region-wide EC2 networking operations; review it before using a shared or production account.
