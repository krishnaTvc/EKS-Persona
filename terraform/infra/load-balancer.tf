# Release pinned to the version documented in the AWS install guide.
# The upstream policy is fetched at plan time; it contains no account credentials.
data "http" "load_balancer_policy" {
  url = "https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.14.1/docs/install/iam_policy.json"
}
resource "aws_iam_role" "load_balancer" {
  name = "eks-persona-workload-load-balancer"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["sts:AssumeRole", "sts:TagSession"], Principal = { Service = "pods.eks.amazonaws.com" } }]
  })
}
resource "aws_iam_role_policy" "load_balancer" {
  role = aws_iam_role.load_balancer.id
  name = "aws-load-balancer-controller-v2-14-1"
  policy = data.http.load_balancer_policy.response_body
}
resource "aws_eks_pod_identity_association" "load_balancer" {
  cluster_name = aws_eks_cluster.main.name
  namespace = "kube-system"
  service_account = "aws-load-balancer-controller"
  role_arn = aws_iam_role.load_balancer.arn
  depends_on = [aws_eks_addon.base, aws_iam_role_policy.load_balancer]
}
