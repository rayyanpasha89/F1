output "url" {
  value = "https://${aws_cloudfront_distribution.app.domain_name}"
}

output "distribution_id" {
  value = aws_cloudfront_distribution.app.id
}

output "frontend_bucket" {
  value = aws_s3_bucket.project["frontend"].id
}

output "artifact_bucket" {
  value = aws_s3_bucket.project["artifacts"].id
}

output "ecr_url" {
  value = aws_ecr_repository.api.repository_url
}

output "runtime_secret_arn" {
  value = aws_secretsmanager_secret.runtime.arn
}

output "bootstrap_task" {
  value = aws_ecs_task_definition.bootstrap.arn
}

output "cluster" {
  value = aws_ecs_cluster.project.name
}

output "service" {
  value = aws_ecs_service.api.name
}

output "task_subnets" {
  value = aws_subnet.public[*].id
}

output "task_security_group" {
  value = aws_security_group.task.id
}

output "build_project" {
  value = aws_codebuild_project.api.name
}

