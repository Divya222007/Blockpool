
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "blockpool.db"


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    with get_connection() as connection:

        # Existing shopping requests
        connection.execute("""
            CREATE TABLE IF NOT EXISTS shopping_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resident TEXT NOT NULL,
                product_id TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0)
            )
        """)

        # Existing product requests
        connection.execute("""
            CREATE TABLE IF NOT EXISTS product_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resident TEXT NOT NULL,
                name TEXT NOT NULL,
                brand TEXT NOT NULL DEFAULT 'Any',
                variant TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                status TEXT NOT NULL DEFAULT 'pending_review'
            )
        """)

        # Users
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                phone TEXT,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL
                    CHECK (role IN ('buyer', 'seller', 'agent', 'admin')),
                apartment_name TEXT,
                block_tower TEXT,
                flat_number TEXT,
                address TEXT,
                city TEXT,
                pincode TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Seller products
        connection.execute("""
            CREATE TABLE IF NOT EXISTS seller_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                category TEXT,
                description TEXT,
                unit TEXT NOT NULL DEFAULT 'unit',
                price REAL NOT NULL CHECK (price >= 0),
                available_quantity INTEGER NOT NULL DEFAULT 0
                    CHECK (available_quantity >= 0),
                minimum_bulk_quantity INTEGER NOT NULL DEFAULT 1
                    CHECK (minimum_bulk_quantity > 0),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (seller_id) REFERENCES users(id)
            )
        """)

        # Orders
        connection.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                buyer_id INTEGER NOT NULL,
                total_amount REAL NOT NULL CHECK (total_amount >= 0),
                delivery_fee REAL NOT NULL DEFAULT 0
                    CHECK (delivery_fee >= 0),
                payment_method TEXT,
                payment_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (payment_status IN (
                        'pending', 'paid', 'failed', 'refunded'
                    )),
                order_status TEXT NOT NULL DEFAULT 'confirmed'
                    CHECK (order_status IN (
                        'confirmed', 'processing', 'ready_for_pickup',
                        'out_for_delivery', 'delivered', 'cancelled'
                    )),
                delivery_address TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (buyer_id) REFERENCES users(id)
            )
        """)

        # Items in each order
        connection.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER,
                product_name TEXT NOT NULL,
                seller_id INTEGER,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_price REAL NOT NULL CHECK (unit_price >= 0),
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (product_id) REFERENCES seller_products(id),
                FOREIGN KEY (seller_id) REFERENCES users(id)
            )
        """)

        # Delivery assignments
        connection.execute("""
            CREATE TABLE IF NOT EXISTS delivery_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL UNIQUE,
                agent_id INTEGER,
                assigned_by INTEGER,
                assignment_method TEXT NOT NULL DEFAULT 'pending'
                    CHECK (assignment_method IN (
                        'automatic', 'self_accept', 'admin', 'pending'
                    )),
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN (
                        'pending', 'assigned', 'accepted', 'picked_up',
                        'out_for_delivery', 'delivered', 'failed', 'cancelled'
                    )),
                pickup_at TEXT,
                estimated_arrival TEXT,
                delivered_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (agent_id) REFERENCES users(id),
                FOREIGN KEY (assigned_by) REFERENCES users(id)
            )
        """)

        # Delivery tracking events
        connection.execute("""
            CREATE TABLE IF NOT EXISTS tracking_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assignment_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                note TEXT,
                latitude REAL,
                longitude REAL,
                event_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (assignment_id)
                    REFERENCES delivery_assignments(id)
            )
        """)

        # NEW: Bulk pools managed by BlockPool
        connection.execute("""
            CREATE TABLE IF NOT EXISTS bulk_pools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pool_code TEXT NOT NULL UNIQUE,
                product_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                supplier_id INTEGER,
                supplier_name TEXT,
                delivery_area TEXT NOT NULL,
                pooling_mode TEXT NOT NULL DEFAULT 'area'
                    CHECK (pooling_mode IN ('community', 'area')),
                unit TEXT NOT NULL DEFAULT 'unit',
                base_price REAL NOT NULL CHECK (base_price >= 0),
                bulk_unit_price REAL NOT NULL CHECK (bulk_unit_price >= 0),
                minimum_quantity INTEGER NOT NULL DEFAULT 1
                    CHECK (minimum_quantity > 0),
                target_quantity INTEGER NOT NULL DEFAULT 1
                    CHECK (target_quantity > 0),
                deadline TEXT,
                status TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN (
                        'open', 'target_reached', 'closed',
                        'procurement', 'fulfilled', 'cancelled'
                    )),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (supplier_id) REFERENCES users(id)
            )
        """)

        # NEW: Individual buyer contributions to a bulk pool
        connection.execute("""
            CREATE TABLE IF NOT EXISTS bulk_pool_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pool_id INTEGER NOT NULL,
                buyer_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                delivery_address TEXT NOT NULL,
                unit_price REAL NOT NULL CHECK (unit_price >= 0),
                allocated_total REAL NOT NULL CHECK (allocated_total >= 0),
                status TEXT NOT NULL DEFAULT 'joined'
                    CHECK (status IN (
                        'joined', 'confirmed', 'cancelled', 'fulfilled'
                    )),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pool_id) REFERENCES bulk_pools(id),
                FOREIGN KEY (buyer_id) REFERENCES users(id),
                UNIQUE (pool_id, buyer_id)
            )
        """)

        # Indexes
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_role
            ON users(role)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_seller_products_active
            ON seller_products(is_active)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_buyer
            ON orders(buyer_id)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_delivery_agent
            ON delivery_assignments(agent_id, status)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_bulk_pools_product_area
            ON bulk_pools(product_id, delivery_area, status)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_bulk_members_buyer
            ON bulk_pool_members(buyer_id, status)
        """)


# Existing shopping request functions
def get_shopping_requests():
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT id, resident, product_id, quantity
            FROM shopping_requests
            ORDER BY id DESC
        """).fetchall()

        return [dict(row) for row in rows]


def add_shopping_request(resident, product_id, quantity):
    with get_connection() as connection:
        cursor = connection.execute("""
            INSERT INTO shopping_requests (resident, product_id, quantity)
            VALUES (?, ?, ?)
        """, (resident, product_id, quantity))

        return cursor.lastrowid


# Existing product request functions
def get_product_requests():
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT id, resident, name, brand, variant, quantity, status
            FROM product_requests
            ORDER BY id DESC
        """).fetchall()

        return [dict(row) for row in rows]


def add_product_request(
    resident,
    name,
    brand="Any",
    variant="",
    quantity=1
):
    with get_connection() as connection:
        cursor = connection.execute("""
            INSERT INTO product_requests
                (resident, name, brand, variant, quantity)
            VALUES (?, ?, ?, ?, ?)
        """, (resident, name, brand, variant, quantity))

        return cursor.lastrowid
