
import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from catalog import get_catalogue, PRODUCTS
from pooling import calculate_pooling
from database import (
    initialize_database,
    get_connection,
    get_shopping_requests,
    add_shopping_request,
    get_product_requests,
    add_product_request,
)

app = FastAPI(title="BlockPool API")

security = HTTPBearer(auto_error=False)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://blockpool-git-main-logicfoundry.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Sessions are stored as hashes, not raw bearer tokens.
with get_connection() as connection:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS auth_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)


# ---------- Password and authentication helpers ----------

def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, 310000
    )
    return salt.hex() + ":" + digest.hex()


def verify_password(password, stored):
    try:
        salt_hex, digest_hex = stored.split(":")
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), 310000
        )
      
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def public_user(row):
    user = dict(row)
    user.pop("password_hash", None)
    return user


def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    if credentials is None:
        raise HTTPException(401, "Please log in first")

    token_hash = hashlib.sha256(
        credentials.credentials.encode()
    ).hexdigest()

    with get_connection() as connection:
        row = connection.execute("""
            SELECT users.*
            FROM auth_sessions
            JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.token_hash = ?
              AND auth_sessions.expires_at > ?
              AND users.is_active = 1
        """, (
            token_hash,
            datetime.now(timezone.utc).isoformat(),
        )).fetchone()

    if row is None:
        raise HTTPException(401, "Session expired or invalid")

    return dict(row)


def require_role(user, *roles):
    if user["role"] not in roles:
        raise HTTPException(403, "You do not have permission for this action")


def create_session(user_id):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires = (
        datetime.now(timezone.utc) + timedelta(hours=12)
    ).isoformat()

    with get_connection() as connection:
        connection.execute("""
            INSERT INTO auth_sessions (token_hash, user_id, expires_at)
            VALUES (?, ?, ?)
        """, (token_hash, user_id, expires))

    return token


# ---------- Request models ----------

class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    role: str
    phone: str | None = Field(default=None, max_length=20)
    apartment_name: str | None = Field(default=None, max_length=120)
    block_tower: str | None = Field(default=None, max_length=50)
    flat_number: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=10)


class LoginRequest(BaseModel):
    email: str
    password: str


class ShoppingRequest(BaseModel):
    resident: str = Field(min_length=1, max_length=80)
    product_id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0, le=10000)


class NewProductRequest(BaseModel):
    resident: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    brand: str = Field(default="Any", max_length=80)
    variant: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0, le=10000)


class SellerProductRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str | None = None
    description: str | None = None
    unit: str = Field(default="unit", max_length=30)
    price: float = Field(ge=0)
    available_quantity: int = Field(ge=0)
    minimum_bulk_quantity: int = Field(default=1, gt=0)


class CheckoutItem(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=10000)


class CheckoutRequest(BaseModel):
    items: list[CheckoutItem] = Field(min_length=1, max_length=100)
    delivery_address: str = Field(min_length=5, max_length=500)
    payment_method: str = Field(default="test", max_length=30)


class AgentAvailability(BaseModel):
    available: bool


class AgentAssignmentRequest(BaseModel):
    agent_id: int


class DeliveryUpdate(BaseModel):
    status: str
    note: str | None = Field(default=None, max_length=300)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    estimated_arrival: datetime | None = None

class CreatePoolRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=100)
    product_name: str = Field(min_length=1, max_length=120)
    pooling_mode: str
    community_name: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=10)
    unit: str = Field(default="unit", max_length=30)
    base_price: float = Field(gt=0)
    bulk_unit_price: float = Field(gt=0)
    minimum_quantity: int = Field(default=1, gt=0, le=100000)
    target_quantity: int = Field(gt=0, le=100000)
    deadline: str | None = Field(default=None, max_length=50)


class JoinPoolRequest(BaseModel):
    quantity: int = Field(gt=0, le=10000)
    delivery_address: str = Field(min_length=5, max_length=500)


# ---------- Basic and existing endpoints ----------

@app.get("/")
def home():
    return {
        "message": "BlockPool API is running",
        "status": "success",
    }


@app.get("/api/catalog")
def get_products():
    return get_catalogue()


@app.get("/api/requests")
def get_requests():
    return get_shopping_requests()

# ---------- BlockPool bulk-pooling APIs ----------

