terraform {

  required_version = ">= 1.10, < 2.0"
  required_providers {

    aws = {
      source = "hashicorp/aws", version = "~> 6.0"
    }

  }

}

provider "aws" {

  region = var.region
  default_tags {
    tags = {
      Project = "eks-persona", ManagedBy = "Terraform"
    }
  }

}

variable "region" {
  type = string
  default = "eu-north-1"
}
variable "github_owner" {
  type = string
}
variable "github_owner_id" {
  type = string
  description = "Numeric repository_owner_id from OIDC identity info"
  validation {
    condition = can(regex("^[0-9]+$", var.github_owner_id))
    error_message = "Copy the numeric owner ID from the OIDC identity info workflow."
  }
}
variable "github_repository_id" {
  type = string
  description = "Numeric repository_id from OIDC identity info"
  validation {
    condition = can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "Copy the numeric repository ID from the OIDC identity info workflow."
  }
}
variable "repository" {
  type = string
  default = "EKS-Persona"
}
variable "state_bucket" {
  type = string
}
variable "create_github_oidc" {
  type = bool
  default = true
}
data "aws_caller_identity" "current" {

}

locals {

  account = data.aws_caller_identity.current.account_id
  oidc_arn = "arn:aws:iam::${local.account}:oidc-provider/token.actions.githubusercontent.com"
  cluster = "eks-persona-dev"

}

resource "aws_s3_bucket" "state" {

  bucket = var.state_bucket
  lifecycle {
    prevent_destroy = true
  }

}
resource "aws_s3_bucket_versioning" "state" {

  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }

}
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {

  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }

}
resource "aws_s3_bucket_public_access_block" "state" {

  bucket = aws_s3_bucket.state.id
  block_public_acls = true
  block_public_policy = true
  ignore_public_acls = true
  restrict_public_buckets = true

}
resource "aws_s3_bucket_policy" "state_tls" {

  bucket = aws_s3_bucket.state.id
  policy = jsonencode({

    Version = "2012-10-17"
    Statement = [{

      Effect = "Deny", Principal = "*", Action = "s3:*"
      Resource = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
      Condition = {
        Bool = {
          "aws:SecureTransport" = "false"
        }
      }

    }]

  })

}

resource "aws_iam_openid_connect_provider" "github" {

  count = var.create_github_oidc ? 1 : 0
  url = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

}

data "aws_iam_policy_document" "github_trust" {

  for_each = {
    infra = "main", deploy = "main"
  }
  statement {

    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type = "Federated"
      identifiers = [local.oidc_arn]
    }
    condition {

      test = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values = ["sts.amazonaws.com"]

    }
    condition {

      test = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = ["repo:${var.github_owner}@${var.github_owner_id}/${var.repository}@${var.github_repository_id}:ref:refs/heads/${each.value}"]

    }

  }

}
resource "aws_iam_role" "ci" {

  for_each = data.aws_iam_policy_document.github_trust
  name = "eks-persona-ci-${each.key}"
  assume_role_policy = each.value.json
  max_session_duration = 7200
  depends_on = [aws_iam_openid_connect_provider.github]

}

