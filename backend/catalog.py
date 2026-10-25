
PRODUCTS = [
    {
        "id": "rice-5kg",
        "name": "Rice",
        "category": "Groceries",
        "brand": "Demo Brand",
        "variant": "5 kg bag",
        "unit": "bag",
        "base_price": 500.0,
        "image_url": "https://res.cloudinary.com/usvuq4si/image/upload/v1792883318/81Vu1q9QfJL._AC_UF894_1000_QL80_.jpg",
    },
    {
        "id": "oil-1l",
        "name": "Cooking Oil",
        "category": "Groceries",
        "brand": "Sunpure",
        "variant": "1 litre bottle",
        "unit": "bottle",
        "base_price": 150.0,
        "image_url": "https://res.cloudinary.com/usvuq4si/image/upload/v1792883473/Sunpure-Sunflower-Oil.jpg",
    },
    {
        "id": "detergent-1kg",
        "name": "Detergent",
        "category": "Cleaning",
        "brand": "Surf Excel",
        "variant": "1 kg pack",
        "unit": "pack",
        "base_price": 120.0,
        "image_url": "https://res.cloudinary.com/usvuq4si/image/upload/v1792883350/Surf-Excel-Easy-Wash-Detergent-Powder-1kg_19e3d4c6-54a2-45b4-a842-46239607e8c0.30282f979a091909b69d0aee322babf7.jpg",
    },
]


OFFERS = [
    {
        "id": "rice-demo",
        "product_id": "rice-5kg",
        "source": "demo",
        "supplier_name": None,
        "valid_until": None,
        "delivery_fee": 60.0,
        "other_fees": 20.0,
        "tiers": [
            {"min_qty": 1, "unit_price": 500.0},
            {"min_qty": 5, "unit_price": 475.0},
            {"min_qty": 10, "unit_price": 450.0},
        ],
    },
    {
        "id": "oil-demo",
        "product_id": "oil-1l",
        "source": "demo",
        "supplier_name": None,
        "valid_until": None,
        "delivery_fee": 40.0,
        "other_fees": 0.0,
        "tiers": [
            {"min_qty": 1, "unit_price": 150.0},
            {"min_qty": 6, "unit_price": 142.0},
            {"min_qty": 12, "unit_price": 135.0},
        ],
    },
    {
        "id": "detergent-demo",
        "product_id": "detergent-1kg",
        "source": "demo",
        "supplier_name": None,
        "valid_until": None,
        "delivery_fee": 40.0,
        "other_fees": 0.0,
        "tiers": [
            {"min_qty": 1, "unit_price": 120.0},
            {"min_qty": 5, "unit_price": 114.0},
            {"min_qty": 10, "unit_price": 108.0},
        ],
    },
]


def get_catalogue():
    return [
        {
            **product,
            "offers": [
                offer
                for offer in OFFERS
                if offer["product_id"] == product["id"]
            ],
        }
        for product in PRODUCTS
    ]