def get_pool_progress(connection, pool_id):
    row = connection.execute("""
        SELECT COALESCE(SUM(quantity), 0) AS total_quantity,
               COUNT(*) AS member_count
        FROM bulk_pool_members
        WHERE pool_id = ? AND status IN ('joined', 'confirmed')
    """, (pool_id,)).fetchone()

    return dict(row)


@app.post("/api/pools")
def create_bulk_pool(
    request: CreatePoolRequest,
    user=Depends(current_user),
):
    # Sellers can submit supplier offers for BlockPool to coordinate.
    # Admins can also create pools.
    require_role(user, "seller", "admin")

    mode = request.pooling_mode.strip().lower()

    if mode not in ("community", "area"):
        raise HTTPException(
            422, "pooling_mode must be 'community' or 'area'"
        )

    if request.bulk_unit_price > request.base_price:
        raise HTTPException(
            422, "Bulk price cannot exceed the base price"
        )

    if request.target_quantity < request.minimum_quantity:
        raise HTTPException(
            422, "Target quantity must be at least the minimum quantity"
        )

    if mode == "community":
        if not request.community_name or not request.community_name.strip():
            raise HTTPException(
                422, "Community pools require a community name"
            )

        delivery_area = request.community_name.strip().casefold()

    else:
        if not request.city or not request.city.strip() or not request.pincode:
            raise HTTPException(
                422, "Area-wide pools require a city and PIN code"
            )

        delivery_area = (
            request.city.strip().casefold()
            + "|"
            + request.pincode.strip()
        )

    pool_code = "BP-" + secrets.token_hex(4).upper()

    with get_connection() as connection:
        supplier_name = (
            user["full_name"] if user["role"] == "seller" else None
        )
        supplier_id = (
            user["id"] if user["role"] == "seller" else None
        )

        cursor = connection.execute("""
            INSERT INTO bulk_pools (
                pool_code, product_id, product_name,
                supplier_id, supplier_name, delivery_area,
                pooling_mode, unit, base_price, bulk_unit_price,
                minimum_quantity, target_quantity, deadline, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """, (
            pool_code,
            request.product_id.strip(),
            request.product_name.strip(),
            supplier_id,
            supplier_name,
            delivery_area,
            mode,
            request.unit.strip(),
            request.base_price,
            request.bulk_unit_price,
            request.minimum_quantity,
            request.target_quantity,
            request.deadline,
        ))

        pool_id = cursor.lastrowid

    return {
        "message": "Pool created for buyer participation",
        "pool_id": pool_id,
        "pool_code": pool_code,
        "pooling_mode": mode,
        "delivery_area": delivery_area,
        "status": "open",
        "note": "Supplier availability and pricing must be confirmed before procurement."
    }


