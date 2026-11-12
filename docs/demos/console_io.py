"""Demonstrate captured input and output.

Run from the project root with:
    printf 'Ada\n3\n' | tracecode --auto-open docs/demos/console_io.py
"""


def main():
    name = input("Name: ")
    count = int(input("How many practice problems did you finish? "))
    print(f"{name} finished {count} practice problems.")


if __name__ == "__main__":
    main()
