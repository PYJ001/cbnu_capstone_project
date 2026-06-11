#utils.py

def pivot():
    if not hasattr(pivot, "count"):
        pivot.count = 0

    pivot.count += 1
    print(f"pivot{pivot.count}")

