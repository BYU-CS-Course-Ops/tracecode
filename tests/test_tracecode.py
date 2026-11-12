import io
import sys

import pytest

from tracecode import RecordingLimitExceeded, TraceRecorder


def load_function(tmp_path, source, name="run", namespace=None):
    filename = tmp_path / f"{name}.py"
    filename.write_text(source)
    scope = {} if namespace is None else namespace
    exec(compile(source, str(filename), "exec"), scope)
    return scope[name], filename


def decode_value(value):
    value_type = value["type"]
    data = value["data"]
    if value_type == "dict":
        return {decode_value(key): decode_value(item) for key, item in data}
    if value_type == "list":
        return [decode_value(item) for item in data]
    if value_type == "tuple":
        return tuple(decode_value(item) for item in data)
    if value_type == "opaque":
        return {"opaque": data["python_type"]}
    if value_type in {"NoneType", "bool", "int", "float", "str"}:
        return data
    return decode_value(data)


def decode_mapping(value):
    assert isinstance(value, dict)
    return {name: decode_value(item) for name, item in value.items()}


def record_function(func, filename, **options):
    recorder = TraceRecorder(target_file=str(filename), **options)
    with recorder:
        result = func()
    return result, recorder.recording


def test_line_snapshots_capture_state_before_each_line(tmp_path):
    func, filename = load_function(
        tmp_path,
        "def run():\n"
        "    value = 1\n"
        "    value = 2\n"
        "    return value\n",
    )

    result, recording = record_function(func, filename)

    assert result == 2
    assert recording[0]["event"] == "source"
    assert recording[0]["filename"] == str(filename)
    assert recording[0]["source"] == filename.read_text()
    lines = [snapshot for snapshot in recording if snapshot["event"] == "line"]
    values = [decode_mapping(snapshot["locals"])["value"] for snapshot in lines[1:]]
    assert values == [1, 2]
    assert recording[-1]["event"] == "return"
    assert recording[-1]["return"] == {"value": {"type": "int", "data": 2}}


def test_records_if_elif_and_each_while_condition_without_helper_frames(tmp_path):
    source = (
        "def run():\n"
        "    value = 0\n"
        "    while value < 2:\n"
        "        if value == 0:\n"
        "            value += 1\n"
        "        elif value == 1:\n"
        "            value += 1\n"
        "    return value\n"
        "run()\n"
    )
    filename = tmp_path / "conditions.py"
    filename.write_text(source)
    namespace = {"__name__": "__main__", "__file__": str(filename)}
    recorder = TraceRecorder(target_file=str(filename))

    with recorder:
        recorder.exec_source(namespace)

    conditions = [
        snapshot for snapshot in recorder.recording if snapshot["event"] == "condition"
    ]
    assert [snapshot["condition"]["result"]["data"] for snapshot in conditions] == [
        True, True, True, False, True, False
    ]
    assert [snapshot["condition"]["source"] for snapshot in conditions] == [
        "value < 2", "value == 0", "value < 2", "value == 0", "value == 1", "value < 2"
    ]
    assert [snapshot["condition"]["kind"] for snapshot in conditions] == [
        "while", "if", "while", "if", "if", "while"
    ]
    assert all(snapshot["function"] == "run" for snapshot in conditions)
    assert all(
        "tracecode_record_condition" not in repr(snapshot.get("globals", {}))
        for snapshot in conditions
    )
    assert all(
        caller["function"] != "_record_condition"
        for snapshot in conditions
        for caller in snapshot["callers"]
    )


def test_displays_sys_argv_as_a_module_local_when_source_uses_it(tmp_path, monkeypatch):
    source = "import sys\nargs = sys.argv\n"
    filename = tmp_path / "arguments.py"
    filename.write_text(source)
    monkeypatch.setattr(sys, "argv", [str(filename), "Gordon"])
    recorder = TraceRecorder(target_file=str(filename))

    with recorder:
        exec(compile(source, str(filename), "exec"), {})

    module_snapshots = [
        snapshot
        for snapshot in recorder.recording
        if snapshot["event"] == "line" and snapshot["function"] == "<module>"
    ]
    assert "sys.argv" not in decode_mapping(module_snapshots[0]["locals"])
    assert decode_mapping(module_snapshots[1]["locals"])["sys.argv"] == [
        str(filename), "Gordon"
    ]


