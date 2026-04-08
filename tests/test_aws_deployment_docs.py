from __future__ import annotations

from pathlib import Path

AWS_NOTE = Path("docs/architecture/aws_deployment.md")
OPS_NOTE = Path("docs/ops/cost_and_ops.md")
FRONTEND_README = Path("frontend/README.md")
ROOT_README = Path("README.md")


def test_aws_deployment_docs_distinguish_deploy_now_shell_from_implemented_cloud_runtime() -> None:
    content = AWS_NOTE.read_text(encoding="utf-8")

    assert "deploy-now backend shell on AWS" in content
    assert "First browser-backed AWS slice" in content
    assert "SUPPORTDOC_DEPLOYMENT_TARGET" in content
    assert "SUPPORTDOC_API_CORS_ALLOWED_ORIGINS" in content
    assert "artifact` remains local-only in the current repo" in content
    assert "promote-pgvector-runtime" in content
    assert "openai_compatible" in content
    assert "Cloud-backed runtime path now implemented" in content
    assert "artifact-mode container support for mounting local FAISS artifacts" in content
    assert "the ALB target-group health path should stay on `/healthz`, not on `/readyz`" in content


def test_frontend_and_ops_docs_pin_browser_config_and_health_boundaries() -> None:
    frontend_content = FRONTEND_README.read_text(encoding="utf-8")
    ops_content = OPS_NOTE.read_text(encoding="utf-8")
    readme_content = ROOT_README.read_text(encoding="utf-8")

    assert "AWS Amplify Hosting" in frontend_content
    assert "VITE_SUPPORTDOC_API_BASE_URL" in frontend_content
    assert "SUPPORTDOC_API_CORS_ALLOWED_ORIGINS" in frontend_content
    assert "SUPPORTDOC_DEPLOYMENT_TARGET=aws" in ops_content
    assert "`/healthz` should stay the ALB target-group health path" in ops_content
    assert "`/readyz` stays the operator-facing compatibility check" in ops_content
    assert "VITE_SUPPORTDOC_API_BASE_URL" in readme_content
    assert "pgvector` retrieval" in readme_content
    assert "OpenAI-compatible inference adapter" in readme_content
    assert "./scripts/smoke-cloud-runtime.sh" in readme_content
