"""Initialize demo data in a chosen local SQLite file."""
import sqlite3
import sys

""" Updated SCHEMA
    products table doesn't allow negative stock
    saved_cart doesn't allow duplicate lines per user
    orders hard stops duplicate orders
    orer_item allows for restock on failure
"""
SCHEMA = '''
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    price REAL NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0)
);
CREATE TABLE IF NOT EXISTS saved_cart (
    user_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (user_id, sku)
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),  -- money as integer cents
    status TEXT NOT NULL,
    request_id TEXT NOT NULL UNIQUE,
    transaction_id TEXT
);
CREATE TABLE IF NOT EXISTS order_items (
    order_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, sku)
);
'''

def initialize(db_path='shop.db'):
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.executemany('INSERT OR IGNORE INTO products VALUES (?, ?, ?, ?)', [
            ('LAP-01', 'Laptop', 999.99, 5),
            ('MOU-01', 'Wireless mouse', 29.95, 20),
            ('USB-01', 'USB cable', 9.99, 50),
        ])


if __name__ == '__main__':
    initialize(sys.argv[1] if len(sys.argv) > 1 else 'shop.db')
