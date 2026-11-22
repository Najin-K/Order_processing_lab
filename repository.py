"""SQLite persistence. Contains deliberate reliability/security problems."""
import sqlite3
from models import Product

""" Added Decimal and context lib modules. """
from contextlib import contextmanager
from decimal import Decimal

""" Added three set values for an orders status. """
FINAL_STATUSES = {"paid", "declined", "payment_error"}

""" Added a custom exception method for out of stock. """
class OutOfStockError(Exception): ...

class StoreRepository:
    def __init__(self, db_path='shop.db'):
        self.db_path = db_path

    def connect(self):
        return sqlite3.connect(self.db_path, timeout=2, isolation_level=None)

    """ Implemented new transaction function to run multiple database steps at once and rollback on any error. """
    @contextmanager
    def transaction(self):
        
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()

    """ Implemented a query wrapper to run the SQL call is needed. """
    def query(self, sql, params=()):
        conn = self.connect()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    """ Refactored to use SQL params to help prevent sql injection. """
    def get_product(self, sku):
        rows = self.query("SELECT sku, name, price, stock FROM products WHERE sku = ?", (sku,))
        return Product(*rows[0]) if rows else None

    """ Refactored to use SQL params to help prevent SQL injection. """
    def get_saved_cart(self, user_id):
        return self.query("SELECT sku, quantity FROM saved_cart WHERE user_id = ?", (user_id,))

    """ Implemented to get a specific order by request_id. """
    def get_order_by_request_id(self, request_id):
        rows = self.query(
            "SELECT id, user_id, amount_cents, status FROM orders WHERE request_id = ?",
            (request_id,))
        return rows[0] if rows else None

    """ Refactored save_cart to use new transaction funcction and SQL params. """
    def save_cart(self, user_id, lines):
        with self.transaction() as conn:
            conn.execute("DELETE FROM saved_cart WHERE user_id = ?", (user_id,))
            conn.executemany(
                "INSERT INTO saved_cart(user_id, sku, quantity) VALUES (?, ?, ?)",
                [(user_id, l.sku, l.quantity) for l in lines])

    """ Implemented new place_order function to reserve stock and create a pending order in one transaction. """
    def place_order(self, user_id, items, amount_cents, request_id):
        with self.transaction() as conn:
            row = conn.execute("SELECT id, user_id FROM orders WHERE request_id = ?",
                               (request_id,)).fetchone()
            if row:
                if row[1] != user_id:
                    raise ValueError("request_id already used by another user")
                return row[0], False
            for sku, qty in items:
                cur = conn.execute(
                    "UPDATE products SET stock = stock - ? WHERE sku = ? AND stock >= ?",
                    (qty, sku, qty))
                if cur.rowcount != 1:  # unknown sku or not enough stock
                    raise OutOfStockError(sku)  # rolls back earlier decrements too
            cur = conn.execute(
                "INSERT INTO orders(user_id, amount_cents, status, request_id) "
                "VALUES (?, ?, 'pending', ?)", (user_id, amount_cents, request_id))
            order_id = cur.lastrowid
            conn.executemany("INSERT INTO order_items(order_id, sku, quantity) VALUES (?, ?, ?)",
                             [(order_id, s, q) for s, q in items])
            return order_id, True

    """ Implemented new finalize_order function to set the final order status and restock if payment failed. """
    def finalize_order(self, order_id, status, transaction_id=None):
        """Move a pending order to its final status. Not paid -> stock goes back.

        Only acts on 'pending' orders, so calling it twice can't restock twice.
        """
        if status not in FINAL_STATUSES:
            raise ValueError(f"Bad status {status!r}")
        with self.transaction() as conn:
            row = conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
            if not row or row[0] != "pending":
                return False
            if status != "paid":
                items = conn.execute("SELECT sku, quantity FROM order_items WHERE order_id = ?",
                                     (order_id,)).fetchall()
                for sku, qty in items:
                    conn.execute("UPDATE products SET stock = stock + ? WHERE sku = ?", (qty, sku))
            conn.execute("UPDATE orders SET status = ?, transaction_id = ? WHERE id = ?",
                         (status, transaction_id, order_id))
            return True

    """ Refactored to get users order instead of every single users. """
    def list_orders(self, user_id):
        rows = self.query(
            "SELECT id, user_id, amount_cents, status FROM orders "
            "WHERE user_id = ? ORDER BY id DESC", (user_id,))
        return [(i, u, Decimal(c).scaleb(-2).quantize(Decimal('0.01')), s) for i, u, c, s in rows]