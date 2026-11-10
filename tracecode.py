from __future__ import annotations

import inspect
import os
import sys
from types import TracebackType
from typing import Any, Callable, Protocol


class Serializer(Protocol):
    def __call__(self, item: Any) -> Any: ...


class RecordingLimitExceeded(RuntimeError):
    """Raised when a recording exceeds a configured snapshot or value limit."""


class TraceRecorder:
    """Record line, return, and exception snapshots for one Python source file."""

    def __init__(
        self,
        serializers: list[tuple[type, Serializer]] | None = None,
        *,
        max_snapshots: int = 10_000,
        max_depth: int = 20,
        max_items: int = 10_000,
        target_file: str | None = None,
    ):
        if max_snapshots < 1 or max_depth < 0 or max_items < 1:
            raise ValueError("max_snapshots/max_items must be positive and max_depth non-negative")
        self._serializers = list(serializers or [])
        self._max_snapshots = max_snapshots
        self._max_depth = max_depth
        self._max_items = max_items
        self._target_file = os.path.realpath(target_file) if target_file else None
        self._previous_trace: Callable | None = None
        self._active = False
        self._recording: list[dict[str, Any]] = []

    @property
    def recording(self) -> list[dict[str, Any]]:
        return self._recording

    def __enter__(self) -> TraceRecorder:
        if self._active:
            raise RuntimeError("TraceRecorder is already active")
        if self._target_file is None:
            caller = inspect.currentframe().f_back
            if caller is None:
                raise RuntimeError("Cannot determine target source file")
            self._target_file = os.path.realpath(caller.f_code.co_filename)
        self._previous_trace = sys.gettrace()
        self._active = True
        sys.settrace(self._trace)
        return self

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
        self._active = False
        sys.settrace(self._previous_trace)

    def _trace(self, frame, event: str, arg):
        if not self._active:
            return None
        try:
            if os.path.realpath(frame.f_code.co_filename) != self._target_file:
                return self._trace
            if event in ("line", "return", "exception"):
                if len(self._recording) >= self._max_snapshots:
                    raise RecordingLimitExceeded(
                        f"Recording exceeded the {self._max_snapshots}-snapshot limit"
                    )
                self._recording.append(self._snapshot(frame, event, arg))
        except BaseException:
            self._stop_tracing()
            raise
        return self._trace

    def _snapshot(self, frame, event: str, arg) -> dict[str, Any]:
        budget = [0]
        snapshot: dict[str, Any] = {
            "event": event,
            "filename": frame.f_code.co_filename,
            "lineno": frame.f_lineno,
            "function": frame.f_code.co_name,
            "qualified_function": frame.f_code.co_qualname,
        }
        local_values = self._visible_values(frame.f_locals)
        if frame.f_code.co_name == "<module>":
            # At module scope locals and globals are the same mapping.
            snapshot["locals"] = self._serialize_scope(local_values, budget)
        else:
            snapshot["locals"] = self._serialize_scope(local_values, budget)
            snapshot["globals"] = self._serialize_scope(
                self._visible_values(frame.f_globals), budget
            )

        if event == "return":
            snapshot["return"] = {"value": self._serialize(arg, 0, budget)}
        elif event == "exception":
            _, exception, _ = arg
            snapshot["exception"] = {
                "type": self._type_name(exception),
                "args": self._serialize(exception.args, 0, budget),
            }
        return snapshot

    def _serialize_scope(self, values: dict[str, Any], budget: list[int]) -> dict[str, Any]:
        return {name: self._serialize(value, 0, budget) for name, value in values.items()}

    @staticmethod
    def _visible_values(values: dict[str, Any]) -> dict[str, Any]:
        return {
            name: value
            for name, value in values.items()
            if not (name.startswith("__") and name.endswith("__"))
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
