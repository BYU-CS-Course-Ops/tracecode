from __future__ import annotations

import ast
import builtins
import inspect
import os
import tokenize
import uuid
from typing import Any

from .code_tracer import (
    PreparedSource,
    SetTraceRecorder,
    _ACTIVE_RECORDER,
    _CallInstrumenter,
    _ConditionInstrumenter,
    _TeeTextStream,
    _active_record_condition,
)


class _StatementInstrumenter(ast.NodeTransformer):
    def __init__(self, helper_name: str):
        self.helper_name = helper_name

    def generic_visit(self, node):
        node = super().generic_visit(node)
        for field, value in ast.iter_fields(node):
            if isinstance(value, list) and value and all(
                isinstance(item, ast.stmt) for item in value
            ):
                instrumented = []
                for statement in value:
                    hook = ast.Expr(
                        value=ast.Call(
                            func=ast.Name(id=self.helper_name, ctx=ast.Load()),
                            args=[],
                            keywords=[],
                        )
                    )
                    instrumented.append(ast.copy_location(hook, statement))
                    instrumented.append(statement)
                setattr(node, field, instrumented)
        return node


class _ASTCallProxy:
    def __init__(self, recorder: TraceRecorder, function: Any, source_name: str):
        self.recorder = recorder
        self.function = function
        self.source_name = source_name

    def __call__(self, *args, **kwargs):
        caller = inspect.currentframe().f_back
        is_target = (
            self.recorder._active
            and caller is not None
            and os.path.realpath(caller.f_code.co_filename) == self.recorder._target_file
        )
        if is_target:
            self.recorder._record_call(caller, self.source_name, args, kwargs)
        result = self.function(*args, **kwargs)
        if is_target:
            self.recorder._record_call_return(caller, self.source_name, result)
        return result


def _active_ast_call_proxy(function: Any, source_name: str) -> Any:
    recorder = _ACTIVE_RECORDER.get()
    if recorder is None or not recorder._active:
        return function
    if hasattr(recorder, "_make_ast_call_proxy"):
        return recorder._make_ast_call_proxy(function, source_name)
    return recorder._make_call_proxy(function, source_name)


def _active_ast_line() -> None:
    recorder = _ACTIVE_RECORDER.get()
    if recorder is None or not recorder._active:
        return
    frame = inspect.currentframe().f_back
    if os.path.realpath(frame.f_code.co_filename) == recorder._target_file:
        recorder._record_snapshot(frame, "line", None)


class ASTPreparedSource(PreparedSource):
    """Source instrumented with AST hooks rather than interpreter tracing."""

    def __init__(self, source: str, filename: str):
        self.source = source
        self.filename = os.path.realpath(filename)
        tree = ast.parse(source, filename=self.filename)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        suffix = uuid.uuid4().hex
        self.call_helper_name = f"__tracecode_ast_call_{suffix}__"
        self.condition_helper_name = f"__tracecode_ast_condition_{suffix}__"
        self.line_helper_name = f"__tracecode_ast_line_{suffix}__"
        while names.intersection(
            {self.call_helper_name, self.condition_helper_name, self.line_helper_name}
        ):
            suffix = uuid.uuid4().hex
            self.call_helper_name = f"__tracecode_ast_call_{suffix}__"
            self.condition_helper_name = f"__tracecode_ast_condition_{suffix}__"
            self.line_helper_name = f"__tracecode_ast_line_{suffix}__"

        tree = _CallInstrumenter(self.call_helper_name, source).visit(tree)
        tree = _ConditionInstrumenter(self.condition_helper_name, source).visit(tree)
        tree = _StatementInstrumenter(self.line_helper_name).visit(tree)
        ast.fix_missing_locations(tree)
        self._code = compile(tree, self.filename, "exec", dont_inherit=True)

    def execute(self, namespace: dict[str, Any]) -> None:
        helpers = {
            self.call_helper_name: _active_ast_call_proxy,
            self.condition_helper_name: _active_record_condition,
            self.line_helper_name: _active_ast_line,
        }
        if any(name in namespace for name in helpers):
            raise RuntimeError("Prepared source helper name collides with its namespace")
        namespace.update(helpers)
        exec(self._code, namespace)  # noqa: S102 - execute prepared student source


def prepare_ast_file(filename: str | os.PathLike[str]) -> ASTPreparedSource:
    """Read, AST-instrument, and compile a Python file without executing it."""
    path = os.path.realpath(os.fspath(filename))
    with tokenize.open(path) as source_file:
        return ASTPreparedSource(source_file.read(), path)


class TraceRecorder(SetTraceRecorder):
    """Trace target-file activity using AST hooks, without ``sys.settrace``."""

    def _make_ast_call_proxy(self, function: Any, source_name: str) -> Any:
        return _ASTCallProxy(self, function, source_name)

    def __enter__(self) -> TraceRecorder:
        if self._active:
            raise RuntimeError("TraceRecorder is already active")
        caller = inspect.currentframe().f_back
        if self._target_file is None:
            if caller is None:
                raise RuntimeError("Cannot determine target source file")
            self._target_file = os.path.realpath(caller.f_code.co_filename)
        with tokenize.open(self._target_file) as source_file:
            self._source = source_file.read()
        self._source_lines = self._source.splitlines()
        try:
            source_tree = ast.parse(self._source, filename=self._target_file)
        except SyntaxError:
            self._uses_sys_argv = False
        else:
            self._uses_sys_argv = any(
                isinstance(node, ast.Attribute)
                and node.attr == "argv"
                and isinstance(node.value, ast.Name)
                and node.value.id == "sys"
                for node in ast.walk(source_tree)
            )
        self._condition_helper_name = None
        self._recording.clear()
        self._snapshot_count = 0
        self._unwinding_frames.clear()
        self._console_parts.clear()
        self._console_chars = 0
        self._console_truncated = False
        self._recording.append(
            {"event": "source", "filename": self._target_file, "source": self._source}
        )
        # Use the same lightweight output tee and input wrapper as SetTraceRecorder.
        import sys

        self._previous_stdout = sys.stdout
        self._previous_stdin = sys.stdin
        self._previous_input = builtins.input
        if self._previous_stdout is not None:
            sys.stdout = _TeeTextStream(self._previous_stdout, self._record_console)
        builtins.input = self._recording_input
        self._active = True
        self._context_token = _ACTIVE_RECORDER.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._active:
            self._active = False
            import sys

            sys.stdout = self._previous_stdout
            builtins.input = self._previous_input
            self._previous_stdout = None
            self._previous_stdin = None
            self._previous_input = None
        if self._context_token is not None:
            _ACTIVE_RECORDER.reset(self._context_token)
            self._context_token = None
        return False

    def _recording_input(self, prompt: str = "") -> str:
        caller = inspect.currentframe().f_back
        if caller is not None and caller.f_code is _ASTCallProxy.__call__.__code__:
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


ASTTraceRecorder = TraceRecorder