def test_serializes_json_primitives_with_type_and_data(tmp_path):
    func, filename = load_function(
        tmp_path,
        "def run():\n"
        "    return [None, True, 2, 1.5, 'hello']\n",
    )

    _, recording = record_function(func, filename)

    returned = next(snapshot["return"]["value"] for snapshot in recording if snapshot["event"] == "return")
    assert returned == {
        "type": "list",
        "data": [
            {"type": "NoneType", "data": None},
            {"type": "bool", "data": True},
            {"type": "int", "data": 2},
            {"type": "float", "data": 1.5},
            {"type": "str", "data": "hello"},
        ],
    }


def test_serializes_collections_and_keeps_snapshots_independent(tmp_path):
    func, filename = load_function(
        tmp_path,
        "def run():\n"
        "    value = {1: (2, [3])}\n"
        "    value[1][1].append(4)\n"
        "    return value\n",
    )

    _, recording = record_function(func, filename)

    before_mutation = next(
        snapshot
        for snapshot in recording
        if snapshot["event"] == "line" and snapshot["lineno"] == 3
    )
    after_mutation = next(
        snapshot
        for snapshot in recording
        if snapshot["event"] == "line" and snapshot["lineno"] == 4
    )
    original_value = decode_mapping(before_mutation["locals"])["value"]
    mutated_value = decode_mapping(after_mutation["locals"])["value"]

    assert original_value == {1: (2, [3])}
    assert mutated_value == {1: (2, [3, 4])}


def test_snapshots_include_function_and_qualified_function_names(tmp_path):
    func, filename = load_function(
        tmp_path,
        "def outer():\n"
        "    def inner():\n"
        "        return 7\n"
        "    return inner()\n",
        name="outer",
    )

    _, recording = record_function(func, filename)

    names = {
        (snapshot["function"], snapshot["qualified_function"])
        for snapshot in recording
        if snapshot["event"] != "source"
    }
    assert ("outer", "outer") in names
    assert ("inner", "outer.<locals>.inner") in names


def test_function_return_records_return_site_and_call_site(tmp_path):
    func, filename = load_function(
        tmp_path,
        "def caller():\n"
        "    result = foo(7)\n"
        "    return result\n"
        "def foo(value):\n"
        "    return value\n",
        name="caller",
    )

    _, recording = record_function(func, filename)

    call_index = next(
        index
        for index, snapshot in enumerate(recording)
        if snapshot.get("function_call", {}).get("qualified_function") == "foo"
    )
    call_site = recording[call_index]
    assert call_site["event"] == "call"
    assert call_site["function"] == "caller"
    assert call_site["lineno"] == 2
    assert call_site["function_call"]["arguments"] == {
        "value": {"type": "int", "data": 7}
    }

    return_index = next(
        index
        for index, snapshot in enumerate(recording)
        if snapshot["event"] == "return" and snapshot["function"] == "foo"
    )
    assert call_index < return_index
    returned = recording[return_index]
    call_return = recording[return_index + 1]

    assert returned["lineno"] == 5
    assert returned["return"]["value"] == {"type": "int", "data": 7}
    assert call_return["event"] == "call_return"
    assert call_return["function"] == "caller"
    assert call_return["lineno"] == 2
    assert call_return["call_return"] == {
        "function": "foo",
        "qualified_function": "foo",
        "value": {"type": "int", "data": 7},
    }


