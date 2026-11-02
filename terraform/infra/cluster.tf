resource "aws_iam_role" "cluster" {

  name = "eks-persona-workload-cluster"
  assume_role_policy = jsonencode({
    Version = "2012-10-17", Statement = [{
      Effect = "Allow", Action = "sts:AssumeRole", Principal = {
        Service = "eks.amazonaws.com"
      }
    }]
  })

}
resource "aws_iam_role_policy_attachment" "cluster" {

  role = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"

}
resource "aws_cloudwatch_log_group" "eks" {

  name = "/aws/eks/${var.cluster_name}/cluster"
  retention_in_days = 7

}
resource "aws_eks_cluster" "main" {

  name = var.cluster_name
  version = var.cluster_version
  role_arn = aws_iam_role.cluster.arn
  enabled_cluster_log_types = ["api", "audit", "authenticator"]
  vpc_config {

    subnet_ids = aws_subnet.private[*].id
    endpoint_private_access = true
    endpoint_public_access = true
    public_access_cidrs = var.api_allowed_cidrs

  }
  access_config {

    authentication_mode = "API"
    bootstrap_cluster_creator_admin_permissions = false

  }
  upgrade_policy {
    support_type = "STANDARD"
  }
  depends_on = [aws_iam_role_policy_attachment.cluster, aws_cloudwatch_log_group.eks]

}

resource "aws_iam_role" "nodes" {

  name = "eks-persona-workload-nodes"
  assume_role_policy = jsonencode({
    Version = "2012-10-17", Statement = [{
      Effect = "Allow", Action = "sts:AssumeRole", Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })

}
resource "aws_iam_role_policy_attachment" "nodes" {

  for_each = toset(["AmazonEKSWorkerNodePolicy", "AmazonEC2ContainerRegistryPullOnly", "AmazonEKS_CNI_Policy"])
  role = aws_iam_role.nodes.name
  policy_arn = "arn:aws:iam::aws:policy/${each.value}"

}
resource "aws_eks_node_group" "main" {

  cluster_name = aws_eks_cluster.main.name
  node_group_name = "persona-workers"
  node_role_arn = aws_iam_role.nodes.arn
  subnet_ids = aws_subnet.private[*].id
  instance_types = ["t3.medium"]
  ami_type = "AL2023_x86_64_STANDARD"
  capacity_type = "ON_DEMAND"
  disk_size = 20
  scaling_config {
    desired_size = 2
    min_size = 2
    max_size = 3
  }
  update_config {
    max_unavailable = 1
  }
  depends_on = [aws_iam_role_policy_attachment.nodes, aws_route_table_association.private]

}

resource "aws_eks_access_entry" "infra" {

  cluster_name = aws_eks_cluster.main.name
  principal_arn = var.infra_role_arn
  type = "STANDARD"

}
resource "aws_eks_access_policy_association" "infra" {

  cluster_name = aws_eks_cluster.main.name
  principal_arn = aws_eks_access_entry.infra.principal_arn
  policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope {
    type = "cluster"
  }

}
resource "aws_eks_access_entry" "operator" {

  cluster_name = aws_eks_cluster.main.name
  principal_arn = var.operator_principal_arn
  type = "STANDARD"

}
resource "aws_eks_access_policy_association" "operator" {

  cluster_name = aws_eks_cluster.main.name
  principal_arn = aws_eks_access_entry.operator.principal_arn
  policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope {
    type = "cluster"
  }

}
resource "aws_eks_access_entry" "deploy" {

  cluster_name = aws_eks_cluster.main.name
  principal_arn = var.deploy_role_arn
  type = "STANDARD"

}
resource "aws_eks_access_policy_association" "deploy" {

  cluster_name = aws_eks_cluster.main.name
  principal_arn = aws_eks_access_entry.deploy.principal_arn
  policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"
  access_scope {
    type = "namespace"
    namespaces = ["persona"]
  }

}