@app.get("/api/pools")
def list_bulk_pools():
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT p.*,
                   COALESCE(m.total_quantity, 0) AS total_quantity,
                   COALESCE(m.member_count, 0) AS member_count
            FROM bulk_pools p
            LEFT JOIN (
                SELECT pool_id,
                       SUM(quantity) AS total_quantity,
                       COUNT(*) AS member_count
                FROM bulk_pool_members
                WHERE status IN ('joined', 'confirmed')
                GROUP BY pool_id
            ) m ON m.pool_id = p.id
            WHERE p.status IN ('open', 'target_reached')
            ORDER BY p.created_at DESC
        """).fetchall()

    result = []

    for row in rows:
        pool = dict(row)
        target = pool["target_quantity"]
        total = pool["total_quantity"]

        pool["quantity_remaining"] = max(0, target - total)
        pool["progress_percent"] = round(
            min(100, total * 100 / target), 1
        ) if target > 0 else 0

        result.append(pool)

    return result


@app.get("/api/pools/{pool_id}")
def get_bulk_pool(pool_id: int):
    with get_connection() as connection:
        row = connection.execute("""
            SELECT p.*,
                   COALESCE(m.total_quantity, 0) AS total_quantity,
                   COALESCE(m.member_count, 0) AS member_count
            FROM bulk_pools p
            LEFT JOIN (
                SELECT pool_id,
                       SUM(quantity) AS total_quantity,
                       COUNT(*) AS member_count
                FROM bulk_pool_members
                WHERE status IN ('joined', 'confirmed')
                GROUP BY pool_id
            ) m ON m.pool_id = p.id
            WHERE p.id = ?
        """, (pool_id,)).fetchone()

        if row is None:
            raise HTTPException(404, "Pool not found")

        pool = dict(row)
        target = pool["target_quantity"]
        total = pool["total_quantity"]

        pool["quantity_remaining"] = max(0, target - total)
        pool["progress_percent"] = round(
            min(100, total * 100 / target), 1
        ) if target > 0 else 0

        return pool


@app.post("/api/pools/{pool_id}/join")
def join_bulk_pool(
    pool_id: int,
    request: JoinPoolRequest,
    user=Depends(current_user),
):
    require_role(user, "buyer")

    address = request.delivery_address.strip()

    if not address:
        raise HTTPException(422, "Delivery address cannot be empty")

    with get_connection() as connection:
        pool = connection.execute("""
            SELECT * FROM bulk_pools WHERE id = ?
        """, (pool_id,)).fetchone()

        if pool is None:
            raise HTTPException(404, "Pool not found")

        if pool["status"] != "open":
            raise HTTPException(400, "This pool is not accepting members")

        if pool["pooling_mode"] == "community":
            buyer_area = (user.get("apartment_name") or "").strip().casefold()

            if not buyer_area or buyer_area != pool["delivery_area"]:
                raise HTTPException(
                    403,
                    "This community pool is only available to buyers "
                    "from the matching apartment community"
                )

        else:
            buyer_city = (user.get("city") or "").strip().casefold()
            buyer_pincode = (user.get("pincode") or "").strip()
            buyer_area = buyer_city + "|" + buyer_pincode

            if buyer_area != pool["delivery_area"]:
                raise HTTPException(
                    403,
                    "This area-wide pool is only available to buyers "
                    "in the matching city and PIN code"
                )

        existing = connection.execute("""
            SELECT id, status
            FROM bulk_pool_members
            WHERE pool_id = ? AND buyer_id = ?
        """, (pool_id, user["id"])).fetchone()

        if existing and existing["status"] != "cancelled":
            raise HTTPException(
                409,
                "You have already joined this pool"
            )

        current = get_pool_progress(connection, pool_id)
        new_total = current["total_quantity"] + request.quantity

        if new_total > pool["target_quantity"]:
            raise HTTPException(
                400,
                f"Only {max(0, pool['target_quantity'] - current['total_quantity'])} "
                "units remain in this pool"
            )

        unit_price = float(pool["bulk_unit_price"])
        allocated_total = round(request.quantity * unit_price, 2)

        if existing:
            connection.execute("""
                UPDATE bulk_pool_members
                SET quantity = ?, delivery_address = ?,
                    unit_price = ?, allocated_total = ?,
                    status = 'joined',
                    created_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                request.quantity, address, unit_price,
                allocated_total, existing["id"],
            ))
        else:
            connection.execute("""
                INSERT INTO bulk_pool_members (
                    pool_id, buyer_id, quantity, delivery_address,
                    unit_price, allocated_total, status
                ) VALUES (?, ?, ?, ?, ?, ?, 'joined')
            """, (
                pool_id, user["id"], request.quantity,
                address, unit_price, allocated_total,
            ))

        new_status = (
            "target_reached"
            if new_total >= pool["target_quantity"]
            else "open"
        )

        connection.execute("""
            UPDATE bulk_pools SET status = ? WHERE id = ?
        """, (new_status, pool_id))

    return {
        "message": "You joined the BlockPool successfully",
        "pool_id": pool_id,
        "quantity": request.quantity,
        "unit_price": unit_price,
        "estimated_total": allocated_total,
        "pool_quantity": new_total,
        "target_quantity": pool["target_quantity"],
        "pool_status": new_status,
        "payment_status": "not_started",
        "note": "This is a participation estimate, not a completed purchase or payment."
    }


@app.get("/api/my-pools")
def my_bulk_pools(user=Depends(current_user)):
    require_role(user, "buyer")

    with get_connection() as connection:
        rows = connection.execute("""
            SELECT m.id AS membership_id,
                   m.pool_id, m.quantity, m.delivery_address,
                   m.unit_price, m.allocated_total, m.status AS member_status,
                   p.pool_code, p.product_name, p.pooling_mode,
                   p.delivery_area, p.target_quantity, p.status AS pool_status
            FROM bulk_pool_members m
            JOIN bulk_pools p ON p.id = m.pool_id
            WHERE m.buyer_id = ?
            ORDER BY m.created_at DESC
        """, (user["id"],)).fetchall()

    return [dict(row) for row in rows]



