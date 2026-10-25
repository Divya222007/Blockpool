
import { useCallback, useEffect, useState } from "react";
import "./App.css";

const API = "http://127.0.0.1:8000";

function App() {
  const [activePage, setActivePage] = useState("Dashboard");
  const [products, setProducts] = useState([]);
  const [requests, setRequests] = useState([]);
  const [showCheckout, setShowCheckout] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState("UPI");
  const [pooling, setPooling] = useState({
    product_groups: [],
    total_savings: 0,
  });

  // Bulk pool state
  const [pools, setPools] = useState([]);
  const [poolQuantities, setPoolQuantities] = useState({});
  const [deliveryAddresses, setDeliveryAddresses] = useState({});
  const [accessToken, setAccessToken] = useState("");
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginMessage, setLoginMessage] = useState("");
  const [joiningPoolId, setJoiningPoolId] = useState(null);

  // Existing shopping state
  const [resident, setResident] = useState("");
  const [quantities, setQuantities] = useState({});
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const [newProduct, setNewProduct] = useState({
    name: "",
    brand: "",
    variant: "",
    quantity: 1,
  });

  // Load catalogue, shopping requests, pooling calculations and available pools.
  const refreshData = useCallback(async () => {
    try {
      const [
        catalogResponse,
        requestsResponse,
        poolingResponse,
        poolsResponse,
      ] = await Promise.all([
        fetch(`${API}/api/catalog`),
        fetch(`${API}/api/requests`),
        fetch(`${API}/api/pooling`),
        fetch(`${API}/api/pools`),
      ]);

      if (
        !catalogResponse.ok ||
        !requestsResponse.ok ||
        !poolingResponse.ok ||
        !poolsResponse.ok
      ) {
        throw new Error("The BlockPool API returned an error.");
      }

      const catalogData = await catalogResponse.json();
      const requestsData = await requestsResponse.json();
      const poolingData = await poolingResponse.json();
      const poolsData = await poolsResponse.json();

      setProducts(Array.isArray(catalogData) ? catalogData : []);
      setRequests(Array.isArray(requestsData) ? requestsData : []);
      setPooling(poolingData || { product_groups: [], total_savings: 0 });

      setPools(
        Array.isArray(poolsData)
          ? poolsData
          : Array.isArray(poolsData.pools)
            ? poolsData.pools
            : []
      );

      setMessage("");
    } catch (error) {
      setMessage(
        "Cannot load BlockPool data. Check that the FastAPI backend is running on port 8000 and that the API endpoints are available."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshData();
  }, [refreshData]);

  // Existing shopping order submission.
  async function submitOrders(event) {
    event.preventDefault();
    setMessage("");

    if (!resident.trim()) {
      setMessage("Please enter your resident name.");
      return;
    }

    const selected = products.filter(
      (product) => Number(quantities[product.id]) > 0
    );

    if (selected.length === 0) {
      setMessage("Choose at least one product and quantity.");
      return;
    }

    setSubmitting(true);
    let submitted = 0;

    try {
      for (const product of selected) {
        const response = await fetch(`${API}/api/requests`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            resident: resident.trim(),
            product_id: product.id,
            quantity: Number(quantities[product.id]),
          }),
        });

        const result = await response.json();

        if (!response.ok) {
          throw new Error(result.detail || "Order submission failed.");
        }

        submitted++;
      }

      setQuantities({});
      setShowCheckout(false);
      await refreshData();
      setMessage(
        submitted === selected.length
          ? "Shopping order submitted successfully!"
          : `${submitted} product request(s) submitted. Please review the remaining items.`
      );
    } catch (error) {
      await refreshData();

      setMessage(
        submitted > 0
          ? `${submitted} item(s) were submitted before an error: ${error.message}`
          : error.message
      );
    } finally {
      setSubmitting(false);
    }
  }

  // Existing request for a product not in the catalogue.
  async function submitNewProduct(event) {
    event.preventDefault();
    setMessage("");

    if (!resident.trim()) {
      setMessage("Please enter your resident name first.");
      return;
    }

    try {
      const response = await fetch(`${API}/api/product-requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resident: resident.trim(),
          name: newProduct.name.trim(),
          brand: newProduct.brand.trim() || "Any",
          variant: newProduct.variant.trim(),
          quantity: Number(newProduct.quantity),
        }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || "Could not submit product request.");
      }

      setMessage("New product request submitted for review.");

      setNewProduct({
        name: "",
        brand: "",
        variant: "",
        quantity: 1,
      });
    } catch (error) {
      setMessage(error.message);
    }
  }

  // Login for buyers who want to join a bulk pool.
  async function loginBuyer(event) {
    event.preventDefault();
    setLoginMessage("");

    try {
      const response = await fetch(`${API}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: loginEmail.trim(),
          password: loginPassword,
        }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || "Login failed.");
      }

      if (!result.access_token) {
        throw new Error("Login succeeded, but no access token was returned.");
      }

      setAccessToken(result.access_token);
      setLoginPassword("");
      setLoginMessage("Login successful. You can now join an available pool.");
    } catch (error) {
      setAccessToken("");
      setLoginMessage(error.message);
    }
  }

  // Join a pool using the authenticated buyer's token.
  async function joinPool(poolId) {
    if (!accessToken) {
      setLoginMessage("Please log in with your buyer account first.");
      return;
    }

    const quantity = Number(poolQuantities[poolId]);
    const deliveryAddress = (deliveryAddresses[poolId] || "").trim();

    if (!Number.isInteger(quantity) || quantity <= 0) {
      setMessage("Enter a valid whole-number quantity.");
      return;
    }

    if (deliveryAddress.length < 5) {
      setMessage("Enter a complete delivery address.");
      return;
    }

    setJoiningPoolId(poolId);
    setMessage("");

    try {
      const response = await fetch(
        `${API}/api/pools/${encodeURIComponent(poolId)}/join`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({
            quantity,
            delivery_address: deliveryAddress,
          }),
        }
      );

      const result = await response.json();

      if (!response.ok) {
        if (response.status === 401) {
          setAccessToken("");
          throw new Error("Your login session is invalid or expired. Please log in again.");
        }

        if (response.status === 403) {
          throw new Error("Only an authorized buyer can join a pool.");
        }

        throw new Error(result.detail || "Could not join the pool.");
      }

      const estimatedTotal =
        result.estimated_total ??
        result.allocated_total ??
        result.total ??
        null;

      setMessage(
        estimatedTotal !== null
          ? `You joined the pool successfully. Estimated amount: ₹${Number(estimatedTotal).toFixed(2)}. Payment is not completed.`
          : "You joined the pool successfully. Payment is not completed."
      );

      setPoolQuantities((previous) => ({
        ...previous,
        [poolId]: "",
      }));

      await refreshData();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setJoiningPoolId(null);
    }
  }

  const totalQuantity = requests.reduce(
    (sum, request) => sum + Number(request.quantity || 0),
    0
  );

  const individualCost = (pooling.product_groups || []).reduce(
    (sum, group) => sum + Number(group.individual_total || 0),
    0
  );

  const pooledCost = (pooling.product_groups || []).reduce(
    (sum, group) => sum + Number(group.pooled_total || 0),
    0
  );

  const savings = Number(pooling.total_savings || 0);

  const pageItems = [
    ["Dashboard", "▦"],
    ["Shopping Requests", "🛒"],
    ["Demand Radar", "📊"],
    ["Group Orders", "📦"],
    ["Bulk Pools", "🤝"],
    ["Master Manifest", "📋"],
  ];

  return (
    <div className="app">
      <aside className="sidebar">
        <h2>🏘️ BlockPool</h2>
        <p className="side-label">APARTMENT COMMERCE</p>

        {pageItems.map(([page, icon]) => (
          <button
            key={page}
            className={`nav ${activePage === page ? "active" : ""}`}
            onClick={() => {
              setActivePage(page);
              setMessage("");
            }}
          >
            {icon} {page}
          </button>
        ))}

        <div className="sidebar-bottom">
          <div className="avatar">D</div>
          <div>
            <strong>Apartment Resident</strong>
            <small>Block A · Bengaluru</small>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">COMMUNITY PURCHASING PLATFORM</p>
            <h1>{activePage}</h1>
            <p className="muted">
              Buy together. Save together. Make every order count.
            </p>
          </div>

          <div className="apartment-badge">⌂ My Apartment</div>
        </header>

        {message && (
          <p className="api-message" role="status">
            {message}
          </p>
        )}

        {loading ? (
          <p>Loading BlockPool data...</p>
        ) : (
          <>
            <section className="stats">
              <div className="stat-card">
                <span>ACTIVE REQUESTS</span>
                <h2>{requests.length}</h2>
                <p>Submitted product requests</p>
              </div>

              <div className="stat-card">
                <span>COMBINED QUANTITY</span>
                <h2>{totalQuantity}</h2>
                <p>Across all product groups</p>
              </div>

              <div className="stat-card">
                <span>POTENTIAL SAVINGS</span>
                <h2 className={savings > 0 ? "green" : ""}>
                  ₹{savings.toFixed(2)}
                </h2>
                <p>Estimated using configured offers</p>
              </div>
            </section>

            {activePage === "Dashboard" && (
              <>
                <section className="welcome">
                  <div>
                    <p>YOUR COMMUNITY, YOUR SAVINGS</p>
                    <h2>Small orders. Smarter buying.</h2>
                    <span>
                      Combine compatible resident requests and discover
                      potential savings.
                    </span>
                  </div>
                  <div className="welcome-icon">🛍️</div>
                </section>

                <section className="content-grid">
                  <div className="panel">
                    <h3>Apartment Demand Radar</h3>
                    <p className="muted">
                      Current requests from all residents
                    </p>

                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>RESIDENT</th>
                            <th>PRODUCT</th>
                            <th>QUANTITY</th>
                          </tr>
                        </thead>

                        <tbody>
                          {requests.map((request) => {
                            const product = products.find(
                              (item) => item.id === request.product_id
                            );

                            return (
                              <tr key={request.id}>
                                <td>{request.resident}</td>
                                <td>{product?.name || request.product_id}</td>
                                <td>
                                  {request.quantity}{" "}
                                  {product?.unit || "units"}
                                </td>
                              </tr>
                            );
                          })}

                          {requests.length === 0 && (
                            <tr>
                              <td colSpan="3">No requests submitted yet.</td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>

                    <button
                      className="secondary-button"
                      onClick={refreshData}
                    >
                      Refresh demand
                    </button>
                  </div>

                  <div className="right-column">
                    <SavingsPanel
                      groups={pooling.product_groups || []}
                      individualCost={individualCost}
                      pooledCost={pooledCost}
                      savings={savings}
                    />
                  </div>
                </section>
              </>
            )}

            {activePage === "Shopping Requests" && (
              <section className="panel">
                <h3>Shop Products</h3>
                <p className="muted">
                  Select one product or several different products.
                </p>

               <form
  onSubmit={(event) => {
    event.preventDefault();
    setMessage("");

    if (!resident.trim()) {
      setMessage("Please enter your resident name.");
      return;
    }

    const selected = products.filter(
      (product) => Number(quantities[product.id]) > 0
    );

    if (selected.length === 0) {
      setMessage("Choose at least one product and quantity.");
      return;
    }

    alert("Checkout button handler reached!");
    setShowCheckout(true);
  }}
>
                  <label htmlFor="resident">Resident name</label>
                  <input
                    id="resident"
                    value={resident}
                    onChange={(event) => setResident(event.target.value)}
                    placeholder="Enter your name"
                    required
                  />

                  <div className="product-grid">
                    {products.map((product) => (
                      <article className="product-card" key={product.id}>
                        {product.image_url && (
  <div className="bp-product-image-container">
    <img
      src={product.image_url}
      alt={product.name}
      className="bp-product-image"
      onError={(event) => {
        event.currentTarget.style.display = "none";
      }}
    />
  </div>
)}

<h3>{product.name}</h3>

                        <p>
                          {product.brand} · {product.variant}
                        </p>
                        <p>Individual price: ₹{product.base_price}</p>

                        {product.offers?.map((offer) => (
                          <div className="bulk-offer" key={offer.id}>
                            <strong>
                              {offer.source === "supplier"
                                ? `Supplier offer${
                                    offer.supplier_name
                                      ? `: ${offer.supplier_name}`
                                      : ""
                                  }`
                                : "Demo bulk offer"}
                            </strong>

                            {offer.tiers.map((tier) => (
                              <p key={tier.min_qty}>
                                {tier.min_qty}+ {product.unit}(s): ₹
                                {tier.unit_price} each
                              </p>
                            ))}
                          </div>
                        ))}

                        <label htmlFor={`qty-${product.id}`}>
                          Quantity
                        </label>

                        <input
                          id={`qty-${product.id}`}
                          type="number"
                          min="0"
                          max="10000"
                          value={quantities[product.id] ?? ""}
                          onChange={(event) =>
                            setQuantities((previous) => ({
                              ...previous,
                              [product.id]: event.target.value,
                            }))
                          }
                          placeholder="0"
                        />
                      </article>
                    ))}
                  </div>

                  <button type="submit" disabled={submitting}>
                    {submitting ? "Submitting..." : "Submit Shopping Order"}
                  </button>
                </form>

                <div className="panel">
                  <h3>Request an unlisted product</h3>
                  <p className="muted">
                    New products are sent for review before being added to the
                    catalogue.
                  </p>

                  <form
                    className="request-form"
                    onSubmit={submitNewProduct}
                  >
                    <label htmlFor="new-name">Product name</label>
                    <input
                      id="new-name"
                      required
                      value={newProduct.name}
                      onChange={(event) =>
                        setNewProduct({
                          ...newProduct,
                          name: event.target.value,
                        })
                      }
                    />

                    <label htmlFor="new-brand">
                      Preferred brand (optional)
                    </label>
                    <input
                      id="new-brand"
                      value={newProduct.brand}
                      onChange={(event) =>
                        setNewProduct({
                          ...newProduct,
                          brand: event.target.value,
                        })
                      }
                    />

                    <label htmlFor="new-variant">
                      Package size / variant
                    </label>
                    <input
                      id="new-variant"
                      required
                      placeholder="e.g. 1 litre bottle"
                      value={newProduct.variant}
                      onChange={(event) =>
                        setNewProduct({
                          ...newProduct,
                          variant: event.target.value,
                        })
                      }
                    />

                    <label htmlFor="new-quantity">Quantity wanted</label>
                    <input
                      id="new-quantity"
                      type="number"
                      min="1"
                      max="10000"
                      required
                      value={newProduct.quantity}
                      onChange={(event) =>
                        setNewProduct({
                          ...newProduct,
                          quantity: event.target.value,
                        })
                      }
                    />

                    <button type="submit">Request New Product</button>
                  </form>
                </div>
              </section>
            )}

            {activePage === "Demand Radar" && (
              <section className="panel">
                <h3>Demand Radar</h3>

                {(pooling.product_groups || []).map((group) => (
                  <div className="cost-row" key={group.product_id}>
                    <span>
                      {group.product_name} · {group.total_quantity} units
                    </span>
                    <strong>{group.recommendation}</strong>
                  </div>
                ))}

                {(pooling.product_groups || []).length === 0 && (
                  <p>
                    No product demand yet. Submit a shopping request to begin.
                  </p>
                )}
              </section>
            )}

            {activePage === "Group Orders" && (
              <section className="panel">
                <h3>Group Orders</h3>

                {(pooling.product_groups || []).map((group) => (
                  <div className="group-order" key={group.product_id}>
                    <h4>{group.product_name}</h4>
                    <p>Total requested: {group.total_quantity} units</p>
                    <p>Bulk unit price: ₹{group.unit_price_after}</p>
                    <p>Estimated group total: ₹{group.pooled_total}</p>
                    <p>Recommendation: {group.recommendation}</p>
                  </div>
                ))}

                {(pooling.product_groups || []).length === 0 && (
                  <p>No grouped demand is available yet.</p>
                )}
              </section>
            )}

            {activePage === "Bulk Pools" && (
              <section className="panel">
                <h3>Bulk Pools</h3>
                <p className="muted">
                  BlockPool coordinates compatible buyer orders. Prices shown
                  here may be estimates until a supplier confirms them.
                </p>

                <div className="pool-login">
                  <h4>Buyer Login</h4>

                  <form className="request-form" onSubmit={loginBuyer}>
                    <label htmlFor="pool-login-email">Email</label>
                    <input
                      id="pool-login-email"
                      type="email"
                      autoComplete="username"
                      value={loginEmail}
                      onChange={(event) =>
                        setLoginEmail(event.target.value)
                      }
                      required
                    />

                    <label htmlFor="pool-login-password">Password</label>
                    <input
                      id="pool-login-password"
                      type="password"
                      autoComplete="current-password"
                      value={loginPassword}
                      onChange={(event) =>
                        setLoginPassword(event.target.value)
                      }
                      required
                    />

                    <button type="submit">Login as Buyer</button>
                  </form>

                  {loginMessage && (
                    <p role="status" className="muted">
                      {loginMessage}
                    </p>
                  )}

                  {accessToken && (
                    <p className="green">
                      Buyer account authenticated.
                    </p>
                  )}
                </div>

                <div className="pool-list">
                  {pools.length === 0 ? (
                    <p>
                      No pools are available yet. A seller or administrator
                      needs to create a pool first.
                    </p>
                  ) : (
                    pools.map((pool) => {
                      const poolId = pool.id ?? pool.pool_id;
                      const target = Number(pool.target_quantity || 0);
                      const collected = Number(
                        pool.total_quantity ??
                          pool.collected_quantity ??
                          pool.current_quantity ??
                          0
                      );

                      const calculatedProgress =
                        target > 0 ? (collected / target) * 100 : 0;

                      const progress = Math.max(
                        0,
                        Math.min(
                          100,
                          Number(
                            pool.progress_percent ?? calculatedProgress
                          )
                        )
                      );

                      const status = String(pool.status || "open").toLowerCase();
                      const isOpen = status === "open";
                      const bulkPrice = Number(pool.bulk_unit_price || 0);

                      return (
                        <article
                          className="group-order"
                          key={poolId}
                        >
                          <h3>
                            {pool.product_name || pool.product_id || "Bulk product"}
                          </h3>

                          <p>
                            Pool code:{" "}
                            {pool.pool_code || pool.code || poolId}
                          </p>

                          <p>
                            Pool type:{" "}
                            {pool.pooling_mode === "community"
                              ? "Community pool"
                              : "Area-wide pool"}
                          </p>

                          <p>
                            Location:{" "}
                            {pool.community_name ||
                              [
                                pool.city,
                                pool.pincode,
                              ]
                                .filter(Boolean)
                                .join(", ") ||
                              pool.delivery_area ||
                              "See pool details"}
                          </p>

                          <p>
                            Status: {pool.status || "open"}
                          </p>

                          <p>
                            Bulk price: ₹{bulkPrice.toFixed(2)} /{" "}
                            {pool.unit || "unit"}
                          </p>

                          <p>
                            Quantity collected: {collected} / {target}
                          </p>

                          <div
                            role="progressbar"
                            aria-label={`${pool.product_name || "Pool"} progress`}
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-valuenow={Math.round(progress)}
                            style={{
                              height: "10px",
                              background: "#e5e7eb",
                              borderRadius: "8px",
                              overflow: "hidden",
                            }}
                          >
                            <div
                              style={{
                                height: "100%",
                                width: `${progress}%`,
                                background: "#16a34a",
                                transition: "width 0.3s ease",
                              }}
                            />
                          </div>

                          <p>{progress.toFixed(0)}% of target reached</p>

                          <p>
                            Minimum quantity: {pool.minimum_quantity ?? 1}
                          </p>

                          {pool.deadline && (
                            <p>Deadline: {pool.deadline}</p>
                          )}

                          {isOpen && poolId != null && (
                            <form
                              className="request-form"
                              onSubmit={(event) => {
                                event.preventDefault();
                                joinPool(poolId);
                              }}
                            >
                              <label htmlFor={`pool-qty-${poolId}`}>
                                Your quantity
                              </label>

                              <input
                                id={`pool-qty-${poolId}`}
                                type="number"
                                min="1"
                                max="10000"
                                required
                                value={poolQuantities[poolId] ?? ""}
                                onChange={(event) =>
                                  setPoolQuantities((previous) => ({
                                    ...previous,
                                    [poolId]: event.target.value,
                                  }))
                                }
                              />

                              <label htmlFor={`pool-address-${poolId}`}>
                                Delivery address
                              </label>

                              <input
                                id={`pool-address-${poolId}`}
                                required
                                minLength="5"
                                value={deliveryAddresses[poolId] ?? ""}
                                onChange={(event) =>
                                  setDeliveryAddresses((previous) => ({
                                    ...previous,
                                    [poolId]: event.target.value,
                                  }))
                                }
                                placeholder="Enter your delivery address"
                              />

                              <button
                                type="submit"
                                disabled={joiningPoolId === poolId}
                              >
                                {joiningPoolId === poolId
                                  ? "Joining..."
                                  : "Join Pool"}
                              </button>
                            </form>
                          )}
                        </article>
                      );
                    })
                  )}
                </div>

                <button
                  type="button"
                  className="secondary-button"
                  onClick={refreshData}
                >
                  Refresh Pools
                </button>
              </section>
            )}

            {activePage === "Master Manifest" && (
              <section className="panel">
                <h3>Master Manifest</h3>
                <p className="muted">
                  Consolidated quantities for supplier preparation.
                </p>

                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>PRODUCT</th>
                        <th>UNIT</th>
                        <th>TOTAL QUANTITY</th>
                      </tr>
                    </thead>

                    <tbody>
                      {(pooling.product_groups || []).map((group) => {
                        const product = products.find(
                          (item) => item.id === group.product_id
                        );

                        return (
                          <tr key={group.product_id}>
                            <td>{group.product_name}</td>
                            <td>{product?.unit || "units"}</td>
                            <td>{group.total_quantity}</td>
                          </tr>
                        );
                      })}

                      {(pooling.product_groups || []).length === 0 && (
                        <tr>
                          <td colSpan="3">No grouped demand is available.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </section>
            )}
          </>
        )}

     {showCheckout && (
  <section className="panel">
    <h2>BlockPool Demo Checkout</h2>
    <p>Review your order before confirming.</p>

    {products
      .filter((product) => Number(quantities[product.id]) > 0)
      .map((product) => (
        <div className="cost-row" key={product.id}>
          <span>
            {product.name} × {Number(quantities[product.id])}
          </span>
          <strong>
            ₹
            {(
              Number(product.base_price || 0) *
              Number(quantities[product.id])
            ).toFixed(2)}
          </strong>
        </div>
      ))}

    <h3>
      Estimated subtotal: ₹
      {products
        .filter((product) => Number(quantities[product.id]) > 0)
        .reduce(
          (total, product) =>
            total +
            Number(product.base_price || 0) *
              Number(quantities[product.id]),
          0
        )
        .toFixed(2)}
    </h3>

    <p>Demo checkout only. No real payment will be taken.</p>

    <label htmlFor="demo-payment-method">
      Payment method
    </label>

    <select
      id="demo-payment-method"
      value={paymentMethod}
      onChange={(event) => setPaymentMethod(event.target.value)}
    >
      <option value="UPI">UPI (Demo)</option>
      <option value="Card">Card (Demo)</option>
      <option value="Pay on Delivery">Pay on Delivery (Demo)</option>
    </select>

    <div className="button-row">
      <button
        type="button"
        className="secondary-button"
        onClick={() => setShowCheckout(false)}
      >
        Back
      </button>

      <button
        type="button"
        disabled={submitting}
        onClick={() => submitOrders({ preventDefault: () => {} })}
      >
        {submitting ? "Processing..." : "Confirm Demo Order"}
      </button>
    </div>
  </section>
)}

        <footer>
          BlockPool · HackDays Prototype · Demo offers are not live supplier
          quotations
        </footer>
      </main>
    </div>
  );
}

function SavingsPanel({
  groups,
  individualCost,
  pooledCost,
  savings,
}) {
  return (
    <div className="panel savings-panel">
      <h3>💰 Savings Truth Engine</h3>
      <p className="muted">
        Calculated from the backend's configured offers
      </p>

      <div className="cost-row">
        <span>Individual product cost</span>
        <strong>₹{individualCost.toFixed(2)}</strong>
      </div>

      <div className="cost-row">
        <span>Pooled cost including fees</span>
        <strong>₹{pooledCost.toFixed(2)}</strong>
      </div>

      <div className="savings-result">
        <span>Estimated net difference</span>
        <h2 className={savings > 0 ? "green" : ""}>
          {savings < 0
            ? `-₹${Math.abs(savings).toFixed(2)}`
            : `₹${savings.toFixed(2)}`}
        </h2>
      </div>

      {groups.map((group) => (
        <div className="cost-row" key={group.product_id}>
          <span>
            {group.product_name}: {group.recommendation}
          </span>
          <strong>₹{group.unit_price_after}/unit</strong>
        </div>
      ))}

      <small>
        Estimates use configured offer tiers and fees. Confirm supplier prices
        and delivery terms before purchasing.
      </small>
    </div>
  );
}

export default App;