def test_snapshots_capture_callers_oldest_first(tmp_path):
    func, filename = load_function(
        tmp_path,
        "def outer():\n"
        "    outer_value = 'outer'\n"
        "    def inner():\n"
        "        inner_value = 2\n"
        "        return inner_value\n"
        "    return inner()\n",
        name="outer",
    )

    _, recording = record_function(func, filename)

    inner_snapshot = next(
        snapshot
        for snapshot in recording
        if snapshot["event"] == "line" and snapshot["function"] == "inner"
    )
    callers = inner_snapshot["callers"]
    assert [caller["qualified_function"] for caller in callers] == ["outer"]
    assert callers[0]["lineno"] == 6
    assert decode_mapping(callers[0]["locals"])["outer_value"] == "outer"


def test_records_exceptions_that_are_handled(tmp_path):
    func, filename = load_function(
        tmp_path,
        "def run():\n"
        "    try:\n"
        "        raise ValueError('bad')\n"
        "    except ValueError:\n"
        "        return 'handled'\n",
    )

    result, recording = record_function(func, filename)

    assert result == "handled"
    exception = next(snapshot["exception"] for snapshot in recording if snapshot["event"] == "exception")
    assert exception["type"] == "ValueError"
    assert exception["message"] == "bad"
    assert [frame["function"] for frame in exception["traceback"]] == ["run"]
    assert exception["args"] == {"type": "tuple", "data": [{"type": "str", "data": "bad"}]}
    assert any(snapshot["event"] == "return" for snapshot in recording)


def test_captures_stdout_and_echoed_stdin_as_console_deltas(tmp_path, monkeypatch, capsys):
    func, filename = load_function(
        tmp_path,
        "def run():\n"
        "    name = input('Name? ')\n"
        "    print(f'Hello {name}')\n",
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("Ada\n"))
    recorder = TraceRecorder(target_file=str(filename))

    with recorder:
        func()

    chunks = [
        chunk
        for snapshot in recorder.recording
        for chunk in snapshot.get("console", [])
    ]
    assert "".join(chunk["text"] for chunk in chunks) == "Name? Ada\nHello Ada\n"
    assert [chunk["stream"] for chunk in chunks] == ["stdout", "stdin", "stdout", "stdout"]
    input_events = [
        event for event in recorder.recording
        if event["event"] in {"input_prompt", "input_return"}
    ]
    assert [event["event"] for event in input_events] == ["input_prompt", "input_return"]
    assert input_events[0]["prompt"] == "Name? "
    assert input_events[0]["console"] == [{"stream": "stdout", "text": "Name? "}]
    assert input_events[1]["input_return"] == {
        "typed_text": "Ada\n",
        "value": {"type": "str", "data": "Ada"},
    }
    assert input_events[1]["console"] == [{"stream": "stdin", "text": "Ada\n"}]
    assert capsys.readouterr().out == "Name? Hello Ada\n"