@app.post("/api/requests")
def add_request(request: ShoppingRequest):
    resident = request.resident.strip()
    product = next(
        (p for p in PRODUCTS if p["id"] == request.product_id),
        None,
    )

    if not resident:
        raise HTTPException(422, "Resident name cannot be empty")
    if not product:
        raise HTTPException(404, "Product not found in catalogue")
    if not product.get("active", True):
        raise HTTPException(400, "Product is not currently available")

    result = add_shopping_request(
        resident, request.product_id, request.quantity
    )
    return {"message": "Shopping request added", "request": result}


@app.get("/api/pooling")
def get_pooling():
    return calculate_pooling(get_shopping_requests())


@app.post("/api/product-requests")
def request_new_product(request: NewProductRequest):
    resident = request.resident.strip()
    name = request.name.strip()
    variant = request.variant.strip()

    if not resident or not name or not variant:
        raise HTTPException(
            422, "Resident, product name, and variant cannot be empty"
        )

    result = add_product_request(
        resident, name, request.brand.strip() or "Any",
        variant, request.quantity
    )
    return {
        "message": "Product request submitted for review",
        "product_request": result,
    }


@app.get("/api/product-requests")
def get_product_request_list():
    return get_product_requests()


# ---------- Registration, login, logout ----------


@app.post("/api/auth/register")
def register(request: RegisterRequest):
    name = request.full_name.strip()
    email = request.email.strip().lower()
    role = request.role.strip().lower()

    if role not in ("buyer", "seller", "agent"):
        raise HTTPException(
            422,
            "Choose buyer, seller, or agent. Admin accounts must be created securely."
        )

    if not name or "@" not in email:
        raise HTTPException(422, "Enter a valid name and email")

    if role == "buyer" and not all([
        request.apartment_name,
        request.flat_number,
        request.address,
        request.city,
        request.pincode
    ]):
        raise HTTPException(
            422,
            "Buyers must provide apartment, flat, address, city, and PIN code"
        )

    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()

        if existing:
            raise HTTPException(
                409, "An account with this email already exists"
            )

        cursor = connection.execute("""
            INSERT INTO users (
                full_name, email, phone, password_hash, role,
                apartment_name, block_tower, flat_number,
                address, city, pincode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name,
            email,
            request.phone,
            hash_password(request.password),
            role,
            request.apartment_name,
            request.block_tower,
            request.flat_number,
            request.address,
            request.city,
            request.pincode,
        ))

        user_id = cursor.lastrowid

    return {
        "message": "Registration successful. Please log in.",
        "user_id": user_id,
        "role": role,
    }

@app.post("/api/auth/login")
def login(request: LoginRequest):
    email = request.email.strip().lower()

    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()

    if row is None or not verify_password(
        request.password, row["password_hash"]
    ):
        raise HTTPException(401, "Invalid email or password")

    if not row["is_active"]:
        raise HTTPException(403, "This account is disabled")

    token = create_session(row["id"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": public_user(row),
    }


@app.post("/api/auth/logout")
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    if credentials is None:
        raise HTTPException(401, "Please log in first")

    token_hash = hashlib.sha256(
        credentials.credentials.encode()
    ).hexdigest()

    with get_connection() as connection:
        connection.execute(
            "DELETE FROM auth_sessions WHERE token_hash = ?",
            (token_hash,),
        )

    return {"message": "Logged out"}


@app.get("/api/auth/me")
def get_my_profile(user=Depends(current_user)):
    return public_user(user)


# ---------- Seller/farmer portal ----------

@app.post("/api/seller/products")
def create_seller_product(
    request: SellerProductRequest,
    user=Depends(current_user),
):
    require_role(user, "seller")

    with get_connection() as connection:
        cursor = connection.execute("""
            INSERT INTO seller_products (
                seller_id, name, category, description, unit,
                price, available_quantity, minimum_bulk_quantity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user["id"], request.name.strip(), request.category,
            request.description, request.unit, request.price,
            request.available_quantity, request.minimum_bulk_quantity,
        ))

    return {
        "message": "Product listed",
        "product_id": cursor.lastrowid,
    }


