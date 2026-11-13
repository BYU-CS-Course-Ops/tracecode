from __future__ import annotations

import ast
import builtins
import inspect
import linecache
import os
import sys
import tokenize
from types import TracebackType
from typing import Any, Callable, Protocol


class Serializer(Protocol):
    def __call__(self, item: Any, /) -> Any: ...


class RecordingLimitExceeded(RuntimeError):
    """Raised when a recording exceeds a configured snapshot or value limit."""


class _CallInstrumenter(ast.NodeTransformer):
    def __init__(self, helper_name: str, source: str):
        self.helper_name = helper_name
        self.source = source

    def visit_Call(self, node: ast.Call):
        self.generic_visit(node)
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in {"super", "locals", "vars", "globals", "eval", "exec"}
        ):
            # These builtins depend on the caller frame; a wrapper would change semantics.
            return node
        source_name = ast.get_source_segment(self.source, node.func) or "function"
        proxy = ast.Call(
            func=ast.Name(id=self.helper_name, ctx=ast.Load()),
            args=[node.func, ast.Constant(source_name)],
            keywords=[],
        )
        wrapped = ast.Call(func=proxy, args=node.args, keywords=node.keywords)
        return ast.copy_location(wrapped, node)


class _ConditionInstrumenter(ast.NodeTransformer):
    def __init__(self, helper_name: str, source: str):
        self.helper_name = helper_name
        self.source = source

    def _wrap(self, test: ast.expr, kind: str) -> ast.expr:
        call = ast.Call(
            func=ast.Name(id=self.helper_name, ctx=ast.Load()),
            args=[
                test,
                ast.Constant(kind),
                ast.Constant(ast.get_source_segment(self.source, test) or ""),
            ],
            keywords=[],
        )
        return ast.copy_location(call, test)

    def visit_If(self, node: ast.If):
        self.generic_visit(node)
        node.test = self._wrap(node.test, "if")
        return node

    def visit_While(self, node: ast.While):
        self.generic_visit(node)
        node.test = self._wrap(node.test, "while")
        return node


class _CallProxy:
    def __init__(self, recorder: TraceRecorder, function: Any, source_name: str):
        self._recorder = recorder
        self._function = function
        self._source_name = source_name

    def __call__(self, *args, **kwargs):
        recorder = self._recorder
        caller = inspect.currentframe().f_back
        if (
            recorder._active
            and caller is not None
            and os.path.realpath(caller.f_code.co_filename) == recorder._target_file
        ):
            recorder._record_call(caller, self._source_name, args, kwargs)
        value = self._function(*args, **kwargs)
        if (
            recorder._active
            and caller is not None
            and os.path.realpath(caller.f_code.co_filename) == recorder._target_file
        ):
            recorder._record_call_return(caller, self._source_name, value)
        return value


class _TeeTextStream:
    def __init__(self, stream, on_text: Callable[[str, str], None]):
        self._stream = stream
        self._on_text = on_text

    def write(self, text: str):
        written = self._stream.write(text)
        self._on_text("stdout", text if written is None else text[:written])
        return written

    def __getattr__(self, name):
        return getattr(self._stream, name)


class _RecordingInputStream:
    def __init__(self, stream, on_text: Callable[[str, str], None]):
        self._stream = stream
        self._on_text = on_text

    def read(self, *args, **kwargs):
        text = self._stream.read(*args, **kwargs)
        self._on_text("stdin", text)
        return text

    def readline(self, *args, **kwargs):
        text = self._stream.readline(*args, **kwargs)
        self._on_text("stdin", text)
        return text

    def readlines(self, *args, **kwargs):
        lines = self._stream.readlines(*args, **kwargs)
        self._on_text("stdin", "".join(lines))
        return lines

    def __iter__(self):
        return self

    def __next__(self):
        line = self.readline()
        if not line:
            raise StopIteration
        return line

    def __getattr__(self, name):
        return getattr(self._stream, name)


