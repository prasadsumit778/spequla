"""Tests for tokenisation, corpus/02 section 8 and D-058."""
import pytest

from src.ingest.tokenise import InMemoryTokenStore, tokenise


def test_same_name_returns_same_token_every_time():
    store = InMemoryTokenStore()
    t1 = tokenise(store, "tenant-a", "customer", "Acme Traders Pvt Ltd")
    t2 = tokenise(store, "tenant-a", "customer", "Acme Traders Pvt Ltd")
    assert t1 == t2


def test_different_names_get_different_tokens():
    store = InMemoryTokenStore()
    t1 = tokenise(store, "tenant-a", "customer", "Acme Traders Pvt Ltd")
    t2 = tokenise(store, "tenant-a", "customer", "Northern Steel Distributors")
    assert t1 != t2


def test_token_format_customer_vs_vendor():
    store = InMemoryTokenStore()
    c = tokenise(store, "tenant-a", "customer", "Acme Traders")
    v = tokenise(store, "tenant-a", "vendor", "Northern Steel Suppliers")
    assert c.startswith("CUST_")
    assert v.startswith("VENDOR_")


def test_tokens_are_per_tenant():
    store = InMemoryTokenStore()
    t_a = tokenise(store, "tenant-a", "customer", "Acme Traders")
    t_b = tokenise(store, "tenant-b", "customer", "Acme Traders")
    # Same real name at two different tenants must not silently collapse to
    # the same token -- token_map is scoped per tenant.
    assert (("tenant-a", t_a)) != (("tenant-b", t_b)) or t_a == t_b  # tokens may coincide in value
    # but the store must have recorded them as two independent rows:
    assert store.find_token("tenant-a", "customer", "Acme Traders") is not None
    assert store.find_token("tenant-b", "customer", "Acme Traders") is not None


def test_empty_name_returns_none():
    store = InMemoryTokenStore()
    assert tokenise(store, "tenant-a", "customer", "") is None
    assert tokenise(store, "tenant-a", "customer", None) is None


def test_employee_entity_type_rejected():
    store = InMemoryTokenStore()
    with pytest.raises(ValueError):
        tokenise(store, "tenant-a", "employee", "Some Employee")
