# tracecode

`tracecode` records the execution of a Python script and creates a standalone HTML viewer. It is intended for instructors who want to make a program's execution visible: learners can move through the trace and inspect the source, variable values, calls, and console output at each step.

## Installation

Requires Python 3.12 or later.

To install:

```sh
pip install tracecode
```

## Use

Run a script with the `tracecode` command:

```sh
tracecode --auto-open path/to/script.py
```

The HTML trace is written next to the script, with the same name and an `.html` extension. `--auto-open` opens it in a browser. Arguments after the script name are passed to the script:

```sh
tracecode path/to/script.py first-argument
```

## Features

- Step **forward** and **backward** through recorded execution snapshots.
- Highlight the active source line and call sites; inspect locals, callers, and function return values.
- Review `if`, `elif`, and `while` condition outcomes
- Review captured standard input and output.
- Inspect exceptions and their tracebacks as they propagate through the program.
- Share the generated standalone HTML file without installing a separate viewer.

The recorder traces the specified script file. Built-in values and common containers are displayed; other Python objects are shown as opaque values unless a custom serializer is supplied through the Python API.

## Demos

The `demos/` directory contains focused CLI examples and a combined walkthrough. Each command generates an HTML trace; run commands from the project root:

- [State and calls](demos/state_and_calls.py) — follow variable values through nested function calls and returns. Run with `tracecode --auto-open demos/state_and_calls.py`.
- [Conditions](demos/conditions.py) — inspect `if`/`elif` and `while` condition outcomes. Run with `tracecode --auto-open demos/conditions.py`.
- [Console I/O](demos/console_io.py) — review captured input and output. Run with `printf 'Ada\n3\n' | tracecode --auto-open demos/console_io.py`.
- [Exceptions](demos/exceptions.py) — follow a `ValueError` through nested calls and see it caught. Run with `printf 'not-a-number\n' | tracecode --auto-open demos/exceptions.py`.
- [Combined walkthrough](demos/walkthrough.py) — combines calls, changing values, conditions, a loop, console I/O, and a caught exception. Run with `printf '3\n90\n70\n50\nnot-a-number\n' | tracecode --auto-open demos/walkthrough.py`.
