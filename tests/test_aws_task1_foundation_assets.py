from __future__ import annotations

from pathlib import Path

ROOT_README = Path("README.md")
TASK1_DOC = Path("docs/ops/aws_task1_foundation.md")
TASK1_README = Path("infra/aws/task1-foundation/README.md")
TASK1_MAIN_TF = Path("infra/aws/task1-foundation/main.tf")
TASK1_VARIABLES_TF = Path("infra/aws/task1-foundation/variables.tf")
TASK1_OUTPUTS_TF = Path("infra/aws/task1-foundation/outputs.tf")
TASK1_TFVARS = Path("infra/aws/task1-foundation/terraform.tfvars.example")
TASK1_VERIFY = Path("scripts/verify-aws-task1.sh")


def test_task1_foundation_assets_exist() -> None:
    for path in [
        TASK1_DOC,
        TASK1_README,
        TASK1_MAIN_TF,
        TASK1_VARIABLES_TF,
        TASK1_OUTPUTS_TF,
        TASK1_TFVARS,
        TASK1_VERIFY,
    ]:
        assert path.exists(), f"Missing Task 1 foundation asset: {path}"


def test_task1_docs_pin_repo_runtime_contract() -> None:
    content = TASK1_DOC.read_text(encoding="utf-8")

    assert "SUPPORTDOC_DEPLOYMENT_TARGET" in content
    assert "SUPPORTDOC_QUERY_RETRIEVAL_MODE" in content
    assert "SUPPORTDOC_QUERY_GENERATION_MODE" in content
    assert "SUPPORTDOC_QUERY_PGVECTOR_DSN" in content
    assert "SUPPORTDOC_QUERY_GENERATION_API_KEY" in content
    assert "VITE_SUPPORTDOC_API_BASE_URL" in content
    assert "supportdoc-rag-chatbot/mvp/backend" in content
    assert "/supportdoc-rag-chatbot/mvp" in content


def test_task1_terraform_covers_https_foundation_requirements() -> None:
    content = TASK1_MAIN_TF.read_text(encoding="utf-8")

    assert 'resource "aws_lb" "public"' in content
    assert 'resource "aws_acm_certificate" "backend"' in content
    assert 'resource "aws_route53_record" "backend_alias_a"' in content
    assert 'resource "aws_ecr_repository" "backend"' in content
    assert 'resource "aws_s3_bucket" "artifacts"' in content
    assert 'resource "aws_cloudwatch_log_group" "backend"' in content
    assert 'resource "aws_secretsmanager_secret" "backend_query_pgvector_dsn"' in content
    assert 'resource "aws_ssm_parameter" "backend_non_secret"' in content
    assert "SUPPORTDOC_QUERY_GENERATION_MODEL" in content
    assert "/healthz" in content


def test_root_readme_references_task1_foundation_assets() -> None:
    content = ROOT_README.read_text(encoding="utf-8")

    assert "infra/aws/task1-foundation/" in content
    assert "docs/ops/aws_task1_foundation.md" in content
