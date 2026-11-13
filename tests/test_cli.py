import json
import re

from tracecode.cli import main


def test_cli_runs_script_with_arguments_and_writes_viewer(tmp_path, monkeypatch, capsys):
    script = tmp_path / "script.py"
    script.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "Path(__file__).with_suffix('.args').write_text(json.dumps(sys.argv[1:]))\n"
        "def run():\n"
        "    result = 42\n"
        "    if result == 42:\n"
        "        result = 42\n"
        "    return result\n"
        "run()\n"
    )
    opened = []
    monkeypatch.setattr("tracecode.trace_viewer.webbrowser.open", opened.append)

    result = main(["--auto-open", str(script), "arg1", "--script-option"])

    assert result == 0
    assert json.loads(script.with_suffix(".args").read_text()) == ["arg1", "--script-option"]
    assert len(opened) == 1
    html = script.with_suffix(".html").read_text()
    payload = json.loads(
        re.search(
            r'<script id="trace-data" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        ).group(1)
    )
    assert payload["filename"] == "script.py"
    assert any(snapshot["function"] == "run" for snapshot in payload["recording"])
    assert payload["recording"][-1]["event"] == "exit"
    assert payload["recording"][-1]["exit"] == {"script": "script.py", "code": 0}
    condition = next(
        snapshot["condition"]
        for snapshot in payload["recording"]
        if snapshot["event"] == "condition"
    )
    assert condition == {
        "result": {"type": "bool", "data": True},
        "kind": "if",
        "source": "result == 42",
    }
    assert str(script.with_suffix(".html")) in capsys.readouterr().out


def test_cli_writes_trace_before_reporting_script_exception(tmp_path, capsys):
    script = tmp_path / "broken.py"
    script.write_text(
        "def run():\n"
        "    raise ValueError('script failed')\n"
        "run()\n"
    )

    result = main([str(script)])

    assert result == 1
    html = script.with_suffix(".html").read_text()
    payload = json.loads(
        re.search(
            r'<script id="trace-data" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        ).group(1)
    )
    exceptions = [snapshot["exception"] for snapshot in payload["recording"] if "exception" in snapshot]
    assert payload["recording"][-1]["event"] == "exit"
    assert payload["recording"][-1]["exit"]["code"] == 1
    assert exceptions[-1]["type"] == "ValueError"
    assert exceptions[-1]["message"] == "script failed"
    assert "ValueError: script failed" in capsys.readouterr().err