@app.get("/api/marketplace")
def marketplace():
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT p.id, p.name, p.category, p.description, p.unit,
                   p.price, p.available_quantity, p.minimum_bulk_quantity,
                   u.full_name AS seller_name
            FROM seller_products p
            JOIN users u ON u.id = p.seller_id
            WHERE p.is_active = 1
              AND p.available_quantity > 0
              AND u.is_active = 1
            ORDER BY p.name
        """).fetchall()

    return [dict(row) for row in rows]


@app.get("/api/seller/orders")
def seller_orders(user=Depends(current_user)):
    require_role(user, "seller")

    with get_connection() as connection:
        rows = connection.execute("""
            SELECT oi.*, o.order_status, o.created_at, o.delivery_address
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            WHERE oi.seller_id = ?
            ORDER BY o.id DESC
        """, (user["id"],)).fetchall()

    return [dict(row) for row in rows]


# ---------- Buyer checkout and order history ----------

@app.post("/api/orders")
def checkout(
    request: CheckoutRequest,
    user=Depends(current_user),
):
    require_role(user, "buyer")

    # Prototype checkout: creates an order with payment pending.
    # A real payment gateway must confirm payment separately.
    with get_connection() as connection:
        prepared_items = []
        total = 0.0

        for item in request.items:
            product = connection.execute("""
                SELECT * FROM seller_products
                WHERE id = ? AND is_active = 1
            """, (item.product_id,)).fetchone()

            if product is None:
                raise HTTPException(
                    404, f"Seller product {item.product_id} not found"
                )

            if product["available_quantity"] < item.quantity:
                raise HTTPException(
                    400, f"Not enough stock for {product['name']}"
                )

            if item.quantity < product["minimum_bulk_quantity"]:
                raise HTTPException(
                    400,
                    f"{product['name']} requires a minimum quantity of "
                    f"{product['minimum_bulk_quantity']}"
                )

            line_total = product["price"] * item.quantity
            total += line_total
            prepared_items.append((product, item.quantity))

        cursor = connection.execute("""
            INSERT INTO orders (
                buyer_id, total_amount, payment_method, delivery_address
            ) VALUES (?, ?, ?, ?)
        """, (
            user["id"], round(total, 2), request.payment_method,
            request.delivery_address.strip(),
        ))
        order_id = cursor.lastrowid

        for product, quantity in prepared_items:
            connection.execute("""
                INSERT INTO order_items (
                    order_id, product_id, product_name, seller_id,
                    quantity, unit_price
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                order_id, product["id"], product["name"],
                product["seller_id"], quantity, product["price"],
            ))

            connection.execute("""
                UPDATE seller_products
                SET available_quantity = available_quantity - ?
                WHERE id = ?
            """, (quantity, product["id"]))

        connection.execute("""
            INSERT INTO delivery_assignments (order_id)
            VALUES (?)
        """, (order_id,))

    return {
        "message": "Order created; payment is pending",
        "order_id": order_id,
        "total_amount": round(total, 2),
        "payment_status": "pending",
    }


@app.get("/api/orders")
def buyer_orders(user=Depends(current_user)):
    require_role(user, "buyer")

    with get_connection() as connection:
        rows = connection.execute("""
            SELECT o.*, d.agent_id, d.status AS delivery_status,
                   d.estimated_arrival
            FROM orders o
            LEFT JOIN delivery_assignments d ON d.order_id = o.id
            WHERE o.buyer_id = ?
            ORDER BY o.id DESC
        """, (user["id"],)).fetchall()

    return [dict(row) for row in rows]


# ---------- Delivery agent portal ----------

