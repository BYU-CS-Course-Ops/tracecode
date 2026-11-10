from tracecode import TraceRecorder


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
    for record in recorder.recording:
        print(record)  # i.e. the user does what they want with it


if __name__ == "__main__":
    main()