def test_input_prompt_is_recorded_when_stdin_reaches_eof(tmp_path, monkeypatch):
    func, filename = load_function(
        tmp_path,
        "def run():\n"
        "    input('Enter your name: ')\n",
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    recorder = TraceRecorder(target_file=str(filename))

    with pytest.raises(EOFError):
        with recorder:
            func()

    chunks = [
        chunk
        for snapshot in recorder.recording
        for chunk in snapshot.get("console", [])
    ]
    assert chunks == [{"stream": "stdout", "text": "Enter your name: "}]


def test_console_capture_respects_character_limit(tmp_path, capsys):
    func, filename = load_function(
        tmp_path,
        "def run():\n"
        "    print('abcdef')\n",
    )
    recorder = TraceRecorder(target_file=str(filename), max_console_chars=3)

    with recorder:
        func()

    chunks = [
        chunk
        for snapshot in recorder.recording
        for chunk in snapshot.get("console", [])
    ]
    assert "".join(chunk["text"] for chunk in chunks) == "abc\n[console capture truncated]\n"
    assert all(chunk["stream"] == "stdout" for chunk in chunks)
    capsys.readouterr()


def test_exception_traceback_grows_outward_as_exception_unwinds(tmp_path):
    func, filename = load_function(
        tmp_path,
        "def leaf():\n"
        "    raise ValueError('bad input')\n"
        "def middle():\n"
        "    return leaf()\n"
        "def outer():\n"
        "    return middle()\n",
        name="outer",
        namespace={},
    )
    recorder = TraceRecorder(target_file=str(filename))

    with pytest.raises(ValueError, match="bad input"):
        with recorder:
            func()

    exceptions = [record["exception"] for record in recorder.recording if "exception" in record]
    assert [
        [frame["function"] for frame in exception["traceback"]]
        for exception in exceptions
    ] == [["leaf"], ["middle", "leaf"], ["outer", "middle", "leaf"]]
    assert [
        [frame["lineno"] for frame in exception["traceback"]]
        for exception in exceptions
    ] == [[2], [4, 2], [6, 4, 2]]
    assert all(exception["type"] == "ValueError" for exception in exceptions)
    assert all(exception["message"] == "bad input" for exception in exceptions)
    assert exceptions[-1]["traceback"][-1]["source"] == "    raise ValueError('bad input')"
    assert not any(
        record["event"] == "return" and record["function"] in {"leaf", "middle", "outer"}
        for record in recorder.recording
    )


def test_traceback_includes_frame_that_started_recording(tmp_path):
    source = (
        "def run(recorder):\n"
        "    with recorder:\n"
        "        try:\n"
        "            outer()\n"
        "        except ValueError:\n"
        "            pass\n"
        "def outer():\n"
        "    raise ValueError('bad')\n"
    )
    filename = tmp_path / "run.py"
    filename.write_text(source)
    namespace = {}
    exec(compile(source, str(filename), "exec"), namespace)
    recorder = TraceRecorder(target_file=str(filename))

    namespace["run"](recorder)

    exceptions = [record["exception"] for record in recorder.recording if "exception" in record]
    assert [frame["function"] for frame in exceptions[-1]["traceback"]] == ["run", "outer"]


def test_records_only_frames_from_target_file(tmp_path):
    target, target_file = load_function(
        tmp_path,
        "def target():\n"
        "    return 42\n",
        name="target",
        namespace={},
    )
    wrapper, wrapper_file = load_function(
        tmp_path,
        "def wrapper():\n"
        "    return target()\n",
        name="wrapper",
        namespace={"target": target},
    )
    recorder = TraceRecorder(target_file=str(target_file))

    with recorder:
        assert wrapper() == 42

    assert recorder.recording
    assert {snapshot["filename"] for snapshot in recorder.recording} == {str(target_file)}
    assert str(wrapper_file) not in {snapshot["filename"] for snapshot in recorder.recording}


def test_custom_serializers_use_first_match_and_copy_output(tmp_path):
    class Parent:
        def __init__(self):
            self.items = [1]

    class Child(Parent):
        pass

    func, filename = load_function(
        tmp_path,
        "def run(value):\n"
        "    value.items.append(2)\n"
        "    return value\n",
    )
    value = Child()
    recorder = TraceRecorder(
        [
            (
                Parent,
                lambda obj: {"selected": "parent", "items": obj.items},
            ),
            (Child, lambda obj: {"selected": "child"}),
        ],
        target_file=str(filename),
    )

    with recorder:
        assert func(value) is value

    snapshots = [snapshot for snapshot in recorder.recording if snapshot["event"] == "line"]
    before = decode_mapping(snapshots[0]["locals"])["value"]
    after = decode_mapping(snapshots[1]["locals"])["value"]
    assert before == {"selected": "parent", "items": [1]}
    assert after == {"selected": "parent", "items": [1, 2]}
    encoded_before = snapshots[0]["locals"]["value"]
    assert encoded_before["type"] == f"{Child.__module__}.{Child.__qualname__}"
    assert encoded_before["data"]["type"] == "dict"


def test_opaque_values_do_not_call_repr(tmp_path):
    class Opaque:
        def __repr__(self):
            raise AssertionError("repr must not be called")

    func, filename = load_function(tmp_path, "def run(value):\n    return value\n")
    recorder = TraceRecorder(target_file=str(filename))

    with recorder:
        func(Opaque())

    first_snapshot = next(record for record in recorder.recording if record["event"] == "line")
    encoded_value = first_snapshot["locals"]["value"]
    assert encoded_value == {
        "type": "opaque",
        "data": {"python_type": f"{Opaque.__module__}.{Opaque.__qualname__}"},
    }


@pytest.mark.parametrize(
    ("options", "expected_snapshots"),
    [
        ({"max_snapshots": 1}, 1),
        ({"max_depth": 0}, 1),
        ({"max_items": 1}, 1),
    ],
)
def test_limits_raise_and_preserve_recorded_snapshots(tmp_path, options, expected_snapshots):
    func, filename = load_function(
        tmp_path,
        "def run():\n"
        "    value = [1]\n"
        "    return value\n",
    )
    recorder = TraceRecorder(target_file=str(filename), **options)
    previous_trace = sys.gettrace()

    with pytest.raises(RecordingLimitExceeded):
        with recorder:
            func()

    assert sum(record["event"] != "source" for record in recorder.recording) == expected_snapshots
    assert isinstance(recorder.recording, list)
    assert sys.gettrace() is previous_trace


def test_user_can_catch_limit_error_and_get_partial_snapshots(tmp_path):
    namespace = {"RecordingLimitExceeded": RecordingLimitExceeded}
    func, filename = load_function(
        tmp_path,
        "def run():\n"
        "    try:\n"
        "        value = 1\n"
        "    except RecordingLimitExceeded:\n"
        "        return 'handled'\n",
        namespace=namespace,
    )
    recorder = TraceRecorder(target_file=str(filename), max_snapshots=1)
    previous_trace = sys.gettrace()

    with recorder:
        result = func()

    assert result == "handled"
    assert sum(record["event"] != "source" for record in recorder.recording) == 1
    assert sys.gettrace() is previous_trace


def test_restores_previous_trace_when_limit_is_caught(tmp_path):
    namespace = {"RecordingLimitExceeded": RecordingLimitExceeded}
    func, filename = load_function(
        tmp_path,
        "def run():\n"
        "    try:\n"
        "        value = 1\n"
        "    except RecordingLimitExceeded:\n"
        "        return 'handled'\n",
        namespace=namespace,
    )
    previous_trace = sys.gettrace()

    def existing_trace(frame, event, arg):
        return existing_trace

    recorder = TraceRecorder(target_file=str(filename), max_snapshots=1)
    try:
        sys.settrace(existing_trace)
        with recorder:
            assert func() == "handled"
        assert sys.gettrace() is existing_trace
    finally:
        sys.settrace(previous_trace)


def test_serializer_error_propagates_and_restores_trace(tmp_path):
    class Value:
        pass

    def broken_serializer(value):
        raise LookupError("serializer failed")

    func, filename = load_function(tmp_path, "def run(value):\n    return value\n")
    recorder = TraceRecorder([(Value, broken_serializer)], target_file=str(filename))
    previous_trace = sys.gettrace()
    previous_stdout = sys.stdout
    previous_stdin = sys.stdin

    with pytest.raises(LookupError, match="serializer failed"):
        with recorder:
            func(Value())

    assert sys.gettrace() is previous_trace
    assert sys.stdout is previous_stdout
    assert sys.stdin is previous_stdin


def test_invalid_limits_are_rejected():
    with pytest.raises(ValueError):
        TraceRecorder(max_snapshots=0)
    with pytest.raises(ValueError):
        TraceRecorder(max_depth=-1)
    with pytest.raises(ValueError):
        TraceRecorder(max_items=0)
    with pytest.raises(ValueError):
        TraceRecorder(max_console_chars=0)