@app.post("/api/agent/availability")
def set_agent_availability(
    request: AgentAvailability,
    user=Depends(current_user),
):
    require_role(user, "agent")

    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS agent_availability (
                agent_id INTEGER PRIMARY KEY,
                available INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (agent_id) REFERENCES users(id)
            )
        """)
        connection.execute("""
            INSERT INTO agent_availability (agent_id, available)
            VALUES (?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                available = excluded.available,
                updated_at = CURRENT_TIMESTAMP
        """, (user["id"], int(request.available)))

    return {"available": request.available}


@app.get("/api/agent/deliveries")
def agent_deliveries(user=Depends(current_user)):
    require_role(user, "agent")

    with get_connection() as connection:
        rows = connection.execute("""
            SELECT d.*, o.delivery_address, o.total_amount, o.order_status
            FROM delivery_assignments d
            JOIN orders o ON o.id = d.order_id
            WHERE d.agent_id = ?
            ORDER BY d.id DESC
        """, (user["id"],)).fetchall()

    return [dict(row) for row in rows]


@app.get("/api/agent/jobs")
def available_delivery_jobs(user=Depends(current_user)):
    require_role(user, "agent")

    with get_connection() as connection:
        rows = connection.execute("""
            SELECT d.id AS assignment_id, d.order_id,
                   o.delivery_address, o.total_amount, d.status
            FROM delivery_assignments d
            JOIN orders o ON o.id = d.order_id
            WHERE d.agent_id IS NULL AND d.status = 'pending'
            ORDER BY d.id
        """).fetchall()

    return [dict(row) for row in rows]


@app.post("/api/agent/jobs/{assignment_id}/accept")
def accept_delivery(
    assignment_id: int,
    user=Depends(current_user),
):
    require_role(user, "agent")

    with get_connection() as connection:
        available = connection.execute("""
            SELECT available FROM agent_availability
            WHERE agent_id = ?
        """, (user["id"],)).fetchone()

        if available is None or not available["available"]:
            raise HTTPException(
                400, "Set yourself as available before accepting a delivery"
            )

        cursor = connection.execute("""
            UPDATE delivery_assignments
            SET agent_id = ?, assignment_method = 'self_accept',
                status = 'accepted', updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND agent_id IS NULL AND status = 'pending'
        """, (user["id"], assignment_id))

        if cursor.rowcount == 0:
            raise HTTPException(409, "This delivery is no longer available")

        connection.execute("""
            INSERT INTO tracking_events (assignment_id, status, note)
            VALUES (?, 'accepted', 'Accepted by delivery agent')
        """, (assignment_id,))

    return {"message": "Delivery accepted", "assignment_id": assignment_id}


# ---------- Admin delivery management ----------

@app.get("/api/admin/agents")
def list_agents(user=Depends(current_user)):
    require_role(user, "admin")

    with get_connection() as connection:
        rows = connection.execute("""
            SELECT u.id, u.full_name, u.phone,
                   COALESCE(a.available, 0) AS available
            FROM users u
            LEFT JOIN agent_availability a ON a.agent_id = u.id
            WHERE u.role = 'agent' AND u.is_active = 1
            ORDER BY u.full_name
        """).fetchall()

    return [dict(row) for row in rows]


@app.post("/api/admin/deliveries/{assignment_id}/assign")
def admin_assign_delivery(
    assignment_id: int,
    request: AgentAssignmentRequest,
    user=Depends(current_user),
):
    require_role(user, "admin")

    with get_connection() as connection:
        agent = connection.execute("""
            SELECT id FROM users
            WHERE id = ? AND role = 'agent' AND is_active = 1
        """, (request.agent_id,)).fetchone()

        if agent is None:
            raise HTTPException(404, "Active delivery agent not found")

        assignment = connection.execute("""
            SELECT * FROM delivery_assignments WHERE id = ?
        """, (assignment_id,)).fetchone()

        if assignment is None:
            raise HTTPException(404, "Delivery assignment not found")

        if assignment["status"] in ("delivered", "cancelled"):
            raise HTTPException(400, "This delivery is already closed")

        connection.execute("""
            UPDATE delivery_assignments
            SET agent_id = ?, assigned_by = ?,
                assignment_method = 'admin', status = 'assigned',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (request.agent_id, user["id"], assignment_id))

        connection.execute("""
            INSERT INTO tracking_events (assignment_id, status, note)
            VALUES (?, 'assigned', ?)
        """, (assignment_id, f"Assigned by admin to agent {request.agent_id}"))

    return {
        "message": "Delivery assigned",
        "assignment_id": assignment_id,
        "agent_id": request.agent_id,
    }


