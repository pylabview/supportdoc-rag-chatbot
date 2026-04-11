from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(".github/workflows/terraform-task1-foundation.yml")
OPS_DOC = Path("docs/ops/aws_task1_foundation.md")
INFRA_README = Path("infra/aws/task1-foundation/README.md")
TFVARS_EXAMPLE = Path("infra/aws/task1-foundation/terraform.tfvars.example")


def test_task1_1_workflow_uses_oidc_and_remote_state_backend_config() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "id-token: write" in content
    assert "issues: write" in content
    assert "pull-requests: write" in content
    assert "aws-actions/configure-aws-credentials@v6.1.0" in content
    assert "role-to-assume: ${{ vars.AWS_ROLE_ARN }}" in content
    assert '-backend-config="bucket=${{ vars.TF_BACKEND_BUCKET }}"' in content
    assert '-backend-config="key=${{ vars.TF_BACKEND_KEY }}"' in content
    assert "repo.full_name == github.repository" in content
    assert "workflow_dispatch" in content
    assert "github.event_name == 'pull_request'" in content


def test_task1_1_docs_pin_remote_state_and_api_hostname() -> None:
    ops_content = OPS_DOC.read_text(encoding="utf-8")
    infra_content = INFRA_README.read_text(encoding="utf-8")
    tfvars_content = TFVARS_EXAMPLE.read_text(encoding="utf-8")

    assert "api.<root_domain_name>" in ops_content
    assert "api.supportdochq.com" in ops_content
    assert "route53_zone_id" in ops_content
    assert "use_lockfile = true" in ops_content
    assert "terraform-task1-foundation.yml" in ops_content
    assert "bootstrap/oidc-trust-pr-and-main.json" in infra_content
    assert "terraform init" in infra_content
    assert 'aws_region            = "us-west-2"' in tfvars_content
    assert 'backend_api_subdomain = "api"' in tfvars_content
    assert "route53_zone_id = null" in tfvars_content
