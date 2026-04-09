variable "aws_region" {
  description = "Target AWS region for the single MVP environment."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project slug used in names, tags, and parameter paths."
  type        = string
  default     = "supportdoc-rag-chatbot"
}

variable "environment" {
  description = "Single deployed environment name for the MVP."
  type        = string
  default     = "mvp"
}

variable "root_domain_name" {
  description = "Existing public Route 53 hosted-zone root used for the backend API record."
  type        = string
}

variable "backend_api_subdomain" {
  description = "Subdomain label prefix used to derive the public backend API FQDN."
  type        = string
  default     = "api.supportdoc-mvp"
}

variable "vpc_cidr" {
  description = "CIDR block for the shared MVP VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "Two public subnets for the internet-facing ALB."
  type        = list(string)
  default     = ["10.42.0.0/24", "10.42.1.0/24"]

  validation {
    condition     = length(var.public_subnet_cidrs) == 2
    error_message = "Exactly two public subnet CIDRs are required."
  }
}

variable "app_private_subnet_cidrs" {
  description = "Two private app subnets for ECS tasks and the private inference host."
  type        = list(string)
  default     = ["10.42.10.0/24", "10.42.11.0/24"]

  validation {
    condition     = length(var.app_private_subnet_cidrs) == 2
    error_message = "Exactly two app private subnet CIDRs are required."
  }
}

variable "data_private_subnet_cidrs" {
  description = "Two private data subnets for RDS."
  type        = list(string)
  default     = ["10.42.20.0/24", "10.42.21.0/24"]

  validation {
    condition     = length(var.data_private_subnet_cidrs) == 2
    error_message = "Exactly two data private subnet CIDRs are required."
  }
}

variable "backend_container_port" {
  description = "Backend container port exposed to the ALB target group."
  type        = number
  default     = 9001
}

variable "inference_port" {
  description = "Private OpenAI-compatible inference port that ECS will call."
  type        = number
  default     = 8000
}

variable "log_retention_days" {
  description = "CloudWatch log retention used for backend and inference groups."
  type        = number
  default     = 14
}

variable "inference_model_id" {
  description = "Default non-secret model identifier recorded in Parameter Store for the backend runtime."
  type        = string
  default     = "mistralai/Mistral-7B-Instruct-v0.3"
}

variable "pgvector_schema_name" {
  description = "Canonical pgvector schema name aligned to the repo defaults."
  type        = string
  default     = "supportdoc_rag"
}

variable "pgvector_runtime_id" {
  description = "Canonical pgvector runtime identifier aligned to the repo defaults."
  type        = string
  default     = "default"
}

variable "pgvector_embedder_mode" {
  description = "Query embedder mode used by the AWS pgvector runtime."
  type        = string
  default     = "local"

  validation {
    condition     = contains(["local", "fixture"], var.pgvector_embedder_mode)
    error_message = "pgvector_embedder_mode must be either local or fixture."
  }
}

variable "s3_force_destroy" {
  description = "Allow Terraform to delete the artifacts bucket even if it contains objects."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Additional tags merged into all resources."
  type        = map(string)
  default     = {}
}
