"""Starting values per country (FR-TEN-004: defaults are data, never hard-coded logic).

Indonesian rates must be verified with a tax advisor before launch (docs/README: "verify").
Every tenant can change them; regional PBJT rates differ by city.
"""

from typing import Any

# FR-INV-006: sales may go negative (flagged), production and transfers ask first.
STOCK: dict[str, Any] = {
    "negative_stock": {"sale": "allow", "production": "warn", "transfer": "warn", "other": "block"},
    "expiry_warning_days": 2,
    "low_days_alert": 2,
}

DEFAULTS: dict[str, dict[str, Any]] = {
    "ID": {
        "tax": {
            "rules": [
                {
                    "id": "pbjt",
                    "name": "PBJT",
                    "rate_bp": 1000,
                    "applies_to_service_charge": True,
                    "price_includes_tax": False,
                    "order": 0,
                    "active": True,
                }
            ]
        },
        "service_charge": {"enabled": False, "rate_bp": 0, "channels": [], "before_tax": True},
        "payment_methods": {
            "methods": [
                {"code": "cash", "name": "Tunai", "kind": "cash"},
                {"code": "qris", "name": "QRIS", "kind": "qris_static"},
                {"code": "transfer", "name": "Transfer bank", "kind": "bank_transfer"},
                {"code": "card", "name": "Kartu debit/kredit", "kind": "card_terminal"},
                {
                    "code": "platform",
                    "name": "Penyelesaian platform",
                    "kind": "platform_settlement",
                },
            ]
        },
        "numbering": {
            "formats": {
                "purchase_order": {"prefix": "PO", "padding": 5, "reset": "yearly"},
                "goods_receipt": {"prefix": "GR", "padding": 5, "reset": "yearly"},
                "transfer": {"prefix": "TRF", "padding": 5, "reset": "yearly"},
                "production": {"prefix": "PRD", "padding": 5, "reset": "yearly"},
                "stock_count": {"prefix": "CNT", "padding": 5, "reset": "yearly"},
                "adjustment": {"prefix": "ADJ", "padding": 5, "reset": "yearly"},
                "sales_day": {"prefix": "SD", "padding": 5, "reset": "yearly"},
                "pos_order": {"prefix": "POS", "padding": 6, "reset": "yearly"},
                "expense": {"prefix": "EXP", "padding": 5, "reset": "yearly"},
                "vendor_return": {"prefix": "RTN", "padding": 5, "reset": "yearly"},
                "vendor_bill": {"prefix": "BILL", "padding": 5, "reset": "yearly"},
                "journal": {"prefix": "JE", "padding": 6, "reset": "yearly"},
                "wholesale_invoice": {"prefix": "INV", "padding": 5, "reset": "yearly"},
            }
        },
        "session": {"idle_minutes": 60},
        "stock": {**STOCK, "count_variance_alert": 200_000},  # Rp 200.000
        "purchasing": {"require_invoice_attachment": False},
        "catalog": {"target_food_cost_bp": 3500},  # 35 %, a common Indonesian target
        "pos": {
            "require_shift": True,
            "cash_rounding_step": 0,
            "tips_enabled": False,
            "void_stock_effect": "waste",
        },
        "receipt": {"header": "", "footer": "Terima kasih!", "paper_mm": 58},
    }
}

# Countries without their own defaults start empty and configure everything themselves.
FALLBACK: dict[str, Any] = {
    "tax": {"rules": []},
    "service_charge": {"enabled": False, "rate_bp": 0, "channels": [], "before_tax": True},
    "payment_methods": {"methods": [{"code": "cash", "name": "Cash", "kind": "cash"}]},
    "numbering": {"formats": {}},
    "session": {"idle_minutes": 60},
    "stock": STOCK,
    "purchasing": {"require_invoice_attachment": False},
    "catalog": {"target_food_cost_bp": None},
    "pos": {
        "require_shift": True,
        "cash_rounding_step": 0,
        "tips_enabled": False,
        "void_stock_effect": "waste",
    },
    "kitchen": {"late_minutes": 15, "recall_minutes": 30},
    "receipt": {"header": "", "footer": "", "paper_mm": 58},
    "production": {"prep_includes_requests": True},
    "tables": {
        "default_dwell_minutes": 90,
        "no_show_after_minutes": 15,
        "allow_overbooking": False,
    },
    "finance": {"auto_journals": True},
    "wholesale": {"payment_terms_days": 14},
}


def default_for(country: str, key: str) -> Any:
    return DEFAULTS.get(country, FALLBACK).get(key, FALLBACK[key])
