from pathlib import Path
import webbrowser

from tracecode import TraceRecorder, write_html_view


class CustomObj:
    def __init__(self, num):
        self._num = num

    def __repr__(self) -> str:
        return str(self._num)


def foo(num):
    return num + 1


def work():
    a = 7
    b = foo(7)
    c = CustomObj(a / b)
    print(a * b)
    print(c)


def main():
    recorder = TraceRecorder(
        [(CustomObj, lambda co: {"num": getattr(co, "_num", None)})]
    )
    with recorder:
        work()

    output_path = write_html_view(
        recorder.recording,
        Path(__file__).resolve().with_suffix(".html"),
    )
    webbrowser.open(output_path.resolve().as_uri())
    print(f"Trace viewer written to {output_path}")


if __name__ == "__main__":
    main()
