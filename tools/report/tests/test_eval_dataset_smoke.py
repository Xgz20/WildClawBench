from tools.report.lib.eval_dataset.smoke import run_warmup_smoke


def test_smoke_without_commands_or_docker(monkeypatch, tmp_path):
    assert run_warmup_smoke([], image="image", workspace=tmp_path) == []
    monkeypatch.setattr("tools.report.lib.eval_dataset.smoke.shutil.which", lambda _: None)
    result = run_warmup_smoke(["echo ok"], image="image", workspace=tmp_path)
    assert result[0]["code"] == "SMOKE_UNAVAILABLE"


def test_smoke_uses_rm_and_returns_status(monkeypatch, tmp_path):
    calls = []

    class Completed:
        returncode = 0
        stderr = ""

    monkeypatch.setattr("tools.report.lib.eval_dataset.smoke.shutil.which", lambda _: "/usr/local/bin/docker")
    monkeypatch.setattr("tools.report.lib.eval_dataset.smoke.subprocess.run", lambda argv, **kwargs: (calls.append((argv, kwargs)) or Completed()))
    result = run_warmup_smoke(["echo ok"], image="image", workspace=tmp_path)
    assert result[0]["code"] == "WARMUP_SMOKE_PASSED"
    assert "--rm" in calls[0][0]
    assert calls[0][1]["timeout"]
