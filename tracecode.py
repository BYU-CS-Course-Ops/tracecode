from types import TracebackType
from typing import Callable


class TraceRecorder:
    def __init__(self, serializers: list[tuple[type, Callable]] = None):
        self._serializers = serializers or []
        pass

    @property
    def recording(self):
        return None
        # Returns the ledger

    def __enter__(self):
        # Set trace
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None,
                 exc_tb: TracebackType | None):
        pass
        # Restore trace


def record_trace(func, *args, serializers=None, **kwargs):
    return result
