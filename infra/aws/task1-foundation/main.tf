provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  root_domain_name             = trimsuffix(var.root_domain_name, ".")
  route53_zone_id              = try(trimspace(var.route53_zone_id), "")
  use_explicit_route53_zone_id = local.route53_zone_id != ""
  backend_api_domain           = "${var.backend_api_subdomain}.${local.root_domain_name}"
  name_prefix                  = "${var.project}-${var.environment}"
  ecr_repository_name          = "${var.project}/${var.environment}/backend"
  s3_bucket_name               = lower("${var.project}-${var.environment}-${data.aws_caller_identity.current.account_id}-${var.aws_region}-artifacts")
  ssm_parameter_prefix         = "/${var.project}/${var.environment}"
  secrets_prefix               = "${var.project}/${var.environment}"
  backend_log_group_name       = "/aws/${var.project}/${var.environment}/backend"
  inference_log_group_name     = "/aws/${var.project}/${var.environment}/inference"

  public_subnet_map = {
    for index, cidr in var.public_subnet_cidrs :
    "public-${index + 1}" => {
      cidr = cidr
      az   = data.aws_availability_zones.available.names[index]
    }
  }

  app_private_subnet_map = {
    for index, cidr in var.app_private_subnet_cidrs :
    "app-private-${index + 1}" => {
      cidr = cidr
      az   = data.aws_availability_zones.available.names[index]
    }
  }

  data_private_subnet_map = {
    for index, cidr in var.data_private_subnet_cidrs :
    "data-private-${index + 1}" => {
      cidr = cidr
      az   = data.aws_availability_zones.available.names[index]
    }
  }

  parameter_seed_values = {
    SUPPORTDOC_DEPLOYMENT_TARGET            = "aws"
    SUPPORTDOC_ENV                          = var.environment
    SUPPORTDOC_QUERY_RETRIEVAL_MODE         = "pgvector"
    SUPPORTDOC_QUERY_PGVECTOR_SCHEMA_NAME   = var.pgvector_schema_name
    SUPPORTDOC_QUERY_PGVECTOR_RUNTIME_ID    = var.pgvector_runtime_id
    SUPPORTDOC_QUERY_PGVECTOR_EMBEDDER_MODE = var.pgvector_embedder_mode
    SUPPORTDOC_QUERY_GENERATION_MODE        = "openai_compatible"
    SUPPORTDOC_QUERY_GENERATION_MODEL       = var.inference_model_id
  }

  common_tags = merge(
    {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
      Epic        = "EPIC-12"
      Task        = "task1-foundation"
    },
    var.tags,
  )
}

data "aws_route53_zone" "public_by_name" {
  count        = local.use_explicit_route53_zone_id ? 0 : 1
  name         = "${local.root_domain_name}."
  private_zone = false
}

locals {
  public_route53_zone_id = local.use_explicit_route53_zone_id ? local.route53_zone_id : data.aws_route53_zone.public_by_name[0].zone_id
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-vpc"
  })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-igw"
  })
}

resource "aws_subnet" "public" {
  for_each = local.public_subnet_map

  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value.cidr
  availability_zone       = each.value.az
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, {
    Name        = "${local.name_prefix}-${each.key}"
    NetworkTier = "public"
  })
}

resource "aws_subnet" "app_private" {
  for_each = local.app_private_subnet_map

  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value.cidr
  availability_zone       = each.value.az
  map_public_ip_on_launch = false

  tags = merge(local.common_tags, {
    Name        = "${local.name_prefix}-${each.key}"
    NetworkTier = "private-app"
  })
}

resource "aws_subnet" "data_private" {
  for_each = local.data_private_subnet_map

  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value.cidr
  availability_zone       = each.value.az
  map_public_ip_on_launch = false

  tags = merge(local.common_tags, {
    Name        = "${local.name_prefix}-${each.key}"
    NetworkTier = "private-data"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-public-rt"
  })
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-nat-eip"
  })
}

resource "aws_nat_gateway" "this" {
  allocation_id = aws_eip.nat.id
  subnet_id     = values(aws_subnet.public)[0].id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-nat"
  })

  depends_on = [aws_internet_gateway.this]
}

resource "aws_route_table" "app_private" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-app-private-rt"
  })
}

resource "aws_route" "app_private_default" {
  route_table_id         = aws_route_table.app_private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this.id
}

resource "aws_route_table_association" "app_private" {
  for_each = aws_subnet.app_private

  subnet_id      = each.value.id
  route_table_id = aws_route_table.app_private.id
}

resource "aws_route_table" "data_private" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-data-private-rt"
  })
}

resource "aws_route_table_association" "data_private" {
  for_each = aws_subnet.data_private

  subnet_id      = each.value.id
  route_table_id = aws_route_table.data_private.id
}

resource "aws_security_group" "alb" {
  name        = "${local.name_prefix}-alb-sg"
  description = "Public ingress for the SupportDoc MVP Application Load Balancer."
  vpc_id      = aws_vpc.this.id

  ingress {
    description      = "Public HTTP redirect entrypoint"
    from_port        = 80
    to_port          = 80
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  ingress {
    description      = "Public HTTPS entrypoint"
    from_port        = 443
    to_port          = 443
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    description      = "Outbound to backend targets and health checks"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-alb-sg"
  })
}

