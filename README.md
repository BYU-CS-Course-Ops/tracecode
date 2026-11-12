# tracecode

`tracecode` records the execution of a Python script to create a standalone HTML viewer. 

It is intended for instructors who want to make a program's execution visible: learners can move through the trace (forward and backward) to inspect the source, variable values, function calls, and console input/output at each step.

<need gif here>

Check out our [live, interactive demos](https://byu-cs-course-ops.github.io/tracecode/).

## Features

- Step **forward** and **backward** through recorded execution snapshots.
- Highlight the active source line and call sites; inspect locals, callers, and function return values.
- Review `if`, `elif`, and `while` condition outcomes
- Review captured standard input and output.
- Inspect exceptions and their tracebacks as they propagate through the program.
- Share the generated standalone HTML file without installing a separate viewer.

The recorder traces the specified script file. Built-in values and common containers are displayed; other Python objects are shown as opaque values unless a custom serializer is supplied through the Python API.

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


