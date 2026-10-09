"""Tenant setting schemas (FR-TEN-004 to 006, 009, FR-IDN-009).

Each setting key has one Pydantic model; values are validated on every write, and stored as
JSON in tenant_settings. Rates are integer basis points (1000 = 10.00 %), never floats
(CLAUDE.md rule 5).
"""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Slug = Annotated[str, Field(pattern=r"^[a-z0-9_]{1,40}$")]
BasisPoints = Annotated[int, Field(ge=0, le=10_000)]  # 0 to 100.00 %


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # mass-assignment protection (docs/06)


class TaxRule(Strict):
    id: Slug
    name: str = Field(min_length=1, max_length=60)
    rate_bp: BasisPoints
    applies_to_service_charge: bool = True  # e.g. PBJT is charged on service charge too
    price_includes_tax: bool = False
    order: int = Field(default=0, ge=0, le=99)  # calculation order
    outlet_ids: list[uuid.UUID] | None = None  # None: every outlet
    active: bool = True


class TaxSettings(Strict):
    rules: list[TaxRule] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_ids(self) -> "TaxSettings":
        ids = [r.id for r in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("tax rule ids must be unique")
        return self


class ServiceChargeSettings(Strict):
    enabled: bool = False  # FR-TEN-005: off by default
    rate_bp: BasisPoints = 0
    channels: list[Slug] = Field(default_factory=list, max_length=20)  # empty: all channels
    before_tax: bool = True


PaymentKind = Literal[
    "cash",
    "qris_static",
    "bank_transfer",
    "card_terminal",
    "ewallet",
    "platform_settlement",
    "voucher",
    "house_account",
]


class PaymentMethod(Strict):
    code: Slug
    name: str = Field(min_length=1, max_length=60)
    kind: PaymentKind
    active: bool = True


class PaymentMethodSettings(Strict):
    methods: list[PaymentMethod] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def unique_codes(self) -> "PaymentMethodSettings":
        codes = [m.code for m in self.methods]
        if len(codes) != len(set(codes)):
            raise ValueError("payment method codes must be unique")
        return self


class NumberingFormat(Strict):
    prefix: str = Field(pattern=r"^[A-Z0-9-]{1,10}$")
    padding: int = Field(default=5, ge=3, le=8)
    reset: Literal["yearly", "never"] = "yearly"


class NumberingSettings(Strict):
    """FR-TEN-009: per document type; numbers are allocated per outlet and year."""

    formats: dict[Slug, NumberingFormat] = Field(default_factory=dict, max_length=40)


class SessionSettings(Strict):
    """FR-IDN-009: tenant idle timeout within the platform limit."""

    idle_minutes: int = Field(default=60, ge=5, le=24 * 60)


ShortagePolicy = Literal["allow", "warn", "block"]


class NegativeStockPolicy(Strict):
    """FR-INV-006: what happens when more is used than is on hand. "warn": the user must
    confirm; "allow": posted and flagged for review; "block": refused."""

    sale: ShortagePolicy = "allow"
    production: ShortagePolicy = "warn"
    transfer: ShortagePolicy = "warn"
    other: ShortagePolicy = "block"  # waste and similar


class StockSettings(Strict):
    negative_stock: NegativeStockPolicy = Field(default_factory=NegativeStockPolicy)
    # FR-INV-012: warn this many days before a batch expires (0 = only on the day).
    expiry_warning_days: int = Field(default=2, ge=0, le=60)
    # FR-INV-012: alert when stock lasts fewer days than this at the recent pace (0 = off).
    low_days_alert: int = Field(default=2, ge=0, le=60)
    # FR-INV-012: alert when a count's difference is worth at least this (minor units, 0 = off).
    count_variance_alert: int = Field(default=0, ge=0, le=10**12)


class CatalogSettings(Strict):
    """FR-CAT-012: default food cost (HPP) target for menu items without their own; None = off."""

    target_food_cost_bp: BasisPoints | None = None


class PurchasingSettings(Strict):
    """FR-PUR-011: supplier invoice photo on receipts, optional unless the tenant requires it."""

    require_invoice_attachment: bool = False


class PosSettings(Strict):
    """FR-SAL-006, 009: how the cashier screen works for this business."""

    require_shift: bool = True  # payments need an open cash shift
    cash_rounding_step: int = Field(default=0, ge=0, le=100_000)  # 0 = off; e.g. 100 for Rp 100
    tips_enabled: bool = False
    # FR-SAL-008: a voided line that was already sent was cooked: write its ingredients off as
    # waste, or not (when the kitchen reuses it).
    void_stock_effect: Literal["waste", "none"] = "waste"


class KitchenSettings(Strict):
    """FR-KDS-004: when a ticket counts as late, and how long a bumped one can be recalled."""

    late_minutes: int = Field(default=15, ge=1, le=240)
    recall_minutes: int = Field(default=30, ge=1, le=24 * 60)


class ProductionSettings(Strict):
    """FR-PRD-008: whether open branch requests (transfers) add to the central kitchen's prep
    list, on top of its own par levels."""

    prep_includes_requests: bool = True


class ReceiptSettings(Strict):
    """FR-SAL-010: what the printed receipt says around the sale, and the paper width."""

    header: str = Field(default="", max_length=300)  # e.g. tax id, phone, Instagram
    footer: str = Field(default="", max_length=300)  # e.g. "Terima kasih!"
    paper_mm: Literal[58, 80] = 58  # most Bluetooth printers in Indonesia are 58 mm


SETTINGS: dict[str, type[Strict]] = {
    "tax": TaxSettings,
    "service_charge": ServiceChargeSettings,
    "payment_methods": PaymentMethodSettings,
    "numbering": NumberingSettings,
    "session": SessionSettings,
    "stock": StockSettings,
    "purchasing": PurchasingSettings,
    "catalog": CatalogSettings,
    "pos": PosSettings,
    "kitchen": KitchenSettings,
    "receipt": ReceiptSettings,
    "production": ProductionSettings,
}


class AllSettings(BaseModel):
    """Response of GET /settings, typed so the generated frontend client knows every field."""

    tax: TaxSettings
    service_charge: ServiceChargeSettings
    payment_methods: PaymentMethodSettings
    numbering: NumberingSettings
    session: SessionSettings
    stock: StockSettings
    purchasing: PurchasingSettings
    catalog: CatalogSettings
    pos: PosSettings
    kitchen: KitchenSettings
    receipt: ReceiptSettings
    production: ProductionSettings
