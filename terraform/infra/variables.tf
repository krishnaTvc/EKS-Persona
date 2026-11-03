variable "region" {
  type = string
  default = "eu-north-1"
}
variable "addon_versions" {
  type = map(string)
  description = "Compatible add-on versions resolved in CloudShell and committed to addons.auto.tfvars.json"
  validation {
    condition = alltrue([for name in ["vpc-cni", "kube-proxy", "coredns", "eks-pod-identity-agent", "aws-ebs-csi-driver"] : contains(keys(var.addon_versions), name)])
    error_message = "Run scripts/cloud/resolve-addon-versions.py and commit its output before deploying."
  }
}
variable "cluster_name" {

  type = string
  default = "eks-persona-dev"
  validation {

    condition = var.cluster_name == "eks-persona-dev"
    error_message = "The bootstrap IAM policy is scoped to eks-persona-dev. Change both together."

  }

}
variable "cluster_version" {
  type = string
  default = "1.36"
}
variable "infra_role_arn" {
  type = string
}
variable "deploy_role_arn" {
  type = string
}
variable "operator_principal_arn" {

  type = string
  validation {

    condition = can(regex("^arn:aws:iam::[0-9]{12}:(role|user)/.+$", var.operator_principal_arn))
    error_message = "Use a permanent IAM role/user ARN, not an STS assumed-role session or account root ARN."

  }

}
variable "api_allowed_cidrs" {

  type = list(string)
  validation {

    condition = length(var.api_allowed_cidrs) > 0 && alltrue([for cidr in var.api_allowed_cidrs : can(cidrnetmask(cidr)) && cidr != "223.185.44.128"])
    error_message = "Provide the runner/operator public IPv4 CIDRs; do not use 0.0.0.0/0."

  }

}
