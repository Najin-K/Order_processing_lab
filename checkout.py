"""Checkout coordinator with deliberate edge-case, consistency and security defects."""
from decimal import Decimal
 
from cart import to_money
from repository import OutOfStockError
from models import OrderResult

""" Return row result using the money rounding helper function from cart. """
def result_from_row(row):
    order_id, user, cents, status = row
    return OrderResult(order_id, status, to_money(Decimal(cents) / 100))


class CheckoutService:
    def __init__(self, repository, payment_gateway):
        self.repository = repository
        self.payment_gateway = payment_gateway

    """ Implemented new refresh_prices function to update any stale cart prices and return a status if checkout must stop. """
    def refresh_prices(self, cart):
        changed = False
        for line in cart.lines:
            product = self.repository.get_product(line.sku)
            if not product:
                return "unavailable"
            current = to_money(product.price)
            if current != to_money(line.unit_price):
                line.unit_price = current
                changed = True
        return "price_changed" if changed else None

    """ Refactored checkout method with new methods from repository and cart. """
    def checkout(self, cart, payment_token, request_id):
        if not request_id:
            raise ValueError("request_id is required")

        existing = self.repository.get_order_by_request_id(request_id)
        if existing:
            if existing[1] != cart.user_id:
                raise ValueError("request_id already used by another user")
            return result_from_row(existing)
 
        if not cart.lines:
            return OrderResult(None, "empty", Decimal("0.00"))
        if not payment_token:
            raise ValueError("payment_token is required")
 
        problem = self.refresh_prices(cart)
        if problem:
            return OrderResult(None, problem, cart.total())
 
        amount = cart.total()
        items = [(l.sku, l.quantity) for l in cart.lines]
 
        """ Reserve stock and create a 'pending' order. """
        try:
            order_id, created = self.repository.place_order(
                cart.user_id, items, int(amount * 100), request_id)
        except OutOfStockError:
            return OrderResult(None, "out_of_stock", amount)
        if not created:
            return result_from_row(self.repository.get_order_by_request_id(request_id))
 
        transaction_id = None
        if amount == 0:
            status = "paid"
        else:
            try:
                response = self.payment_gateway.charge(amount, payment_token)
                if response.get("approved") is True:
                    status, transaction_id = "paid", response.get("transaction_id")
                else:
                    status = "declined"
            except Exception:
                status = "payment_error"
 
        """ Record the outcome; non-paid statuses give the stock back. """
        self.repository.finalize_order(order_id, status, transaction_id)
 
        if status == "paid":
            cart.lines = []
            cart.discount_code = None
            cart.save()
        return OrderResult(order_id, status, amount)