from __future__ import annotations

import json
from pathlib import Path

FRONTEND_DIR = Path("frontend")


def test_frontend_scaffold_uses_react_and_vite() -> None:
    package_json = FRONTEND_DIR / "package.json"
    assert package_json.is_file()

    package = json.loads(package_json.read_text(encoding="utf-8"))

    assert package["name"] == "supportdoc-browser-demo"
    assert package["private"] is True
    assert package["scripts"]["dev"] == "vite"
    assert package["scripts"]["build"] == "vite build"
    assert package["scripts"]["preview"] == "vite preview"
    assert "react" in package["dependencies"]
    assert "react-dom" in package["dependencies"]
    assert "vite" in package["devDependencies"]
    assert "@vitejs/plugin-react" in package["devDependencies"]
    assert package["engines"]["node"] == "^20.19.0 || >=22.12.0"


def test_frontend_npmrc_and_lockfile_avoid_environment_specific_registry_pinning() -> None:
    npmrc = (FRONTEND_DIR / ".npmrc").read_text(encoding="utf-8")
    lockfile = (FRONTEND_DIR / "package-lock.json").read_text(encoding="utf-8")

    assert "omit-lockfile-registry-resolved=true" in npmrc
    assert '"resolved"' not in lockfile
    assert "packages.applied-caas-gateway1.internal.api.openai.org" not in lockfile


def test_frontend_shell_contains_required_browser_demo_regions() -> None:
    app_file = FRONTEND_DIR / "src" / "App.jsx"
    assert app_file.is_file()

    content = app_file.read_text(encoding="utf-8")

    for required_text in (
        "SupportDoc RAG Chatbot",
        "Question box",
        "Submit",
        "Result panel",
        "Status area",
        "Supported answer",
        "Refusal",
        "Backend unavailable",
        "loading",
        "Refresh backend status",
        "Citation markers",
        "Citation markers only",
        "Do not paste secrets",
    ):
        assert required_text in content


def test_frontend_readme_and_env_example_document_local_startup_and_api_base_url() -> None:
    readme = (FRONTEND_DIR / "README.md").read_text(encoding="utf-8")
    env_example = (FRONTEND_DIR / ".env.example").read_text(encoding="utf-8")

    assert "./scripts/run-api-local.sh" in readme
    assert "npm install" in readme
    assert "npm run dev" in readme
    assert "^20.19.0 || >=22.12.0" in readme
    assert "VITE_SUPPORTDOC_API_BASE_URL" in readme
    assert "http://127.0.0.1:9001" in readme
    assert "POST /query" in readme
    assert "GET /readyz" in readme
    assert "citation markers only" in readme
    assert "Do not paste secrets" in readme
    assert "bash scripts/smoke-browser-demo.sh" in readme
    assert "VITE_SUPPORTDOC_API_BASE_URL=http://127.0.0.1:9001" in env_example


def test_repo_docs_link_to_frontend_scaffold_and_local_startup() -> None:
    readme_content = Path("README.md").read_text(encoding="utf-8")
    aws_note = Path("docs/architecture/aws_deployment.md").read_text(encoding="utf-8")
    validation_index = Path("docs/validation/README.md").read_text(encoding="utf-8")

    assert "## 7C. Local browser demo" in readme_content
    assert "frontend/README.md" in readme_content
    assert "VITE_SUPPORTDOC_API_BASE_URL" in readme_content
    assert "^20.19.0 || >=22.12.0" in readme_content
    assert "live `POST /query` submission" in readme_content
    assert "bash scripts/smoke-browser-demo.sh" in readme_content
    assert "checked-in React SPA browser demo under `frontend/`" in aws_note
    assert (
        "thin local browser demo now exists under `frontend/` and can call the live local API"
        in validation_index
    )
    assert "scripts/smoke-browser-demo.sh" in validation_index
