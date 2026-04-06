from __future__ import annotations

import json
import subprocess
from pathlib import Path

FRONTEND_DIR = Path("frontend")


def _read_frontend_config_payload() -> dict[str, str]:
    script = """
import fs from "node:fs/promises";

const source = await fs.readFile(new URL("./src/config.js", import.meta.url), "utf8");
const moduleUrl = `data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`;
const { DEFAULT_API_BASE_URL, buildApiUrl, readApiBaseUrl } = await import(moduleUrl);

const configuredApiBaseUrl = readApiBaseUrl({
  VITE_SUPPORTDOC_API_BASE_URL: "https://api.example.test/",
});
const defaultApiBaseUrl = readApiBaseUrl();

console.log(
  JSON.stringify({
    configuredApiBaseUrl,
    configuredQueryUrl: buildApiUrl(configuredApiBaseUrl, "/query"),
    defaultApiBaseUrl,
    defaultReadinessUrl: buildApiUrl(defaultApiBaseUrl, "/readyz"),
  })
);
"""
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        check=True,
        capture_output=True,
        cwd=FRONTEND_DIR,
        text=True,
    )
    return json.loads(result.stdout)


def test_frontend_config_reads_non_local_api_base_url_from_vite_env() -> None:
    payload = _read_frontend_config_payload()

    assert payload["configuredApiBaseUrl"] == "https://api.example.test"
    assert payload["configuredQueryUrl"] == "https://api.example.test/query"


def test_frontend_config_keeps_local_default_when_vite_env_is_missing() -> None:
    payload = _read_frontend_config_payload()

    assert payload["defaultApiBaseUrl"] == "http://127.0.0.1:9001"
    assert payload["defaultReadinessUrl"] == "http://127.0.0.1:9001/readyz"
