terraform {

  required_version = ">= 1.10, < 2.0"
  backend "s3" {

  }
  required_providers {

    aws = {
      source = "hashicorp/aws", version = "~> 6.0"
    }
    http = {
      source = "hashicorp/http"
      version = "~> 3.0"
    }

  }

}
provider "aws" {

  region = var.region
  default_tags {
    tags = {
      Project = "eks-persona", Environment = "dev", ManagedBy = "Terraform"
    }
  }

}
data "aws_caller_identity" "current" {

}
data "aws_availability_zones" "available" {
  state = "available"
}
