from pathlib import Path

import pytest

from geniesim_cli.commands import benchmark


def test_check_inference_execs_with_clean_python_environment(monkeypatch, tmp_path):
    script = tmp_path / "check_inference.py"
    payload = tmp_path / "payload.pkl"
    script.write_text("# probe\n", encoding="utf-8")
    payload.write_bytes(b"payload")

    monkeypatch.setattr(benchmark, "_check_script", lambda: script)
    monkeypatch.setattr(benchmark, "_python_check_cmd", lambda: "/usr/bin/python3")
    monkeypatch.setattr(benchmark, "_resolve_payload", lambda arg: Path(arg))
    monkeypatch.setenv(
        "PYTHONPATH",
        "/isaac-sim/kit/python/lib/python3.11:/isaac-sim/kit/python/lib/python3.11/site-packages",
    )
    monkeypatch.setenv("PYTHONHOME", "/isaac-sim/kit/python")
    monkeypatch.setenv("GENIESIM_KEEP_ME", "1")

    called = {}

    def fake_execvpe(file, args, env):
        called["file"] = file
        called["args"] = args
        called["env"] = env

    def fail_execvp(*args):
        pytest.fail("check-inference must exec with an explicit sanitized environment")

    monkeypatch.setattr(benchmark.os, "execvpe", fake_execvpe)
    monkeypatch.setattr(benchmark.os, "execvp", fail_execvp)

    benchmark._do_check_inference([str(payload), "--infer-host=127.0.0.1:8999"])

    assert called["file"] == "/usr/bin/python3"
    assert called["args"] == [
        "/usr/bin/python3",
        str(script),
        str(payload),
        "--host",
        "127.0.0.1",
        "--port",
        "8999",
    ]
    assert "PYTHONPATH" not in called["env"]
    assert "PYTHONHOME" not in called["env"]
    assert called["env"]["GENIESIM_KEEP_ME"] == "1"