@app.post("/api/admin/deliveries/auto-assign")
def auto_assign_delivery(user=Depends(current_user)):
    require_role(user, "admin")

    assigned = []

    with get_connection() as connection:
        jobs = connection.execute("""
            SELECT id FROM delivery_assignments
            WHERE agent_id IS NULL AND status = 'pending'
            ORDER BY id
        """).fetchall()

        for job in jobs:
            agent = connection.execute("""
                SELECT u.id
                FROM users u
                JOIN agent_availability a ON a.agent_id = u.id
                WHERE u.role = 'agent'
                  AND u.is_active = 1
                  AND a.available = 1
                  AND NOT EXISTS (
                      SELECT 1 FROM delivery_assignments d
                      WHERE d.agent_id = u.id
                        AND d.status IN (
                            'assigned', 'accepted', 'picked_up',
                            'out_for_delivery'
                        )
                  )
                ORDER BY u.id
                LIMIT 1
            """).fetchone()

            if agent is None:
                continue

            connection.execute("""
                UPDATE delivery_assignments
                SET agent_id = ?, assigned_by = ?,
                    assignment_method = 'automatic',
                    status = 'assigned',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND agent_id IS NULL AND status = 'pending'
            """, (agent["id"], user["id"], job["id"]))

            connection.execute("""
                INSERT INTO tracking_events (assignment_id, status, note)
                VALUES (?, 'assigned', 'Automatically assigned')
            """, (job["id"],))

            assigned.append({
                "assignment_id": job["id"],
                "agent_id": agent["id"],
            })

    return {"assigned": assigned, "count": len(assigned)}


# ---------- Delivery tracking and timings ----------

@app.post("/api/agent/deliveries/{assignment_id}/update")
def update_delivery(
    assignment_id: int,
    request: DeliveryUpdate,
    user=Depends(current_user),
):
    require_role(user, "agent")

    allowed_statuses = {
        "accepted", "picked_up", "out_for_delivery",
        "delivered", "failed",
    }
    if request.status not in allowed_statuses:
        raise HTTPException(422, "Invalid delivery status")

    now = datetime.now(timezone.utc).isoformat()
    estimated = (
        request.estimated_arrival.isoformat()
        if request.estimated_arrival else None
    )

    with get_connection() as connection:
        assignment = connection.execute("""
            SELECT * FROM delivery_assignments
            WHERE id = ? AND agent_id = ?
        """, (assignment_id, user["id"])).fetchone()

        if assignment is None:
            raise HTTPException(404, "Delivery assignment not found")

        if assignment["status"] in ("delivered", "cancelled"):
            raise HTTPException(400, "This delivery is already closed")

        pickup_at = assignment["pickup_at"]
        delivered_at = assignment["delivered_at"]

        if request.status == "picked_up" and not pickup_at:
            pickup_at = now
        if request.status == "delivered":
            delivered_at = now

        connection.execute("""
            UPDATE delivery_assignments
            SET status = ?, pickup_at = ?, delivered_at = ?,
                estimated_arrival = COALESCE(?, estimated_arrival),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            request.status, pickup_at, delivered_at,
            estimated, assignment_id,
        ))

        connection.execute("""
            UPDATE orders SET order_status = ?
            WHERE id = ?
        """, (
            "delivered" if request.status == "delivered"
            else "out_for_delivery" if request.status == "out_for_delivery"
            else "ready_for_pickup" if request.status == "picked_up"
            else "processing",
            assignment["order_id"],
        ))

        connection.execute("""
            INSERT INTO tracking_events (
                assignment_id, status, note, latitude, longitude
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            assignment_id, request.status, request.note,
            request.latitude, request.longitude,
        ))

    return {
        "message": "Delivery tracking updated",
        "assignment_id": assignment_id,
        "status": request.status,
        "updated_at": now,
        "estimated_arrival": estimated,
    }


@app.get("/api/orders/{order_id}/tracking")
def order_tracking(
    order_id: int,
    user=Depends(current_user),
):
    require_role(user, "buyer", "admin", "agent")

    with get_connection() as connection:
        order = connection.execute("""
            SELECT o.id, o.buyer_id, o.order_status,
                   d.id AS assignment_id, d.agent_id, d.status,
                   d.pickup_at, d.estimated_arrival, d.delivered_at
            FROM orders o
            LEFT JOIN delivery_assignments d ON d.order_id = o.id
            WHERE o.id = ?
        """, (order_id,)).fetchone()

        if order is None:
            raise HTTPException(404, "Order not found")

        if user["role"] == "buyer" and order["buyer_id"] != user["id"]:
            raise HTTPException(403, "This is not your order")

        if (
            user["role"] == "agent"
            and order["agent_id"] != user["id"]
        ):
            raise HTTPException(403, "This delivery is not assigned to you")

        events = connection.execute("""
            SELECT status, note, latitude, longitude, event_time
            FROM tracking_events
            WHERE assignment_id = ?
            ORDER BY id
        """, (order["assignment_id"],)).fetchall()

    result = dict(order)
    result["events"] = [dict(event) for event in events]
    return result