# Intentionally a LAB infrastructure policy. EC2 network operations are region-wide.
# CI cannot edit its own IAM roles or the OIDC provider. Review before shared-account use.
resource "aws_iam_role_policy" "infra" {

  role = aws_iam_role.ci["infra"].id
  name = "eks-persona-lab-infrastructure"
  policy = jsonencode({

    Version = "2012-10-17"
    Statement = [
    {

      Sid = "StateBucketList", Effect = "Allow", Action = ["s3:ListBucket", "s3:GetBucketLocation"],
      Resource = aws_s3_bucket.state.arn

    },
    {

      Sid = "InfraStateOnly", Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      Resource = "${aws_s3_bucket.state.arn}/infra/*"

    },
    {

      Sid = "NetworkLabRegion", Effect = "Allow",
      Action = [
      "ec2:Describe*", "ec2:CreateVpc", "ec2:DeleteVpc", "ec2:ModifyVpcAttribute",
      "ec2:CreateSubnet", "ec2:DeleteSubnet", "ec2:ModifySubnetAttribute",
      "ec2:CreateInternetGateway", "ec2:AttachInternetGateway", "ec2:DetachInternetGateway", "ec2:DeleteInternetGateway",
      "ec2:CreateRouteTable", "ec2:DeleteRouteTable", "ec2:CreateRoute", "ec2:DeleteRoute", "ec2:ReplaceRoute",
      "ec2:AssociateRouteTable", "ec2:DisassociateRouteTable", "ec2:ReplaceRouteTableAssociation",
      "ec2:AllocateAddress", "ec2:ReleaseAddress", "ec2:CreateNatGateway", "ec2:DeleteNatGateway",
      "ec2:CreateTags", "ec2:DeleteTags"
      ], Resource = "*", Condition = {
        StringEquals = {
          "aws:RequestedRegion" = var.region
        }
      }

    },
    {

      Sid = "ProjectEks", Effect = "Allow", Action = ["eks:*"],
      Resource = [
      "arn:aws:eks:${var.region}:${local.account}:cluster/${local.cluster}",
      "arn:aws:eks:${var.region}:${local.account}:*/${local.cluster}/*"
      ]

    },
    {

      Sid = "EksReadCatalogue", Effect = "Allow",
      Action = ["eks:ListClusters", "eks:DescribeAddonVersions", "eks:DescribeAddonConfiguration", "eks:DescribeClusterVersions"], Resource = "*"

    },
    {

      Sid = "WorkloadRolesOnly", Effect = "Allow",
      Action = [
      "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:UpdateAssumeRolePolicy",
      "iam:TagRole", "iam:UntagRole", "iam:ListRolePolicies", "iam:GetRolePolicy", "iam:PutRolePolicy", "iam:DeleteRolePolicy",
      "iam:ListAttachedRolePolicies", "iam:AttachRolePolicy", "iam:DetachRolePolicy"
      ], Resource = "arn:aws:iam::${local.account}:role/eks-persona-workload-*"

    },
    {

      Sid = "PassWorkloadRoles", Effect = "Allow", Action = "iam:PassRole",
      Resource = "arn:aws:iam::${local.account}:role/eks-persona-workload-*",
      Condition = {
        StringEquals = {
          "iam:PassedToService" = ["eks.amazonaws.com", "ec2.amazonaws.com", "pods.eks.amazonaws.com"]
        }
      }

    },
    {

      Sid = "EksServiceLinkedRole", Effect = "Allow", Action = "iam:CreateServiceLinkedRole", Resource = "*",
      Condition = {
        StringEquals = {
          "iam:AWSServiceName" = ["eks.amazonaws.com", "eks-nodegroup.amazonaws.com", "autoscaling.amazonaws.com"]
        }
      }

    },
    {

      Sid = "ReadAwsPolicies", Effect = "Allow", Action = ["iam:GetPolicy", "iam:GetPolicyVersion"], Resource = "arn:aws:iam::aws:policy/*"

    },
    {

      Sid = "ReadCiRoles", Effect = "Allow", Action = ["iam:GetRole"],
      Resource = [aws_iam_role.ci["infra"].arn, aws_iam_role.ci["deploy"].arn]

    },
    {

      Sid = "ProjectLogs", Effect = "Allow", Action = ["logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy", "logs:DeleteRetentionPolicy", "logs:TagResource", "logs:UntagResource", "logs:ListTagsForResource"],
      Resource = "arn:aws:logs:${var.region}:${local.account}:log-group:/aws/eks/${local.cluster}/cluster*"

    },
    {
      Sid = "LogGroupRead", Effect = "Allow", Action = ["logs:DescribeLogGroups"], Resource = "*"
    },
    {
      Sid = "EcrLogin", Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*"
    },
    {

      Sid = "ProjectEcrBuild", Effect = "Allow",
      Action = [
      "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage",
      "ecr:DescribeImages", "ecr:DescribeImageScanFindings", "ecr:StartImageScan", "ecr:ListImages", "ecr:DescribeRepositories"
      ], Resource = "arn:aws:ecr:${var.region}:${local.account}:repository/eks-persona/*"

    }
    ]

  })

}

resource "aws_iam_role_policy" "deploy" {
  role = aws_iam_role.ci["deploy"].id
  name = "persona-deployment-and-backup"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "eks:DescribeCluster"
        Resource = "arn:aws:eks:${var.region}:${local.account}:cluster/${local.cluster}"
      },
      {
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject"]
        Resource = "${aws_s3_bucket.state.arn}/backups/*"
      }
    ]
  })
}

resource "aws_ecr_repository" "app" {

  for_each = toset(["frontend", "registration", "persona", "media"])
  name = "eks-persona/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  force_delete = false
  image_scanning_configuration {
    scan_on_push = true
  }
  lifecycle {
    prevent_destroy = true
  }

}

output "state_bucket" {
  value = aws_s3_bucket.state.id
}
output "infra_role_arn" {
  value = try(aws_iam_role.ci["infra"].arn, null)
}
output "deploy_role_arn" {
  value = try(aws_iam_role.ci["deploy"].arn, null)
}
output "ecr_registry" {
  value = "${local.account}.dkr.ecr.${var.region}.amazonaws.com"
}
