from types import SimpleNamespace

import pytest
from django.contrib import admin as dj_admin

from accounts.admin import CustomUserAdmin
from accounts.models import User
from menu.admin import ProductAdmin, StockAdjustmentAdmin
from menu.models import Product, StockAdjustment
from orders.models import OrderOutbox

pytestmark = pytest.mark.django_db


def _req(user):
    return SimpleNamespace(user=user)


def test_product_admin_stock_edit_routes_through_service(make_product, employee_user):
    product = make_product(stock=5)
    ma = ProductAdmin(Product, dj_admin.site)
    product.stock_quantity = 20  # what the admin form submitted
    ma.save_model(_req(employee_user), product, SimpleNamespace(changed_data=["stock_quantity"]), change=True)

    product.refresh_from_db()
    assert product.stock_quantity == 20 and product.version == 2
    assert OrderOutbox.objects.filter(event_type="inventory.stock_changed", aggregate_id=product.code).exists()
    assert StockAdjustment.objects.filter(product=product, reason="admin edit").exists()


def test_product_admin_non_stock_edit_emits_nothing(make_product, employee_user):
    product = make_product(stock=5)
    ma = ProductAdmin(Product, dj_admin.site)
    product.name = "Новое имя"
    ma.save_model(_req(employee_user), product, SimpleNamespace(changed_data=["name"]), change=True)

    product.refresh_from_db()
    assert product.version == 1
    assert not OrderOutbox.objects.filter(event_type="inventory.stock_changed").exists()


def test_user_admin_profile_edit_routes_through_service(user):
    ma = CustomUserAdmin(User, dj_admin.site)
    user.first_name = "Пётр"
    ma.save_model(_req(user), user, SimpleNamespace(changed_data=["first_name"]), change=True)

    user.refresh_from_db()
    assert user.first_name == "Пётр" and user.customer_version == 2
    assert OrderOutbox.objects.filter(event_type="identity.customer_changed", aggregate_id=str(user.id)).exists()


def test_stock_adjustment_admin_is_audit_only():
    ma = StockAdjustmentAdmin(StockAdjustment, dj_admin.site)
    req = _req(None)
    assert ma.has_add_permission(req) is False
    assert ma.has_change_permission(req) is False
    assert ma.has_delete_permission(req) is False
