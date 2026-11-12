"""Combine state, calls, conditions, loops, console I/O, and exceptions.

Run from the project root with:
    printf '3\n90\n70\n50\nnot-a-number\n' | tracecode --auto-open docs/demos/walkthrough.py
"""


def average(total, count):
    return total / count


def label_for(score):
    if score >= 80:
        return "high"
    elif score >= 60:
        return "middle"
    else:
        return "low"


def main():
    count = int(input("How many scores? "))
    total = 0
    remaining = count

    while remaining > 0:
        score = int(input("Score: "))
        total += score
        remaining -= 1

    mean = average(total, count)
    try:
        bonus = int(input("Bonus points (integer): "))
    except ValueError as error:
        print(f"Invalid bonus ({error}); using 0.")
        bonus = 0

    final_score = mean + bonus
    label = label_for(final_score)
    print(f"Average: {mean:.1f}")
    print(f"Final score: {final_score:.1f} ({label})")


if __name__ == "__main__":
    main()