resource "aws_security_group" "ecs" {
  name        = "${local.name_prefix}-ecs-sg"
  description = "Backend ECS tasks only accept traffic from the ALB."
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "Backend traffic from the public ALB"
    from_port       = var.backend_container_port
    to_port         = var.backend_container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description      = "Allow outbound calls to RDS, inference, ECR, S3, and model downloads"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ecs-sg"
  })
}

resource "aws_security_group" "rds" {
  name        = "${local.name_prefix}-rds-sg"
  description = "Private PostgreSQL ingress only from ECS."
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "PostgreSQL from ECS tasks only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    description      = "Default egress for managed database operations"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-rds-sg"
  })
}

resource "aws_security_group" "inference" {
  name        = "${local.name_prefix}-inference-sg"
  description = "Private OpenAI-compatible inference ingress only from ECS."
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "Inference traffic from ECS tasks only"
    from_port       = var.inference_port
    to_port         = var.inference_port
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    description      = "Outbound for package, model, and patch downloads"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-inference-sg"
  })
}

resource "aws_ecr_repository" "backend" {
  name                 = local.ecr_repository_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-backend-ecr"
  })
}

resource "aws_s3_bucket" "artifacts" {
  bucket        = local.s3_bucket_name
  force_destroy = var.s3_force_destroy

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-artifacts"
  })
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "artifact_prefixes" {
  for_each = toset([
    "corpus/",
    "processed/",
    "evaluation/outputs/",
    "deployment/",
  ])

  bucket  = aws_s3_bucket.artifacts.id
  key     = each.value
  content = ""
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = local.backend_log_group_name
  retention_in_days = var.log_retention_days

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-backend-log-group"
  })
}

resource "aws_cloudwatch_log_group" "inference" {
  name              = local.inference_log_group_name
  retention_in_days = var.log_retention_days

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-inference-log-group"
  })
}

resource "aws_ssm_parameter" "backend_non_secret" {
  for_each = local.parameter_seed_values

  name  = "${local.ssm_parameter_prefix}/backend/${each.key}"
  type  = "String"
  value = each.value

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-${lower(replace(each.key, "_", "-"))}-parameter"
  })
}

resource "aws_secretsmanager_secret" "rds_master_credentials" {
  name        = "${local.secrets_prefix}/database/master-credentials"
  description = "Placeholder secret for the RDS PostgreSQL master credentials created in Task 2."

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-database-master-secret"
  })
}

resource "aws_secretsmanager_secret" "backend_query_pgvector_dsn" {
  name        = "${local.secrets_prefix}/backend/query-pgvector-dsn"
  description = "Placeholder secret for SUPPORTDOC_QUERY_PGVECTOR_DSN."

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-backend-pgvector-dsn-secret"
  })
}

resource "aws_secretsmanager_secret" "backend_query_generation_api_key" {
  name        = "${local.secrets_prefix}/backend/query-generation-api-key"
  description = "Placeholder secret for SUPPORTDOC_QUERY_GENERATION_API_KEY when the inference endpoint requires authentication."

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-backend-generation-api-key-secret"
  })
}

resource "aws_lb" "public" {
  name               = substr(replace("${local.name_prefix}-alb", "-", ""), 0, 32)
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = values(aws_subnet.public)[*].id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-alb"
  })
}

resource "aws_lb_target_group" "backend" {
  name        = substr(replace("${local.name_prefix}-api", "-", ""), 0, 32)
  port        = var.backend_container_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.this.id

  health_check {
    enabled             = true
    path                = "/healthz"
    healthy_threshold   = 2
    unhealthy_threshold = 2
    interval            = 30
    timeout             = 5
    matcher             = "200-399"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-backend-tg"
  })
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.public.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_acm_certificate" "backend" {
  domain_name       = local.backend_api_domain
  validation_method = "DNS"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-backend-acm"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "backend_validation" {
  for_each = {
    for option in aws_acm_certificate.backend.domain_validation_options :
    option.domain_name => {
      name   = option.resource_record_name
      type   = option.resource_record_type
      record = option.resource_record_value
    }
  }

  allow_overwrite = true
  zone_id         = local.public_route53_zone_id
  name            = each.value.name
  type            = each.value.type
  ttl             = 60
  records         = [each.value.record]
}

resource "aws_acm_certificate_validation" "backend" {
  certificate_arn         = aws_acm_certificate.backend.arn
  validation_record_fqdns = values(aws_route53_record.backend_validation)[*].fqdn
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.public.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-Res-2021-06"
  certificate_arn   = aws_acm_certificate_validation.backend.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

resource "aws_route53_record" "backend_alias_a" {
  zone_id = local.public_route53_zone_id
  name    = local.backend_api_domain
  type    = "A"

  alias {
    name                   = aws_lb.public.dns_name
    zone_id                = aws_lb.public.zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "backend_alias_aaaa" {
  zone_id = local.public_route53_zone_id
  name    = local.backend_api_domain
  type    = "AAAA"

  alias {
    name                   = aws_lb.public.dns_name
    zone_id                = aws_lb.public.zone_id
    evaluate_target_health = true
  }
}
