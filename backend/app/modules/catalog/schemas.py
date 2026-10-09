import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Language = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")]
Code = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9._-]{1,16}$")]
Sku = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9._/-]{1,64}$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ItemType = Literal["ingredient", "semi_finished", "menu"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UnitIn(Strict):
    code: Code
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    dimension: Literal["mass", "volume", "count"]


class UnitOut(UnitIn):
    id: uuid.UUID
    is_platform: bool


class CategoryIn(Strict):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    parent_id: uuid.UUID | None = None
    sort_order: int = Field(default=0, ge=0, le=100_000)
    is_active: bool = True


class CategoryOut(CategoryIn):
    id: uuid.UUID


class TranslationIn(Strict):
    language: Language
    name: Name
    description: Annotated[str, StringConstraints(max_length=2000)] | None = None


class ConversionIn(Strict):
    unit_id: uuid.UUID
    factor_to_base: Decimal = Field(gt=0, max_digits=18, decimal_places=6)


class ItemIn(Strict):
    sku: Sku
    type: ItemType
    category_id: uuid.UUID | None = None
    base_unit_id: uuid.UUID
    is_stocked: bool = True
    # Optional; derived from is_stocked when missing. "untracked" always means not stocked.
    tracking_mode: Literal["exact", "estimated", "untracked"] | None = None
    standard_cost: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    target_food_cost_bp: int | None = Field(default=None, gt=0, le=10_000)
    shelf_life_days: int | None = Field(default=None, gt=0, le=36500)
    storage_type: Literal["frozen", "chilled", "dry"] | None = None
    allergens: list[Annotated[str, StringConstraints(min_length=1, max_length=40)]] = Field(
        default_factory=list, max_length=20
    )
    translations: list[TranslationIn] = Field(min_length=1, max_length=10)
    conversions: list[ConversionIn] = Field(default_factory=list, max_length=20)

    @field_validator("translations")
    @classmethod
    def _one_per_language(cls, v: list[TranslationIn]) -> list[TranslationIn]:
        if len({t.language for t in v}) != len(v):
            raise ValueError("one translation per language")
        return v

    @model_validator(mode="after")
    def _tracking(self) -> "ItemIn":
        if self.tracking_mode is None:
            self.tracking_mode = "exact" if self.is_stocked else "untracked"
        self.is_stocked = self.tracking_mode != "untracked"
        return self

    @field_validator("conversions")
    @classmethod
    def _one_per_unit(cls, v: list[ConversionIn]) -> list[ConversionIn]:
        if len({c.unit_id for c in v}) != len(v):
            raise ValueError("one conversion per unit")
        return v


class ItemUpdate(ItemIn):
    version: int = Field(ge=1)
    is_active: bool = True


class TranslationOut(BaseModel):
    language: str
    name: str
    description: str | None


class ConversionOut(BaseModel):
    unit_id: uuid.UUID
    factor_to_base: Decimal


class ItemSummary(BaseModel):
    id: uuid.UUID
    sku: str
    type: ItemType
    name: str
    category_id: uuid.UUID | None
    base_unit_id: uuid.UUID
    is_active: bool
    photo_upload_id: uuid.UUID | None = None


class ItemOut(ItemSummary):
    is_stocked: bool
    tracking_mode: str = "exact"
    standard_cost: Decimal | None = None
    target_food_cost_bp: int | None = None
    shelf_life_days: int | None
    storage_type: str | None
    allergens: list[str]
    version: int
    translations: list[TranslationOut]
    conversions: list[ConversionOut]


# ─── Channels and prices (FR-CAT-004) ─────────────────────────────────────

# Same shape as the channel slugs tenant settings already use (service_charge.channels).
ChannelCode = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{1,40}$")]
ChannelKind = Literal["dine_in", "takeaway", "platform", "wholesale"]
MAX_PRICE = 10**12  # minor units; far above any menu price, far below bigint


class ChannelIn(Strict):
    code: ChannelCode
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    kind: ChannelKind
    platform: ChannelCode | None = None  # e.g. "grabfood"; required for kind "platform" only
    sort_order: int = Field(default=0, ge=0, le=100_000)
    is_active: bool = True

    @model_validator(mode="after")
    def _platform_only_for_platform_kind(self) -> "ChannelIn":
        if (self.kind == "platform") != (self.platform is not None):
            raise ValueError("platform is required for kind 'platform' and only for it")
        return self


class ChannelOut(ChannelIn):
    id: uuid.UUID


class PriceIn(Strict):
    channel_id: uuid.UUID
    valid_from: date
    # Strict: a JSON integer only; never coerce "25000" or 1.5 into money.
    price: int = Field(ge=0, le=MAX_PRICE, strict=True)


class PriceOut(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    channel_id: uuid.UUID
    valid_from: date
    price: int


class EffectivePrice(BaseModel):
    item_id: uuid.UUID
    valid_from: date
    price: int


# ─── Recipes (FR-CAT-005 to 007) ──────────────────────────────────────────

Qty = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4)]
MAX_BOM_LINES = 100


class BomLineIn(Strict):
    component_item_id: uuid.UUID
    qty: Qty
    unit_id: uuid.UUID
    waste_pct: Decimal = Field(default=Decimal(0), ge=0, lt=100, max_digits=5, decimal_places=2)


class BomIn(Strict):
    """A draft. Yield defaults to 1 base unit of the item (what a menu item needs)."""

    yield_qty: Qty | None = None
    yield_unit_id: uuid.UUID | None = None
    lines: list[BomLineIn] = Field(min_length=1, max_length=MAX_BOM_LINES)

    @field_validator("lines")
    @classmethod
    def _one_line_per_component(cls, v: list[BomLineIn]) -> list[BomLineIn]:
        if len({line.component_item_id for line in v}) != len(v):
            raise ValueError("one line per component")
        return v


class BomActivate(Strict):
    valid_from: date


class BomLineOut(BaseModel):
    component_item_id: uuid.UUID
    component_sku: str
    component_name: str
    qty: Decimal
    unit_id: uuid.UUID
    waste_pct: Decimal


class BomSummary(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    version: int
    status: Literal["draft", "active"]
    valid_from: date | None
    valid_to: date | None
    yield_qty: Decimal
    yield_unit_id: uuid.UUID


class BomOut(BomSummary):
    lines: list[BomLineOut]


class CostLine(BaseModel):
    """One ingredient after expanding nested recipes, per 1 base unit of the item."""

    item_id: uuid.UUID
    sku: str
    name: str
    base_qty: Decimal
    unit_code: str  # the ingredient's base unit
    unit_cost: Decimal | None  # per base unit; None: unknown yet or hidden
    cost: Decimal | None


class ChannelMargin(BaseModel):
    channel_id: uuid.UUID
    price: int  # list price, minor units
    net_price: int  # without included taxes
    margin: Decimal | None
    cost_pct: Decimal | None  # food cost (HPP) as % of the net price


class Costing(BaseModel):
    item_id: uuid.UUID
    on: date
    bom_id: uuid.UUID | None  # None: the item has no active recipe on that date
    lines: list[CostLine]
    cost: Decimal | None  # per 1 base unit; None when any ingredient cost is unknown
    missing_costs: list[uuid.UUID]
    cost_visible: bool
    margins: list[ChannelMargin]
