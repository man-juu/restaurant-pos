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


SETTINGS: dict[str, type[Strict]] = {
    "tax": TaxSettings,
    "service_charge": ServiceChargeSettings,
    "payment_methods": PaymentMethodSettings,
    "numbering": NumberingSettings,
    "session": SessionSettings,
    "stock": StockSettings,
}


class AllSettings(BaseModel):
    """Response of GET /settings, typed so the generated frontend client knows every field."""

    tax: TaxSettings
    service_charge: ServiceChargeSettings
    payment_methods: PaymentMethodSettings
    numbering: NumberingSettings
    session: SessionSettings
    stock: StockSettings
