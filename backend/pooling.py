
from catalog import PRODUCTS, OFFERS
from datetime import date


def calculate_pooling(requests):
    """Combine resident requests and calculate bulk prices and savings."""

    today = date.today().isoformat()
    product_map = {p["id"]: p for p in PRODUCTS}

    # Keep only offers within their validity dates.
    valid_offers = []
    for offer in OFFERS:
        if offer.get("valid_from") and today < offer["valid_from"]:
            continue
        if offer.get("valid_until") and today > offer["valid_until"]:
            continue
        valid_offers.append(offer)

    results = []

    for offer in valid_offers:
        product_id = offer["product_id"]
        product = product_map.get(product_id)

        if not product or product.get("active") is False:
            continue

        matching = [
            r for r in requests
            if r.get("product_id") == product_id
            and isinstance(r.get("quantity"), int)
            and not isinstance(r.get("quantity"), bool)
            and r["quantity"] > 0
        ]

        if not matching:
            continue

        total_quantity = sum(r["quantity"] for r in matching)

        tiers = sorted(
            offer["tiers"], key=lambda tier: tier["min_qty"]
        )
        eligible = [
            tier for tier in tiers
            if total_quantity >= tier["min_qty"]
        ]

        if not eligible:
            continue

        best_tier = eligible[-1]
        bulk_price = float(best_tier["unit_price"])
        base_price = float(product["base_price"])

        individual_product_cost = total_quantity * base_price
        pooled_product_cost = total_quantity * bulk_price

        delivery_fee = float(offer.get("delivery_fee", 0))
        other_fees = float(offer.get("other_fees", 0))

        # Demo assumption: every separate order pays the same fees.
        individual_total = (
            individual_product_cost
            + len(matching) * (delivery_fee + other_fees)
        )

        pooled_total = (
            pooled_product_cost + delivery_fee + other_fees
        )

        net_savings = individual_total - pooled_total

        # Allocate pooled fees proportionally by quantity.
        allocations = []
        allocated_so_far = 0.0

        for index, request in enumerate(matching):
            share = request["quantity"] / total_quantity

            if index < len(matching) - 1:
                allocated_cost = round(
                    request["quantity"] * bulk_price
                    + share * (delivery_fee + other_fees),
                    2,
                )
                allocated_so_far += allocated_cost
            else:
                # Assign rounding remainder to the last allocation.
                allocated_cost = round(
                    pooled_total - allocated_so_far, 2
                )

            allocations.append({
                "request_id": request.get("id"),
                "resident": request.get("resident", "Resident"),
                "quantity": request["quantity"],
                "estimated_cost": allocated_cost,
            })

        if net_savings > 0:
            recommendation = "POOL NOW"
        elif net_savings == 0:
            recommendation = "EITHER OPTION"
        else:
            recommendation = "BUY SEPARATELY"

        results.append({
            "product_id": product_id,
            "product_name": product["name"],
            "offer_source": offer.get("source", "demo"),
            "supplier_name": offer.get("supplier_name"),
            "total_quantity": total_quantity,
            "unit_price_before": round(base_price, 2),
            "unit_price_after": round(bulk_price, 2),
            "individual_product_cost": round(
                individual_product_cost, 2
            ),
            "pooled_product_cost": round(pooled_product_cost, 2),
            "delivery_fee": round(delivery_fee, 2),
            "other_fees": round(other_fees, 2),
            "individual_total": round(individual_total, 2),
            "pooled_total": round(pooled_total, 2),
            "net_savings": round(net_savings, 2),
            "recommendation": recommendation,
            "allocations": allocations,
        })

    return {
        "product_groups": results,
        "total_savings": round(
            sum(item["net_savings"] for item in results), 2
        ),
    }
