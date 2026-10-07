import uuid
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

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


class ItemOut(ItemSummary):
    is_stocked: bool
    shelf_life_days: int | None
    storage_type: str | None
    allergens: list[str]
    version: int
    translations: list[TranslationOut]
    conversions: list[ConversionOut]
