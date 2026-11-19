## 0.1.2

- `tracecode` now uses exclusively AST hooks instead of `settrace`; this resulted in a 20x speedup in runtime for code with calls to external libraries. 
- UI hooks for custom panels (used by the `byubit` project)
- Various UI refinements

## 0.1.1

Initial release!

Project on GitHub: [BYU-CS-Course-Ops/tracecode](https://github.com/BYU-CS-Course-Ops/tracecode)

Live demos: [tracecode GitHub Pages](https://byu-cs-course-ops.github.io/tracecode/)

`tracecode` records the execution of a Python script to create a standalone HTML viewer. 

It is intended for instructors who want to make a program's execution visible: learners can move through the trace (forward and backward) to inspect the source, variable values, function calls, and console input/output at each step.
