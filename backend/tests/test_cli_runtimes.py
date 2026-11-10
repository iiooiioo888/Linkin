"""CLI 技能運行時：只檢查固定命令，不執行安裝。"""

from __future__ import annotations

import json
import subprocess

from backend.company.cli_runtimes import CLI_RUNTIMES, format_status, probe_all, probe_runtime
from backend.scripts.cli_runtimes import main


def test_catalog_covers_cli_only_skills():
    ids = {item.skill_id for item in CLI_RUNTIMES}
    assert ids == {"agent-reach", "just-scrape", "agent-browser", "cli-anything"}
    assert all(item.check_args == ("--help",) for item in CLI_RUNTIMES)
    assert "pypi" not in CLI_RUNTIMES[0].install.lower()
    assert "github.com/Panniantong/agent-reach" in CLI_RUNTIMES[0].install


def test_missing_binary_is_not_installed():
    spec = CLI_RUNTIMES[0]
    row = probe_runtime(spec, which=lambda _name: None)
    assert row["installed"] is False
    assert row["ok"] is False
    assert row["detail"] == "尚未安裝"
    assert row["install"] == spec.install


def test_found_binary_runs_fixed_help_only():
    spec = next(item for item in CLI_RUNTIMES if item.id == "just-scrape")
    seen: list[list[str]] = []

    def _run(argv, **kwargs):
        seen.append(list(argv))
        assert kwargs["check"] is False
        return subprocess.CompletedProcess(argv, 0, stdout="just-scrape 1.2.3\n", stderr="")

    row = probe_runtime(spec, which=lambda _name: "/usr/local/bin/just-scrape", run=_run)
    assert seen == [["/usr/local/bin/just-scrape", "--help"]]
    assert row["installed"] is True
    assert row["ok"] is True
    assert row["detail"] == "just-scrape 1.2.3"


def test_timeout_stays_installed_but_not_ok():
    spec = CLI_RUNTIMES[1]

    def _run(argv, **_kwargs):
        raise subprocess.TimeoutExpired(argv, 8)

    row = probe_runtime(spec, which=lambda _name: "/bin/just-scrape", run=_run)
    assert row["installed"] is True
    assert row["ok"] is False
    assert row["detail"] == "檢查逾時"


def test_probe_all_uses_injected_which(monkeypatch):
    monkeypatch.setattr("backend.company.cli_runtimes.shutil.which", lambda name: f"/bin/{name}" if name == "agent-reach" else None)

    def _run(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    rows = probe_all(run=_run)
    by_id = {row["id"]: row for row in rows}
    assert by_id["agent-reach"]["installed"] is True
    assert by_id["agent-browser"]["installed"] is False
    text = format_status(rows)
    assert "已安裝" in text
    assert "未安裝" in text
    assert "npm install -g agent-browser" in text


def test_cli_json(capsys):
    code = main(["--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert {row["id"] for row in payload["runtimes"]} == {
        "agent-reach",
        "just-scrape",
        "agent-browser",
        "cli-anything",
    }
