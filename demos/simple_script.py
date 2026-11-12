"""A small example for tracing variables, function calls, and return values.

Run from the project root with:
    tracecode --auto-open demos/simple_script.py
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
        {"name": "Notebook", "price": 4.50, "quantity": 2},
        {"name": "Pencil", "price": 1.25, "quantity": 3},
    ]
    line_totals, subtotal = summarize_order(items)
    discount = 2.00
    total = subtotal - discount

    receipt = {
        "items": items,
        "line_totals": line_totals,
        "subtotal": subtotal,
        "discount": discount,
        "total": total,
    }

    print(f"Subtotal: ${receipt['subtotal']:.2f}")
    print(f"Discount: ${receipt['discount']:.2f}")
    print(f"Total:    ${receipt['total']:.2f}")


if __name__ == "__main__":
    main()
