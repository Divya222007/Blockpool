
from pooling import calculate_pooling

requests = [
    {
        "id": 1,
        "resident": "Ayesha",
        "product_id": "rice-5kg",
        "quantity": 3,
    },
    {
        "id": 2,
        "resident": "Gurukiran",
        "product_id": "rice-5kg",
        "quantity": 4,
    },
    {
        "id": 3,
        "resident": "Divya",
        "product_id": "rice-5kg",
        "quantity": 3,
    },
    {
        "id": 4,
        "resident": "Ayesha",
        "product_id": "oil-1l",
        "quantity": 2,
    },
]

result = calculate_pooling(requests)

for group in result["product_groups"]:
    print("\nProduct:", group["product_name"])
    print("Quantity:", group["total_quantity"])
    print("Bulk unit price:", group["unit_price_after"])
    print("Pooled total:", group["pooled_total"])
    print("Net savings:", group["net_savings"])
    print("Recommendation:", group["recommendation"])

print("\nTotal estimated savings:", result["total_savings"])

# Verify resident payments add up to the pooled total.
print("\nChecking resident payment allocations...")

for group in result["product_groups"]:
    allocated_total = round(
        sum(
            item["estimated_cost"]
            for item in group["allocations"]
        ),
        2,
    )

    pooled_total = group["pooled_total"]

    print(f'{group["product_name"]}:')
    print(f"  Pooled total: ₹{pooled_total:.2f}")
    print(f"  Resident payments: ₹{allocated_total:.2f}")

    assert allocated_total == pooled_total, (
        f'Payment mismatch for {group["product_name"]}'
    )

print("All payment allocation tests passed!")

