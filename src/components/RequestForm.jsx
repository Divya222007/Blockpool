
import { useEffect, useState } from "react";
import "./RequestForms.css";

const API = "http://127.0.0.1:8000";

const PRODUCT_IMAGES = {
  "rice-5kg":
    "https://res.cloudinary.com/usvuq4si/image/upload/v1792883318/81Vu1q9QfJL._AC_UF894_1000_QL80_.jpg",

  "oil-1l":
    "https://res.cloudinary.com/usvuq4si/image/upload/v1792883473/Sunpure-Sunflower-Oil.jpg",

  "detergent-1kg":
    "https://res.cloudinary.com/usvuq4si/image/upload/v1792883350/Surf-Excel-Easy-Wash-Detergent-Powder-1kg_19e3d4c6-54a2-45b4-a842-46239607e8c0.30282f979a091909b69d0aee322babf7.jpg",
};

export default function RequestForm({ onOrderAdded }) {
  const [products, setProducts] = useState([]);
  const [resident, setResident] = useState("");
  const [quantities, setQuantities] = useState({});
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function loadProducts() {
      try {
        const response = await fetch(`${API}/api/catalog`);

        if (!response.ok) {
          throw new Error("Could not load the product catalogue.");
        }

        const data = await response.json();
        setProducts(data);
      } catch (error) {
        setMessage(
          error.message || "Could not connect to the BlockPool backend."
        );
      } finally {
        setLoading(false);
      }
    }

    loadProducts();
  }, []);

  function getPricing(product) {
    const offer = product.offers?.find(
      (item) => item.tiers?.length
    );

    if (!offer) return null;

    const tiers = [...offer.tiers].sort(
      (a, b) => a.min_qty - b.min_qty
    );

    return { offer, tiers };
  }

  async function submitOrders(event) {
    event.preventDefault();
    setMessage("");

    if (!resident.trim()) {
      setMessage("Please enter your name.");
      return;
    }

    const selectedProducts = products.filter(
      (product) => Number(quantities[product.id]) > 0
    );

    if (selectedProducts.length === 0) {
      setMessage("Please enter a quantity for at least one product.");
      return;
    }

    const hasInvalidQuantity = selectedProducts.some(
      (product) =>
        !Number.isInteger(Number(quantities[product.id])) ||
        Number(quantities[product.id]) > 10000
    );

    if (hasInvalidQuantity) {
      setMessage("Please enter whole-number quantities up to 10000.");
      return;
    }

    setSubmitting(true);

    try {
      for (const product of selectedProducts) {
        const response = await fetch(`${API}/api/requests`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            resident: resident.trim(),
            product_id: product.id,
            quantity: Number(quantities[product.id]),
          }),
        });

        if (!response.ok) {
          let errorMessage = "Order submission failed.";

          try {
            const error = await response.json();
            errorMessage = error.detail || errorMessage;
          } catch {
            // Use the fallback message.
          }

          throw new Error(errorMessage);
        }
      }

      setMessage("Shopping requests submitted successfully!");
      setQuantities({});

      if (onOrderAdded) {
        await onOrderAdded();
      }
    } catch (error) {
      setMessage(error.message || "Could not submit your shopping request.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <section className="bp-catalogue">
        <p className="bp-status">Loading products...</p>
      </section>
    );
  }

  return (
    <section className="bp-catalogue">
      <header className="bp-heading">
        <span className="bp-eyebrow">BLOCKPOOL MARKETPLACE</span>
        <h2>Shop Smarter, Together.</h2>
        <p>
          Combine household demand with neighbours to explore
          potential bulk-buying savings.
        </p>
      </header>

      {message && (
        <p className="bp-status" role="status" aria-live="polite">
          {message}
        </p>
      )}

      {products.length === 0 ? (
        <p>No products are available. Please check your backend.</p>
      ) : (
        <form onSubmit={submitOrders}>
          <div className="bp-resident">
            <label htmlFor="bp-resident-name">Resident name</label>
            <input
              id="bp-resident-name"
              type="text"
              value={resident}
              onChange={(event) => setResident(event.target.value)}
              placeholder="Enter your name"
              required
            />
          </div>

          <div className="bp-product-grid">
            {products.map((product) => {
              const pricing = getPricing(product);
              const imageUrl =
                PRODUCT_IMAGES[product.id] || product.image_url;

              return (
                <article className="bp-product-card" key={product.id}>
                  <div className="bp-image-box">
                    <img
                      src={imageUrl}
                      alt={product.name}
                      className="bp-product-image"
                      loading="eager"
                      onError={(event) => {
                        console.error(
                          `Could not load image for ${product.name}:`,
                          event.currentTarget.src
                        );
                        event.currentTarget.style.display = "none";
                        event.currentTarget.parentElement.classList.add(
                          "bp-image-failed"
                        );
                      }}
                      onLoad={(event) => {
                        event.currentTarget.parentElement.classList.remove(
                          "bp-image-failed"
                        );
                      }}
                    />
                    <span className="bp-image-fallback">
                      {product.name}
                    </span>
                  </div>

                  <div className="bp-product-content">
                    <span className="bp-category">
                      {product.category}
                    </span>

                    <h3>{product.name}</h3>
                    <p className="bp-description">
                      {product.brand} · {product.variant}
                    </p>

                    <p className="bp-base-price">
                      Individual price
                      <strong>₹{product.base_price}</strong>
                    </p>

                    {pricing && (
                      <div className="bp-bulk-box">
                        <h4>
                          {pricing.offer.source === "supplier"
                            ? "Supplier offer"
                            : "Illustrative bulk prices"}
                        </h4>

                        {pricing.tiers.map((tier) => (
                          <div
                            className="bp-price-row"
                            key={tier.min_qty}
                          >
                            <span>{tier.min_qty}+ units</span>
                            <strong>₹{tier.unit_price} each</strong>
                          </div>
                        ))}
                      </div>
                    )}

                    <label
                      className="bp-quantity-label"
                      htmlFor={`bp-qty-${product.id}`}
                    >
                      Quantity ({product.unit})
                    </label>

                    <input
                      id={`bp-qty-${product.id}`}
                      className="bp-quantity-input"
                      type="number"
                      min="0"
                      max="10000"
                      step="1"
                      value={quantities[product.id] ?? ""}
                      onChange={(event) =>
                        setQuantities((previous) => ({
                          ...previous,
                          [product.id]: event.target.value,
                        }))
                      }
                      placeholder="0"
                    />
                  </div>
                </article>
              );
            })}
          </div>

          <button
            className="bp-submit-button"
            type="submit"
            disabled={submitting}
          >
            {submitting ? "Submitting..." : "Submit Shopping Order"}
          </button>
        </form>
      )}

      <p className="bp-disclaimer">
        Demo prices are illustrative, not confirmed supplier quotes.
        No real payment is collected by this form.
      </p>
    </section>
  );
}
