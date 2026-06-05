import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_command(args, **kwargs):
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **kwargs,
    )


def test_shell_scripts_pass_bash_syntax_check():
    script_dirs = [
        ROOT / "scripts",
        ROOT / "backend" / "scripts",
        ROOT / "web" / "scripts",
        ROOT / "gateway" / "scripts",
    ]
    scripts = sorted(
        script
        for script_dir in script_dirs
        if script_dir.exists()
        for script in script_dir.glob("*.sh")
    )

    assert scripts, "expected deployment shell scripts to exist"

    failures = []
    for script in scripts:
        result = run_command(["bash", "-n", str(script)])
        if result.returncode != 0:
            failures.append(f"{script}: {result.stderr or result.stdout}")

    assert not failures, "\n".join(failures)


def copy_validate_script(tmp_path):
    gateway_dir = tmp_path / "gateway"
    scripts_dir = gateway_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    (gateway_dir / ".env").write_text("", encoding="utf-8")
    script = scripts_dir / "validate_config.sh"
    shutil.copy2(ROOT / "gateway" / "scripts" / "validate_config.sh", script)
    return script


def test_validate_config_accepts_minimal_valid_config(tmp_path):
    script = copy_validate_script(tmp_path)
    config = tmp_path / "valid.yaml"
    config.write_text(
        textwrap.dedent(
            """
            model_list:
              - model_name: test-model
                litellm_params:
                  model: openai/gpt-4o-mini
                  api_key: os.environ/OPENAI_API_KEY
            general_settings:
              master_key: os.environ/LITELLM_MASTER_KEY
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "OPENAI_API_KEY": "sk-" + "x" * 32,
        "LITELLM_MASTER_KEY": "sk-litellm-" + "x" * 32,
    }

    result = run_command(["bash", str(script), "--config", str(config)], env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "配置验证通过" in result.stdout


def test_validate_config_rejects_missing_required_model_list(tmp_path):
    script = copy_validate_script(tmp_path)
    config = tmp_path / "missing-model-list.yaml"
    config.write_text(
        textwrap.dedent(
            """
            general_settings:
              master_key: os.environ/LITELLM_MASTER_KEY
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    result = run_command(["bash", str(script), "--config", str(config)])

    assert result.returncode == 2
    assert "缺少必需字段: model_list" in result.stdout


def test_litellm_systemd_unit_keeps_local_gateway_binding_contract():
    unit = (ROOT / "gateway" / "systemd" / "litellm.service").read_text(encoding="utf-8")

    assert "EnvironmentFile=/opt/litellm-proxy/.env" in unit
    assert "WorkingDirectory=/opt/litellm-proxy" in unit
    assert "--host ${HOST:-127.0.0.1}" in unit
    assert "--port ${PORT:-4000}" in unit


def test_nginx_templates_preserve_ready_and_sse_proxying():
    app_template = (ROOT / "scripts" / "nginx" / "velab.conf.template").read_text(
        encoding="utf-8"
    )
    gateway_template = (ROOT / "gateway" / "nginx" / "litellm.conf").read_text(
        encoding="utf-8"
    )

    assert "location = /backend-api/ready" in app_template
    assert "proxy_pass http://127.0.0.1:8000/ready" in app_template
    assert "location /api/chat" in app_template
    assert "proxy_buffering off;" in app_template
    assert "proxy_buffering off;" in gateway_template
    assert "proxy_pass http://127.0.0.1:4000" in gateway_template


def test_health_check_json_remains_valid_when_curl_fails(tmp_path):
    project = tmp_path / "project"
    scripts_dir = project / "scripts"
    bin_dir = project / "bin"
    scripts_dir.mkdir(parents=True)
    (project / "backend").mkdir()
    (project / "gateway").mkdir()
    bin_dir.mkdir()

    health_check = scripts_dir / "health_check.sh"
    shutil.copy2(ROOT / "scripts" / "health_check.sh", health_check)

    curl_mock = bin_dir / "curl"
    curl_mock.write_text("#!/bin/sh\nexit 22\n", encoding="utf-8")
    curl_mock.chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
    }

    result = subprocess.run(
        ["bash", str(health_check), "--json"],
        cwd=project,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["overall_status"] == "unhealthy"
    assert payload["services"]["backend"]["status"] == "unhealthy"
    assert payload["services"]["web"]["status"] == "unhealthy"
    assert payload["services"]["gateway"]["status"] == "unhealthy"


def test_health_check_json_stays_clean_when_optional_dependency_checks_fail(tmp_path):
    project = tmp_path / "project"
    scripts_dir = project / "scripts"
    bin_dir = project / "bin"
    scripts_dir.mkdir(parents=True)
    (project / "backend").mkdir()
    (project / "gateway").mkdir()
    bin_dir.mkdir()

    health_check = scripts_dir / "health_check.sh"
    shutil.copy2(ROOT / "scripts" / "health_check.sh", health_check)

    curl_mock = bin_dir / "curl"
    curl_mock.write_text("#!/bin/sh\nexit 22\n", encoding="utf-8")
    curl_mock.chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DATABASE_URL": "postgresql://postgres:bad@127.0.0.1:1/fota",
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "MINIO_ENDPOINT": "127.0.0.1:1",
        "MINIO_ACCESS_KEY": "minioadmin",
        "MINIO_SECRET_KEY": "minioadmin",
    }

    result = subprocess.run(
        ["bash", str(health_check), "--json"],
        cwd=project,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["services"]["postgresql"]["status"] == "unhealthy"
    assert payload["services"]["redis"]["status"] == "unhealthy"
    assert payload["services"]["minio"]["status"] == "unhealthy"
