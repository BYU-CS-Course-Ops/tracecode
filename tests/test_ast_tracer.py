import io
import sys

from tracecode import PreparedSource, SetTraceRecorder, TraceRecorder, prepare_file
from tracecode.code_tracer import TraceRecorder as ModuleTraceRecorder


def test_ast_recorder_tracks_target_statements_calls_conditions_and_io(tmp_path, monkeypatch):
    filename = tmp_path / "student.py"
    filename.write_text(
        "def double(value):\n"
        "    return value * 2\n"
        "name = input('Name? ')\n"
        "number = int(name)\n"
        "if number > 1:\n"
        "    result = double(number)\n"
        "print(result)\n"
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("3\n"))
    previous_trace = sys.gettrace()
    prepared = prepare_file(filename)
    assert isinstance(prepared, PreparedSource)
    assert ModuleTraceRecorder is TraceRecorder
    assert SetTraceRecorder is not TraceRecorder
    namespace = {"__name__": "__main__", "__file__": str(filename)}
    recorder = TraceRecorder(target_file=str(filename))

    with recorder:
        prepared.execute(namespace)

    assert sys.gettrace() is previous_trace
    assert namespace["result"] == 6
    events = [item["event"] for item in recorder.recording]
    assert "condition" in events
    assert "input_prompt" in events and "input_return" in events
    assert "call" in events and "call_return" in events
    assert any(item.get("console") for item in recorder.recording)
    calls = [item for item in recorder.recording if item["event"] == "call"]
    assert any(item["function_call"]["qualified_function"] == "double" for item in calls)
    returns = [item for item in recorder.recording if item["event"] == "call_return"]
    assert any(item["call_return"]["value"] == {"type": "int", "data": 6} for item in returns)
    assert all(item["filename"] == str(filename) for item in recorder.recording[1:])


def test_ast_recorder_does_not_record_module_setup_when_activated_later(tmp_path):
    filename = tmp_path / "student.py"
    filename.write_text(
        "setup = 1\n"
        "def run():\n"
        "    value = 2\n"
        "    return value\n"
    )
    prepared = prepare_file(filename)
    namespace = {"__name__": "student", "__file__": str(filename)}
    prepared.execute(namespace)

    recorder = TraceRecorder(target_file=str(filename))
    with recorder:
        assert namespace["run"]() == 2

    assert not any(
        item["event"] == "line" and item["function"] == "<module>"
        for item in recorder.recording
    )
