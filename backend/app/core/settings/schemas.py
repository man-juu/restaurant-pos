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
    # FR-PUR-009 three-way match: a billed unit price may exceed the PO price by this much
    # (basis points) before it is flagged; and whether a flagged bill can still be paid.
    bill_price_tolerance_bp: int = Field(default=0, ge=0, le=10_000)
    block_mismatched_payment: bool = False


class PosSettings(Strict):
    """FR-SAL-006, 009: how the cashier screen works for this business."""

    require_shift: bool = True  # payments need an open cash shift
    cash_rounding_step: int = Field(default=0, ge=0, le=100_000)  # 0 = off; e.g. 100 for Rp 100
    tips_enabled: bool = False
    # FR-SAL-008: a voided line that was already sent was cooked: write its ingredients off as
    # waste, or not (when the kitchen reuses it).
    void_stock_effect: Literal["waste", "none"] = "waste"
    # FR-SAL-013: tills may take orders while the connection is down and sync them later.
    offline_enabled: bool = True


class KitchenSettings(Strict):
    """FR-KDS-004: when a ticket counts as late, and how long a bumped one can be recalled."""

    late_minutes: int = Field(default=15, ge=1, le=240)
    recall_minutes: int = Field(default=30, ge=1, le=24 * 60)


class ProductionSettings(Strict):
    """FR-PRD-008: whether open branch requests (transfers) add to the central kitchen's prep
    list, on top of its own par levels."""

    prep_includes_requests: bool = True


class WholesaleSettings(Strict):
    """FR-SAL-011: when wholesale invoices fall due unless the invoice says otherwise."""

    payment_terms_days: int = Field(default=14, ge=0, le=365)


class PlanningSettings(Strict):
    """FR-INV-018, FR-PRD-005, FR-PUR-007: how forecasts, order quantities, the production
    plan and vendor suggestions are worked out. Every business tunes these to its own way."""

    forecast_weeks: int = Field(default=8, ge=2, le=26)  # history the forecast looks at
    forecast_min_days: int = Field(default=28, ge=7, le=180)  # less history: plain averages
    order_cost: int = Field(default=0, ge=0, le=10**12)  # minor units per order; 0 = no EOQ
    holding_cost_pct: int = Field(default=25, ge=1, le=200)  # of unit cost, per year
    plan_days: int = Field(default=3, ge=1, le=14)  # how far ahead the production plan looks
    reliability_weight_pct: int = Field(default=30, ge=0, le=200)  # vendor: late or short
    lead_day_cost_bp: int = Field(default=0, ge=0, le=5000)  # vendor: price added per lead day


class TransferSettings(Strict):
    """FR-TRF-006: what one outlet charges another for goods it sends. "cost": no charge
    beyond stock value (one legal entity). "cost_plus": stock value plus a markup, shown on
    the delivery note and in the charges report (outlets that are separate businesses)."""

    price_mode: Literal["cost", "cost_plus"] = "cost"
    markup_bp: int = Field(default=0, ge=0, le=100_000)


class ReportSettings(Strict):
    """FR-RPT-007: how popular an item must be to count as popular in menu engineering, as
    a share of a fair share of portions sold (70 % is the usual rule)."""

    menu_popularity_pct: int = Field(default=70, ge=10, le=200)


class FinanceSettings(Strict):
    """FR-FIN-003: journal sales, stock, purchases and payments automatically once the books
    are set up. Off: only manual journals (an accountant keeps the books elsewhere)."""

    auto_journals: bool = True
    # Owner 2026-10-10: most owners have no accountant. "simple" shows money in and out,
    # profit and loss, and money accounts; "advanced" adds the books, receivables,
    # platform settlements and prime cost.
    mode: Literal["simple", "advanced"] = "simple"


class TablesSettings(Strict):
    """FR-TBL-006 to 008: how long a party usually stays; after how many minutes a booking
    whose guests have not come is shown as late (staff then mark it a no-show)."""

    default_dwell_minutes: int = Field(default=90, ge=15, le=600)
    no_show_after_minutes: int = Field(default=15, ge=0, le=240)
    allow_overbooking: bool = False  # off: a table is never booked twice for the same time


class ReceiptSettings(Strict):
    """FR-SAL-010: what the printed receipt says around the sale, and the paper width."""

    header: str = Field(default="", max_length=300)  # e.g. tax id, phone, Instagram
    footer: str = Field(default="", max_length=300)  # e.g. "Terima kasih!"
    paper_mm: Literal[58, 80] = 58  # most Bluetooth printers in Indonesia are 58 mm


class LoyaltySettings(Strict):
    """FR-SAL-016: how guests earn points and what a point is worth when turned into a voucher.
    Every number is the business's own choice."""

    earn_per: int = Field(default=10_000, ge=1, le=10**9)  # net sales per point earned
    point_value: int = Field(default=100, ge=1, le=10**9)  # money one point is worth
    min_redeem_points: int = Field(default=100, ge=1, le=10**9)
    voucher_valid_days: int = Field(default=90, ge=0, le=3650)  # 0 = never expires


class BookingSettings(Strict):
    """FR-TBL-010: what guests may book on the public booking page, and the reminder text
    staff send. Times are minutes after midnight in the business's time zone."""

    opens_min: int = Field(default=600, ge=0, le=1439)  # 10:00, first bookable time
    closes_min: int = Field(default=1260, ge=1, le=1440)  # 21:00, last bookable start
    slot_minutes: int = Field(default=30, ge=5, le=240)
    min_notice_minutes: int = Field(default=60, ge=0, le=10_080)
    days_ahead: int = Field(default=30, ge=1, le=365)
    max_party: int = Field(default=8, ge=1, le=200)
    max_open_per_phone: int = Field(default=2, ge=1, le=20)  # stops one number booking a lot
    reminder_text: str = Field(
        default="Hi {name}, see you at {outlet} on {date} at {time} for {party}.",
        max_length=500,
    )

    @model_validator(mode="after")
    def _hours(self) -> "BookingSettings":
        if self.closes_min <= self.opens_min:
            raise ValueError("closes_min must be after opens_min")
        return self


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
    "tables": TablesSettings,
    "finance": FinanceSettings,
    "wholesale": WholesaleSettings,
    "planning": PlanningSettings,
    "transfers": TransferSettings,
    "reports": ReportSettings,
    "loyalty": LoyaltySettings,
    "booking": BookingSettings,
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
    tables: TablesSettings
    finance: FinanceSettings
    wholesale: WholesaleSettings
    planning: PlanningSettings
    transfers: TransferSettings
    reports: ReportSettings
    loyalty: LoyaltySettings
    booking: BookingSettings
