"""Demonstrate changing values across function calls and returns.

Run from the project root with:
    tracecode --auto-open demos/state_and_calls.py
"""


def item_total(item):
    return item["price"] * item["quantity"]


def summarize_order(items):
    line_totals = []
    for item in items:
        line_totals.append(item_total(item))
    subtotal = sum(line_totals)
    return line_totals, subtotal


def main():
    items = [
        {"name": "Notebook", "price": 4, "quantity": 2},
        {"name": "Pencil", "price": 1, "quantity": 3},
    ]
    line_totals, subtotal = summarize_order(items)
    discount = 2
    total = subtotal - discount
    print(f"Subtotal: {subtotal}")
    print(f"Total: {total}")


if __name__ == "__main__":
    main()