class TraceRecorder:
    """Record execution snapshots and console deltas for one Python source file."""

    def __init__(
        self,
        serializers: list[tuple[type, Serializer]] | None = None,
        *,
        max_snapshots: int = 10_000,
        max_depth: int = 20,
        max_items: int = 10_000,
        max_console_chars: int = 1_000_000,
        target_file: str | None = None,
    ):
        if max_snapshots < 1 or max_depth < 0 or max_items < 1 or max_console_chars < 1:
            raise ValueError("limits must be positive, except max_depth which may be zero")
        self._serializers = list(serializers or [])
        self._max_snapshots = max_snapshots
        self._max_depth = max_depth
        self._max_items = max_items
        self._max_console_chars = max_console_chars
        self._target_file = os.path.realpath(target_file) if target_file else None
        self._previous_trace: Callable | None = None
        self._target_frame = None
        self._previous_target_frame_trace = None
        self._active = False
        self._recording: list[dict[str, Any]] = []
        self._snapshot_count = 0
        self._source_lines: list[str] = []
        self._source = ""
        self._condition_helper_name: str | None = None
        self._uses_sys_argv = False
        self._unwinding_frames: set[int] = set()
        self._previous_stdout = None
        self._previous_stdin = None
        self._previous_input = None
        self._input_call_active = False
        self._console_parts: list[dict[str, str]] = []
        self._console_chars = 0
        self._console_truncated = False

    @property
    def recording(self) -> list[dict[str, Any]]:
        return self._recording

    def __enter__(self) -> TraceRecorder:
        if self._active:
            raise RuntimeError("TraceRecorder is already active")
        caller = inspect.currentframe().f_back
        if self._target_file is None:
            if caller is None:
                raise RuntimeError("Cannot determine target source file")
            self._target_file = os.path.realpath(caller.f_code.co_filename)
        self._target_frame = (
            caller
            if caller is not None
            and os.path.realpath(caller.f_code.co_filename) == self._target_file
            else None
        )
        if self._target_frame is not None:
            self._previous_target_frame_trace = self._target_frame.f_trace
        with tokenize.open(self._target_file) as source_file:
            source = source_file.read()
        self._source = source
        self._source_lines = source.splitlines()
        self._condition_helper_name = None
        try:
            syntax_tree = ast.parse(source, filename=self._target_file)
        except SyntaxError:
            self._uses_sys_argv = False
        else:
            self._uses_sys_argv = any(
                isinstance(node, ast.Attribute)
                and node.attr == "argv"
                and isinstance(node.value, ast.Name)
                and node.value.id == "sys"
                for node in ast.walk(syntax_tree)
            )
        self._recording.clear()
        self._snapshot_count = 0
        self._unwinding_frames.clear()
        self._console_parts.clear()
        self._console_chars = 0
        self._console_truncated = False
        self._recording.append(
            {"event": "source", "filename": self._target_file, "source": source}
        )
        self._previous_trace = sys.gettrace()
        self._previous_stdout = sys.stdout
        self._previous_stdin = sys.stdin
        self._previous_input = builtins.input
        if self._previous_stdout is not None:
            sys.stdout = _TeeTextStream(self._previous_stdout, self._record_console)
        if self._previous_stdin is not None:
            sys.stdin = _RecordingInputStream(self._previous_stdin, self._record_console)
        builtins.input = self._recording_input
        self._active = True
        sys.settrace(self._trace)
        if self._target_frame is not None:
            self._target_frame.f_trace = self._trace
        return self

    def exec_source(self, namespace: dict[str, Any]):
        """Execute this recorder's source after instrumenting if/elif/while tests."""
        if not self._active:
            raise RuntimeError("TraceRecorder must be active to execute source")
        syntax_tree = ast.parse(self._source, filename=self._target_file)
        names = {
            node.id
            for node in ast.walk(syntax_tree)
            if isinstance(node, ast.Name)
        }
        call_helper_name = "__tracecode_call__"
        condition_helper_name = "__tracecode_record_condition__"
        while (
            call_helper_name in names
            or call_helper_name in namespace
            or condition_helper_name in names
            or condition_helper_name in namespace
        ):
            call_helper_name += "_"
            condition_helper_name += "_"
        self._condition_helper_name = condition_helper_name
        namespace[call_helper_name] = self._make_call_proxy
        namespace[condition_helper_name] = self._record_condition
        syntax_tree = _CallInstrumenter(call_helper_name, self._source).visit(syntax_tree)
        syntax_tree = _ConditionInstrumenter(condition_helper_name, self._source).visit(syntax_tree)
        ast.fix_missing_locations(syntax_tree)
        code = compile(syntax_tree, self._target_file, "exec", dont_inherit=True)
        exec(code, namespace)

    def _make_call_proxy(self, function: Any, source_name: str) -> Any:
        if inspect.isfunction(function):
            return function
        if inspect.ismethod(function) and function.__func__ is not TraceRecorder._recording_input:
            return function
        return _CallProxy(self, function, source_name)

    def _record_call(self, frame, source_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]):
        self._record_snapshot(
            frame,
            "call",
            {
                "qualified_function": source_name,
                "positional_arguments": args,
                "keyword_arguments": kwargs,
            },
        )

    def _record_call_return(self, frame, source_name: str, value: Any):
        self._record_snapshot(
            frame,
            "call_return",
            {"qualified_function": source_name, "value": value},
        )

    def _record_condition(self, value: Any, kind: str, source: str) -> bool:
        result = bool(value)
        frame = inspect.currentframe().f_back
        if (
            self._active
            and frame is not None
            and os.path.realpath(frame.f_code.co_filename) == self._target_file
        ):
            self._record_snapshot(
                frame,
                "condition",
                {"result": result, "kind": kind, "source": source},
            )
        return result

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        self._stop_tracing()
        self._previous_trace = None
        return False

    def _stop_tracing(self):
        if self._active:
            self._active = False
            if self._target_frame is not None and self._target_frame.f_trace is self._trace:
                self._target_frame.f_trace = self._previous_target_frame_trace
            self._target_frame = None
            self._previous_target_frame_trace = None
            sys.stdout = self._previous_stdout
            sys.stdin = self._previous_stdin
            builtins.input = self._previous_input
            self._previous_stdout = None
            self._previous_stdin = None
            self._previous_input = None
        sys.settrace(self._previous_trace)

    def _trace(self, frame, event: str, arg):
        if not self._active:
            return None
        try:
            frame_id = id(frame)
            if event == "line":
                self._unwinding_frames.discard(frame_id)
            elif event == "exception":
                self._unwinding_frames.add(frame_id)
            elif event == "return" and frame_id in self._unwinding_frames:
                # The preceding exception snapshot already represents this frame's unwind.
                self._unwinding_frames.discard(frame_id)
                return self._trace

            is_target_frame = os.path.realpath(frame.f_code.co_filename) == self._target_file
            caller = frame.f_back
            is_importlib_frame = frame.f_globals.get("__name__", "").startswith("importlib.")
            is_trace_helper = frame.f_code in (
                TraceRecorder._recording_input.__code__,
                TraceRecorder._record_condition.__code__,
                TraceRecorder._make_call_proxy.__code__,
                _CallProxy.__call__.__code__,
                _TeeTextStream.write.__code__,
            )
            is_generator = bool(
                frame.f_code.co_flags
                & (
                    inspect.CO_GENERATOR
                    | inspect.CO_COROUTINE
                    | inspect.CO_ASYNC_GENERATOR
                )
            )
            is_direct_target_call = (
                caller is not None
                and os.path.realpath(caller.f_code.co_filename) == self._target_file
            )
            if (
                not is_target_frame
                and event == "call"
                and is_direct_target_call
                and not is_trace_helper
                and not is_importlib_frame
            ):
                self._record_snapshot(caller, "call", frame)
            if (
                not is_target_frame
                and event == "return"
                and is_direct_target_call
                and not is_generator
                and not is_trace_helper
                and not is_importlib_frame
            ):
                self._record_snapshot(caller, "call_return", (frame, arg))
            if not is_target_frame:
                return self._trace
            # Python calls are captured at frame entry; C-callable objects are
            # captured by the AST-installed proxy.
            if (
                event == "call"
                and caller is not None
                and os.path.realpath(caller.f_code.co_filename) == self._target_file
            ):
                self._record_snapshot(caller, "call", frame)
            elif event in ("line", "return", "exception"):
                self._record_snapshot(frame, event, arg)
                if (
                    event == "return"
                    and caller is not None
                    and os.path.realpath(caller.f_code.co_filename) == self._target_file
                ):
                    self._record_snapshot(caller, "call_return", (frame, arg))
        except BaseException:
            self._stop_tracing()
            raise
        return self._trace

    def _recording_input(self, prompt: str = "") -> str:
        caller = inspect.currentframe().f_back
        if caller is not None and caller.f_code is _CallProxy.__call__.__code__:
            caller = caller.f_back
        records_input = (
            caller is not None
            and os.path.realpath(caller.f_code.co_filename) == self._target_file
        )
        if isinstance(prompt, str):
            self._record_console("stdout", prompt)
            if records_input:
                self._record_snapshot(caller, "input_prompt", prompt)

        self._input_call_active = True
        try:
            value = self._previous_input(prompt)
        except BaseException:
            self._input_call_active = False
            if not records_input and isinstance(prompt, str):
                self._record_console("stdout", prompt)
            raise
        self._input_call_active = False
        if isinstance(value, str):
            self._record_console("stdin", value + "\n")
            if records_input:
                self._record_snapshot(caller, "input_return", value)
        return value

    def _record_console(self, stream: str, text: str):
        if self._input_call_active or not isinstance(text, str) or not text or self._console_truncated:
            return
        remaining = self._max_console_chars - self._console_chars
        if remaining > 0:
            text_to_keep = text[:remaining]
            self._console_parts.append({"stream": stream, "text": text_to_keep})
            self._console_chars += len(text_to_keep)
        if len(text) > remaining:
            self._console_parts.append(
                {"stream": stream, "text": "\n[console capture truncated]\n"}
            )
            self._console_truncated = True

    def _take_console_delta(self) -> list[dict[str, str]]:
        chunks = self._console_parts
        self._console_parts = []
        return chunks

    def _record_snapshot(self, frame, event: str, arg):
        if self._snapshot_count >= self._max_snapshots:
            raise RecordingLimitExceeded(
                f"Recording exceeded the {self._max_snapshots}-snapshot limit"
            )
        self._recording.append(self._snapshot(frame, event, arg))
        self._snapshot_count += 1

    def _snapshot(self, frame, event: str, arg) -> dict[str, Any]:
        budget = [0]
        console_delta = self._take_console_delta()
        snapshot: dict[str, Any] = {
            "event": event,
            "filename": frame.f_code.co_filename,
            "lineno": frame.f_lineno,
            "function": frame.f_code.co_name,
            "qualified_function": frame.f_code.co_qualname,
        }
        snapshot["locals"] = self._serialize_scope(self._frame_locals(frame), budget)
        snapshot["callers"] = self._capture_callers(frame.f_back, budget)
        if console_delta:
            snapshot["console"] = console_delta

        if event == "return":
            snapshot["return"] = {"value": self._serialize(arg, 0, budget)}
        elif event == "exception":
            _, exception, traceback = arg
            snapshot["exception"] = {
                "type": self._type_name(exception),
                "message": self._exception_message(exception),
                "args": self._serialize(exception.args, 0, budget),
                "traceback": self._capture_traceback(traceback),
            }
        elif event == "call_return":
            if isinstance(arg, dict):
                function_name = arg["qualified_function"]
                qualified_function = function_name
                value = arg["value"]
            else:
                returned_frame, value = arg
                function_name = returned_frame.f_code.co_name
                qualified_function = returned_frame.f_code.co_qualname
            snapshot["call_return"] = {
                "function": function_name,
                "qualified_function": qualified_function,
                "value": self._serialize(value, 0, budget),
            }
        elif event == "input_prompt":
            snapshot["prompt"] = arg
        elif event == "condition":
            snapshot["condition"] = {
                "result": self._serialize(arg["result"], 0, budget),
                "kind": arg["kind"],
                "source": arg["source"],
            }
        elif event == "input_return":
            snapshot["input_return"] = {
                "typed_text": arg + "\n",
                "value": self._serialize(arg, 0, budget),
            }
        elif event == "call":
            if isinstance(arg, dict):
                snapshot["function_call"] = {
                    "qualified_function": arg["qualified_function"],
                    "arguments": self._serialize_scope(arg["keyword_arguments"], budget),
                    "positional_arguments": [
                        self._serialize(value, 0, budget)
                        for value in arg["positional_arguments"]
                    ],
                }
            else:
                snapshot["function_call"] = {
                    "qualified_function": arg.f_code.co_qualname,
                    "arguments": self._serialize_scope(
                        self._visible_values(arg.f_locals), budget
                    ),
                }
        return snapshot

    def _exception_message(self, exception: BaseException) -> str:
        previous_trace = sys.gettrace()
        sys.settrace(None)
        try:
            return str(exception)
        except BaseException:
            return ""
        finally:
            sys.settrace(previous_trace)

    def _capture_traceback(self, traceback: TracebackType | None) -> list[dict[str, Any]]:
        frames = []
        while traceback is not None:
            frame = traceback.tb_frame
            filename = frame.f_code.co_filename
            lineno = traceback.tb_lineno
            if os.path.realpath(filename) == self._target_file:
                source = (
                    self._source_lines[lineno - 1]
                    if 0 < lineno <= len(self._source_lines)
                    else ""
                )
            else:
                source = linecache.getline(filename, lineno).rstrip("\r\n")
            frames.append(
                {
                    "filename": filename,
                    "lineno": lineno,
                    "function": frame.f_code.co_name,
                    "qualified_function": frame.f_code.co_qualname,
                    "source": source,
                }
            )
            traceback = traceback.tb_next
        return frames

    def _capture_callers(self, frame, budget: list[int]) -> list[dict[str, Any]]:
        callers = []
        while frame is not None:
            if os.path.realpath(frame.f_code.co_filename) == self._target_file:
                callers.append(
                    {
                        "function": frame.f_code.co_name,
                        "qualified_function": frame.f_code.co_qualname,
                        "lineno": frame.f_lineno,
                        "locals": self._serialize_scope(self._frame_locals(frame), budget),
                    }
                )
            frame = frame.f_back
        return list(reversed(callers))

    def _serialize_scope(self, values: dict[str, Any], budget: list[int]) -> dict[str, Any]:
        return {name: self._serialize(value, 0, budget) for name, value in values.items()}

    def _frame_locals(self, frame) -> dict[str, Any]:
        values = self._visible_values(frame.f_locals)
        if (
            frame.f_code.co_name == "<module>"
            and self._uses_sys_argv
            and frame.f_globals.get("sys") is sys
        ):
            values["sys.argv"] = sys.argv
        return values

    def _visible_values(self, values: dict[str, Any]) -> dict[str, Any]:
        return {
            name: value
            for name, value in values.items()
            if not (name.startswith("__") and name.endswith("__"))
            and name != self._condition_helper_name
        }

    @staticmethod
    def _type_name(value: Any) -> str:
        value_type = type(value)
        if value_type.__module__ == "builtins":
            return value_type.__qualname__
        return f"{value_type.__module__}.{value_type.__qualname__}"

    def _serialize(self, value: Any, depth: int, budget: list[int]) -> Any:
        budget[0] += 1
        type_name = self._type_name(value)
        if budget[0] > self._max_items:
            raise RecordingLimitExceeded(
                f"Snapshot exceeded the {self._max_items}-item serialization limit"
            )
        if depth > self._max_depth:
            raise RecordingLimitExceeded(
                f"Snapshot exceeded the {self._max_depth}-level serialization depth limit"
            )

        for value_type, serializer in self._serializers:
            if isinstance(value, value_type):
                data = self._serialize(serializer(value), depth + 1, budget)
                return {"type": type_name, "data": data}

        if isinstance(value, BaseException):
            return {
                "type": "opaque",
                "data": {
                    "python_type": type_name,
                    "exception_message": self._exception_message(value),
                },
            }

        if value is None:
            return {"type": "NoneType", "data": None}
        if type(value) in (bool, int, float, str):
            return {"type": self._type_name(value), "data": value}
        if type(value) is list:
            return {
                "type": "list",
                "data": [self._serialize(item, depth + 1, budget) for item in value],
            }
        if type(value) is tuple:
            return {
                "type": "tuple",
                "data": [self._serialize(item, depth + 1, budget) for item in value],
            }
        if type(value) is dict:
            return {
                "type": "dict",
                "data": [
                    [self._serialize(key, depth + 1, budget), self._serialize(item, depth + 1, budget)]
                    for key, item in value.items()
                ],
            }
        return {"type": "opaque", "data": {"python_type": type_name}}
