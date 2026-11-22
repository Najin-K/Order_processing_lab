from decimal import Decimal
 
import pytest
 
from cart import ShoppingCart, InvalidQuantity, InsufficientStock
from checkout import CheckoutService
from payments import FakePaymentGateway
from repository import StoreRepository
from setup_db import initialize
 
@pytest.fixture
def repo(tmp_path):
    """ Implemented new repo fixture to create a fresh, seeded test database for every test. """
    db = str(tmp_path / "test.db")
    initialize(db)
    return StoreRepository(db)
 
""" Implemented new stock helper to read the current stock level for a product. """
def stock(repo, sku):
    return repo.get_product(sku).stock
 
""" Tests that totals use exact cent rounding with the discount and shipping applied. """
def test_money_is_exact(repo):
    cart = ShoppingCart("u1", repo)
    cart.add_item("USB-01", 3)
    cart.apply_discount("welcome10")
    assert cart.subtotal() == Decimal("29.97")
    assert cart.total() == Decimal("34.96")
 
""" Tests that zero, negative, fractional and boolean quantities raise InvalidQuantity. """ 
def test_bad_quantities_rejected(repo):
    cart = ShoppingCart("u1", repo)
    for bad in (0, -5, 1.5, True):
        with pytest.raises(InvalidQuantity):
            cart.add_item("MOU-01", bad)
 
""" Tests that adding items counts what is already in the cart against available stock. """
def test_stock_check_counts_cart_contents(repo):
    cart = ShoppingCart("u1", repo)
    cart.add_item("LAP-01", 3)
    with pytest.raises(InsufficientStock):
        cart.add_item("LAP-01", 3)  # 6 > 5
 
""" Tests that the discount is recalculated after cart edits and that a repeated coupon does not stack. """
def test_discount_follows_cart_edits_and_does_not_stack(repo):
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 2)
    cart.apply_discount("WELCOME10")
    cart.apply_discount("WELCOME10")
    assert cart.discount_amount() == Decimal("5.99")
    cart.add_item("MOU-01", 1)
    assert cart.discount_amount() == Decimal("8.99")
    cart.remove_item("MOU-01", 2)
    assert cart.discount_amount() == Decimal("3.00")
 
""" Tests that a fixed SAVE15 discount is capped at the subtotal so the total never drops below shipping. """ 
def test_fixed_discount_never_goes_negative(repo):
    cart = ShoppingCart("u1", repo)
    cart.add_item("USB-01", 1)
    cart.apply_discount("SAVE15")
    assert cart.discount_amount() == Decimal("9.99")
    assert cart.total() == Decimal("7.99")
 
""" Tests that a paid checkout reduces stock, empties the saved cart and charges the gateway once. """ 
def test_successful_checkout(repo):
    gw = FakePaymentGateway()
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 2)
    result = CheckoutService(repo, gw).checkout(cart, "TEST_TOKEN", "r1")
    assert result.status == "paid"
    assert stock(repo, "MOU-01") == 18
    assert cart.lines == [] and repo.get_saved_cart("u1") == []
    assert len(gw.calls) == 1
 

""" Tests that a declined payment returns the reserved stock and leaves the cart intact for a retry. """ 
def test_declined_payment_restores_stock_and_keeps_cart(repo):
    gw = FakePaymentGateway(should_approve=False)
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 2)
    result = CheckoutService(repo, gw).checkout(cart, "TEST_TOKEN", "r1")
    assert result.status == "declined"
    assert stock(repo, "MOU-01") == 20
    assert len(cart.lines) == 1
 
""" Tests that a gateway error is reported as payment_error and the reserved stock is restored. """ 
def test_gateway_exception_restores_stock(repo):
    class Boom(FakePaymentGateway):
        def charge(self, amount, payment_token):
            raise TimeoutError("network")
 
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 2)
    result = CheckoutService(repo, Boom()).checkout(cart, "TEST_TOKEN", "r1")
    assert result.status == "payment_error"
    assert stock(repo, "MOU-01") == 20
 
""" Tests that repeating a request_id returns the original order without charging or reserving stock again. """ 
def test_repeated_request_id_charges_once(repo):
    gw = FakePaymentGateway()
    svc = CheckoutService(repo, gw)
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 2)
    first = svc.checkout(cart, "TEST_TOKEN", "same")
    cart.add_item("MOU-01", 1)  # user clicks again with another cart state
    second = svc.checkout(cart, "TEST_TOKEN", "same")
    assert second.order_id == first.order_id and second.status == "paid"
    assert len(gw.calls) == 1 and stock(repo, "MOU-01") == 18
 
""" Tests that when two carts want the last units, only the first checkout succeeds and stock never goes negative. """ 
def test_last_units_cannot_be_oversold(repo):
    gw = FakePaymentGateway()
    svc = CheckoutService(repo, gw)
    a, b = ShoppingCart("a", repo), ShoppingCart("b", repo)
    a.add_item("LAP-01", 3)
    b.add_item("LAP-01", 3)
    assert svc.checkout(a, "TEST_TOKEN", "ra").status == "paid"
    assert svc.checkout(b, "TEST_TOKEN", "rb").status == "out_of_stock"
    assert stock(repo, "LAP-01") == 2 and len(gw.calls) == 1
    assert len(b.lines) == 1
 
""" Tests that checkout raises ValueError when the request_id is empty. """ 
def test_missing_request_id_rejected(repo):
    cart = ShoppingCart("u1", repo)
    cart.add_item("MOU-01", 1)
    with pytest.raises(ValueError):
        CheckoutService(repo, FakePaymentGateway()).checkout(cart, "TEST_TOKEN", "")
 
""" Tests that SQL injection strings are treated as plain text and return nothing. """
def test_sql_injection_is_inert(repo):
    assert repo.get_product("x' OR '1'='1") is None
    assert repo.get_saved_cart("x' OR '1'='1") == []
 
""" Tests that list_orders returns only the requesting user's orders. """ 
def test_orders_are_per_user(repo):
    svc = CheckoutService(repo, FakePaymentGateway())
    for user in ("a", "b"):
        cart = ShoppingCart(user, repo)
        cart.add_item("USB-01", 1)
        svc.checkout(cart, "TEST_TOKEN", f"req-{user}")
    assert [o[1] for o in repo.list_orders("a")] == ["a"]
