from __future__ import annotations

import argparse
import sys
import traceback
import types
from pathlib import Path

from .code_tracer import TraceRecorder
from .trace_viewer import write_html_view


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tracecode",
        description="Run a Python script, record its execution, and write an HTML viewer.",
    )
    parser.add_argument(
        "--auto-open",
        action="store_true",
        help="Open the generated HTML trace in a browser.",
    )
    parser.add_argument("script", help="Python script to run")
    parser.add_argument(
        "script_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to the script",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    script = Path(args.script).expanduser().resolve()
    if not script.is_file():
        parser.error(f"script is not a file: {script}")

    recorder = TraceRecorder(target_file=str(script))
    previous_argv = sys.argv
    previous_path = sys.path[:]
    sys.argv = [str(script), *args.script_args]
    sys.path.insert(0, str(script.parent))
    failure = None
    exit_code = 0
    script_module = types.ModuleType("__main__")
    script_module.__file__ = str(script)
    script_module.__cached__ = None
    script_module.__loader__ = None
    script_module.__package__ = None
    script_module.__spec__ = None
    had_main_module = "__main__" in sys.modules
    previous_main_module = sys.modules.get("__main__")
    try:
        sys.modules["__main__"] = script_module
        with recorder:
            recorder.exec_source(script_module.__dict__)
    except SystemExit as error:
        if isinstance(error.code, int):
            exit_code = error.code
        elif error.code is not None:
            print(error.code, file=sys.stderr)
            exit_code = 1
    except BaseException:
        failure = sys.exc_info()
        exit_code = 1
    finally:
        if had_main_module:
            sys.modules["__main__"] = previous_main_module
        else:
            sys.modules.pop("__main__", None)
        sys.argv = previous_argv
        sys.path[:] = previous_path

    output = script.with_suffix(".html")
    write_html_view(recorder.recording, output, auto_open=args.auto_open)
    print(f"Trace written to {output}")
    if failure is not None:
        traceback.print_exception(*failure)
    return exit_code
