"""Demonstrate a traceback as an exception unwinds and is caught.

Run from the project root with:
    printf 'not-a-number\n' | tracecode --auto-open docs/demos/exceptions.py
"""


def parse_count(text):
    return int(text)


def read_count():
    text = input("Enter a whole number: ")
    return parse_count(text)


def main():
    try:
        count = read_count()
        print(f"You entered {count}.")
    except ValueError as error:
        print(f"Could not read that number: {error}")


if __name__ == "__main__":
    main()
