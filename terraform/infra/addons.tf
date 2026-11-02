resource "aws_iam_role" "ebs" {

  name = "eks-persona-workload-ebs"
  assume_role_policy = jsonencode({

    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Action = ["sts:AssumeRole", "sts:TagSession"], Principal = {
        Service = "pods.eks.amazonaws.com"
      }
    }]

  })

}
resource "aws_iam_role_policy_attachment" "ebs" {

  role = aws_iam_role.ebs.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEBSCSIDriverPolicyV2"

}
resource "aws_eks_addon" "base" {

  for_each = toset(["vpc-cni", "kube-proxy", "coredns", "eks-pod-identity-agent"])
  cluster_name = aws_eks_cluster.main.name
  addon_name = each.value
  addon_version = var.addon_versions[each.value]
  configuration_values = each.value == "vpc-cni" ? jsonencode({
    enableNetworkPolicy = "true"
  }) : null
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
  depends_on = [aws_eks_node_group.main]

}
resource "aws_eks_addon" "ebs" {

  cluster_name = aws_eks_cluster.main.name
  addon_name = "aws-ebs-csi-driver"
  addon_version = var.addon_versions["aws-ebs-csi-driver"]
  pod_identity_association {

    role_arn = aws_iam_role.ebs.arn
    service_account = "ebs-csi-controller-sa"

  }
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
  depends_on = [aws_eks_addon.base, aws_iam_role_policy_attachment.ebs]

}
