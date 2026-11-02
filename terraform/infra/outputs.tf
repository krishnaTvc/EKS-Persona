output "cluster_name" {
  value = aws_eks_cluster.main.name
}
output "region" {
  value = var.region
}
output "vpc_id" {
  value = aws_vpc.main.id
}
output "private_subnets" {
  value = aws_subnet.private[*].id
}
output "ecr_registry" {
  value = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.region}.amazonaws.com"
}
