# `tracecode`

This framework uses `settrace` to record the step-by-step play of a small Python program.

It produces a JSON recording of the program storing each line of executed code in the target file with the state changes made. 

These JSON recordings can be used to create a bidirectional replay of the program, allowing the user to step forward and backward to observe the state of the program.

This tool can be used for both educational and development purposes. 

It is simple and lightweight.