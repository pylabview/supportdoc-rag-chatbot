output "aws_region" {
  description = "Selected AWS region for the MVP foundation."
  value       = var.aws_region
}

output "environment" {
  description = "Single deployed environment name."
  value       = var.environment
}

output "name_prefix" {
  description = "Shared resource naming prefix."
  value       = local.name_prefix
}

output "backend_api_domain" {
  description = "Public HTTPS backend domain fronting the ALB."
  value       = local.backend_api_domain
}

output "backend_base_url" {
  description = "Public HTTPS backend base URL."
  value       = "https://${local.backend_api_domain}"
}

output "public_route53_zone_id" {
  description = "Public Route 53 hosted zone ID used for ACM validation and ALB alias records."
  value       = local.public_route53_zone_id
}

output "vpc_id" {
  description = "Shared MVP VPC identifier."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs for the ALB."
  value       = values(aws_subnet.public)[*].id
}

output "app_private_subnet_ids" {
  description = "Private app subnet IDs for ECS tasks and the inference host."
  value       = values(aws_subnet.app_private)[*].id
}

output "data_private_subnet_ids" {
  description = "Private data subnet IDs for RDS."
  value       = values(aws_subnet.data_private)[*].id
}

output "route_table_ids" {
  description = "Route tables used by the public, app-private, and data-private subnet tiers."
  value = {
    public       = aws_route_table.public.id
    app_private  = aws_route_table.app_private.id
    data_private = aws_route_table.data_private.id
  }
}

output "security_group_ids" {
  description = "Security groups that enforce ALB -> ECS -> RDS/inference traffic."
  value = {
    alb       = aws_security_group.alb.id
    ecs       = aws_security_group.ecs.id
    rds       = aws_security_group.rds.id
    inference = aws_security_group.inference.id
  }
}

output "ecr_repository_name" {
  description = "Private ECR repository name for the backend image."
  value       = aws_ecr_repository.backend.name
}

output "ecr_repository_url" {
  description = "Private ECR repository URL for pushes."
  value       = aws_ecr_repository.backend.repository_url
}

output "artifact_bucket_name" {
  description = "Artifacts bucket name."
  value       = aws_s3_bucket.artifacts.bucket
}

output "artifact_prefixes" {
  description = "Seeded S3 prefixes for corpus, processed data, deployment files, and evaluation outputs."
  value       = sort([for object in aws_s3_object.artifact_prefixes : object.key])
}

output "cloudwatch_log_group_names" {
  description = "CloudWatch log groups reserved for the backend and inference runtimes."
  value = {
    backend   = aws_cloudwatch_log_group.backend.name
    inference = aws_cloudwatch_log_group.inference.name
  }
}

output "ssm_parameter_prefix" {
  description = "SSM Parameter Store path prefix for non-secret backend runtime configuration."
  value       = local.ssm_parameter_prefix
}

output "ssm_parameter_names" {
  description = "Seeded backend non-secret parameters aligned to the repo runtime contract."
  value       = { for key, parameter in aws_ssm_parameter.backend_non_secret : key => parameter.name }
}

output "secret_names" {
  description = "Secrets Manager names reserved for backend and database secrets."
  value = {
    database_master_credentials      = aws_secretsmanager_secret.rds_master_credentials.name
    backend_query_pgvector_dsn       = aws_secretsmanager_secret.backend_query_pgvector_dsn.name
    backend_query_generation_api_key = aws_secretsmanager_secret.backend_query_generation_api_key.name
  }
}

output "alb_arn" {
  description = "Application Load Balancer ARN."
  value       = aws_lb.public.arn
}

output "alb_dns_name" {
  description = "Public ALB DNS name."
  value       = aws_lb.public.dns_name
}

output "https_listener_arn" {
  description = "HTTPS listener ARN that fronts the backend target group."
  value       = aws_lb_listener.https.arn
}

output "backend_target_group_arn" {
  description = "Backend target group ARN reserved for the ECS service in Task 4."
  value       = aws_lb_target_group.backend.arn
}
