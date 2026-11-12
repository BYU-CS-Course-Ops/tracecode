"""Demonstrate recorded if, elif, and while condition outcomes.

Run from the project root with:
    tracecode --auto-open demos/conditions.py
"""


def describe_temperature(temperature):
    if temperature < 0:
        description = "below freezing"
    elif temperature < 20:
        description = "cool"
    else:
        description = "warm"
    print(f"{temperature}°C is {description}.")


def count_down(start):
    while start > 0:
        print(start)
        start -= 1
    print("Go!")


def main():
    describe_temperature(12)
    count_down(2)


if __name__ == "__main__":
    main()
