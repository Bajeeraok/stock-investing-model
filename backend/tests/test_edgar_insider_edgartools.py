"""Tests for edgartools Form 4 insider flow helpers."""
from __future__ import annotations

from signals.edgar_insider import _buys_sells_from_form4, _classify_transaction


class _Act:
    def __init__(self, code, transaction_type, shares):
        self.code = code
        self.transaction_type = transaction_type
        self.shares = shares


class _Form4:
    def get_transaction_activities(self):
        return [
            _Act("S", "sale", 1000),
            _Act("P", "purchase", 500),
        ]

    @property
    def common_stock_purchases(self):
        return None

    @property
    def common_stock_sales(self):
        return None


def test_classify_transaction():
    assert _classify_transaction("P", "purchase") == "buy"
    assert _classify_transaction("S", "sale") == "sell"
    assert _classify_transaction("M", "exercise") == "buy"


def test_buys_sells_from_form4():
    buys, sells, n = _buys_sells_from_form4(_Form4())
    assert buys == 500
    assert sells == 1000
    assert n == 2
