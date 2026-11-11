"""Demonstrate how a traceback grows as an exception unwinds the stack."""

from pathlib import Path

from tracecode import TraceRecorder, write_html_view


def deepest_call():
    a = 7
    raise ValueError("This error is recorded as it unwinds.")


def middle_call():
    b = 8
    deepest_call()
    c = 9
    return b + c


def outer_call():
    a = 10
    d = middle_call()
    print('foo')


def main():
    recorder = TraceRecorder()
    with recorder:
        try:
            outer_call()
        except ValueError:
            # Catch the example error while the recorder still captures its full trace.
            pass

    write_html_view(
        recorder.recording,
        Path(__file__).resolve().with_suffix(".html"),
        auto_open=True,
    )


if __name__ == "__main__":
    main()
