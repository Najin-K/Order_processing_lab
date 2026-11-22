"""Business logic. Several design and correctness issues are intentional."""
from models import CartLine

""" Imported decimal module for financial calculations. """
from decimal import Decimal, ROUND_HALF_UP

""" Added flat shipping fee for FREESHIP coupon to be used on. """
SHIPPING_FEE = Decimal("7.99")

""" Added coupons to a dictionary. """
COUPONS = {
    "WELCOME10": (Decimal("0.10"), Decimal("0"), False),
    "STUDENT20": (Decimal("0.20"), Decimal("0"), False),
    "SAVE15": (Decimal("0"), Decimal("15"), False),
    "FREESHIP": (Decimal("0"), Decimal("0"), True),
}

""" Implemented a helper function to handle money rounding. """
def to_money(value):
    """Decimal rounded to cents; never does arithmetic on binary floats."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

""" Added a custom CartError exception class methods for certain exceptions. """
class CartError(Exception): ...
class InvalidQuantity(CartError): ...
class UnknownProduct(CartError): ...
class ItemNotInCart(CartError): ...
class InsufficientStock(CartError): ...
class InvalidCoupon(CartError): ...

class ShoppingCart:
    def __init__(self, user_id, repository):
        self.user_id = user_id
        self.repository = repository
        self.lines = []
        self.discount_code = None
        self.discounted_total = None

    """ Implemented helper function to check if item is in lines Array. """
    def find(self, sku):
        return next((x for x in self.lines if x.sku == sku), None)

    """ Implemented helper function to validate quantity value. """
    def validate_quantity_value(self, quantity):
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise InvalidQuantity(f"Quantity must be a positive integer, got {quantity!r}")

    def add_item(self, sku, quantity):
        """ Using helper function to validate quantity value. """
        self.validate_quantity_value(quantity)
        
        product = self.repository.get_product(sku)
        if not product:
            raise UnknownProduct(sku)
        
        existing = self.find(sku)
        """ Implemented a check to add quantity to current quantity if there is enough product stock. """
        new_quantity = quantity + (existing.quantity if existing else 0)
        if product.stock < new_quantity:  # counts what is already in the cart
            raise InsufficientStock(f"{sku}: New quantity {new_quantity}, only {product.stock} in stock")
        
        if existing:
            existing.quantity += quantity
        else:
            self.lines.append(CartLine(sku, product.name, product.price, quantity))
        return True

    def remove_item(self, sku, quantity=None):
        """ Removed for loop and used new helper fucntion. """
        line = self.find(sku)
        """ Check if line is None raise the custom ItemNotInCart exception. """
        if line == None:
            raise ItemNotInCart(sku)
        """ If line is NOT None validate the quantity value. """
        if quantity is not None:
            self.validate_quantity_value(quantity)
        """ Removes the entire line in the shopping cart. """
        if quantity is None or quantity >= line.quantity:
            self.lines = [x for x in self.lines if x.sku != sku]
        else:
            """ Removes only a certain amount in the shopping cart. """
            line.quantity -= quantity
        return True

    def subtotal(self):
        """ Refactored to use helper function and Decimal module. """
        return sum((to_money(l.unit_price) * l.quantity for l in self.lines), Decimal("0.00"))

    """ Refactored to use new discount_amount and shipping helper to properly calculate total. """
    def total(self):
        return self.subtotal() - self.discount_amount() + self.shipping()

    """ Refactored to use new coupon dictionary. """
    def apply_discount(self, code):
        """ Sets/replace the active coupon so there is no coupon stacking. """
        key = (code or "").strip().upper()
        if key not in COUPONS:
            raise InvalidCoupon(code)
        self.discount_code = key
        return True

    """ Implemented helper function to properly apply discount amount. """
    def discount_amount(self):
        if self.discount_code not in COUPONS:
            return Decimal("0.00")
        pct, fixed, _ = COUPONS[self.discount_code]
        sub = self.subtotal()
        return min(to_money(sub * pct + fixed), sub)  # never below zero

    """ Implemented a shipping fee for FREESHIP coupon to apply to. """
    def shipping(self):
        if not self.lines:
            return Decimal("0.00")
        free = self.discount_code in COUPONS and COUPONS[self.discount_code][2]
        return Decimal("0.00") if free else SHIPPING_FEE

    def load(self):
        for sku, quantity in self.repository.get_saved_cart(self.user_id):
            self.add_item(sku, quantity)

    def save(self):
        self.repository.save_cart(self.user_id, self.lines)
