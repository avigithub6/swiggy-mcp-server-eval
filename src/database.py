import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "swiggy.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize SQLite tables and seed realistic Swiggy orders & coupons."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY,
        vertical TEXT NOT NULL,          -- 'FOOD' or 'INSTAMART'
        items TEXT NOT NULL,
        total_amount REAL NOT NULL,
        status TEXT NOT NULL,            -- 'Preparing', 'Out for delivery', 'Delivered', 'Cancelled', 'Refunded'
        eta_mins INTEGER NOT NULL,
        rider_name TEXT,
        rider_phone TEXT
    );

    CREATE TABLE IF NOT EXISTS coupons (
        code TEXT PRIMARY KEY,
        discount_percent INTEGER NOT NULL,
        min_order REAL NOT NULL,
        is_swiggy_one_only INTEGER DEFAULT 0
    );
    """)

    # Seed realistic orders if table is empty
    cursor.execute("SELECT COUNT(*) FROM orders")
    if cursor.fetchone()[0] == 0:
        sample_orders = [
            ("SWG-101", "FOOD", "Paneer Tikka Masala, 2 Butter Naan", 340.0, "Out for delivery", 10, "Ramesh Kumar", "+91-9811100001"),
            ("SWG-102", "FOOD", "Hyderabadi Chicken Biryani (Full)", 420.0, "Preparing", 25, "Suresh Yadav", "+91-9811100002"),
            ("SWG-103", "FOOD", "Masala Dosa, Filter Coffee", 180.0, "Delivered", 0, "Amit Sharma", "+91-9811100003"),
            ("SWG-104", "INSTAMART", "Amul Milk 1L, Brown Bread, 6 Eggs", 165.0, "Out for delivery", 6, "Vikram Singh", "+91-9811100004"),
            ("SWG-105", "FOOD", "Veg Hakka Noodles, Chilli Paneer", 290.0, "Delayed", 45, "Deepak Verma", "+91-9811100005"),
            ("SWG-106", "INSTAMART", "1kg Tomatoes, Coriander, Green Chillies", 85.0, "Delivered", 0, "Ravi Tiwari", "+91-9811100006"),
            ("SWG-107", "FOOD", "Margherita Pizza (Medium), Garlic Bread", 620.0, "Preparing", 30, "Karan Mehta", "+91-9811100007"),
        ]
        cursor.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            sample_orders
        )

        sample_coupons = [
            ("SWIGGY50", 50, 199.0, 0),
            ("TRYNEW", 30, 149.0, 0),
            ("ONEFREE", 20, 99.0, 1),
        ]
        cursor.executemany(
            "INSERT INTO coupons VALUES (?, ?, ?, ?)",
            sample_coupons
        )

    conn.commit()
    conn.close()

def reset_db():
    """Drop existing tables and re-seed fresh data for deterministic evaluation runs."""
    conn = get_connection()
    conn.executescript("""
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS coupons;
    """)
    conn.commit()
    conn.close()
    init_db()


if __name__ == "__main__":
    init_db()
    print(f"✅ Database initialized successfully at: {DB_PATH}")
