"""Recipe expansion and theoretical cost (FR-CAT-005, FR-CAT-007).

`explode` turns quantities of menu or semi-finished items into the ingredients they use,
through nested recipes, as exact decimals per base unit. Sales consumption (slice 1k) and
production (slice 1g) use the same function, so the screen and the stock ledger agree.

Costs come from a pluggable source: the inventory module (slice 1e) registers its moving
average costs here. The catalog never reads inventory tables (module boundaries, CLAUDE.md
rule 4). Until a source is registered, every cost is unknown and shown as such.
"""

import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from typing import cast

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.settings import service as settings
from app.core.settings.pricing import calculate
from app.core.settings.schemas import ServiceChargeSettings, TaxSettings
from app.modules.catalog.boms import MAX_DEPTH, active_boms, item_names
from app.modules.catalog.models import Bom, BomLine, Channel, Item, ItemPrice
from app.modules.catalog.schemas import ChannelMargin, Costing, CostLine
from app.modules.catalog.service import InvalidCatalogReference
from app.modules.catalog.units import base_factors

CostSource = Callable[[AsyncSession, set[uuid.UUID]], Awaitable[dict[uuid.UUID, Decimal]]]
QTY = Decimal("0.000001")
MONEY = Decimal("0.01")
HUNDRED = Decimal(100)


async def _no_costs(_db: AsyncSession, _ids: set[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    return {}


_cost_source: CostSource = _no_costs


def set_cost_source(source: CostSource) -> None:
    """Called once by the inventory module at start-up (slice 1e)."""
    global _cost_source
    _cost_source = source


async def _lines_by_bom(db: AsyncSession, boms: list[Bom]) -> dict[uuid.UUID, list[BomLine]]:
    out: dict[uuid.UUID, list[BomLine]] = defaultdict(list)
    stmt = select(BomLine).where(BomLine.bom_id.in_([b.id for b in boms]))
    for line in (await db.execute(stmt)).scalars():
        out[line.bom_id].append(line)
    return out


async def _expand_level(
    db: AsyncSession, frontier: dict[uuid.UUID, Decimal], boms: dict[uuid.UUID, Bom]
) -> dict[uuid.UUID, Decimal]:
    """One level down: what the items with a recipe need, per base unit of each."""
    lines = await _lines_by_bom(db, list(boms.values()))
    pairs = {(ln.component_item_id, ln.unit_id) for ls in lines.values() for ln in ls}
    pairs |= {(b.item_id, b.yield_unit_id) for b in boms.values()}
    factors = await base_factors(db, pairs)
    needed: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for item_id, bom in boms.items():
        batch = bom.yield_qty * factors[(item_id, bom.yield_unit_id)]
        for ln in lines[bom.id]:
            gross = ln.qty * factors[(ln.component_item_id, ln.unit_id)]
            gross /= 1 - ln.waste_pct / HUNDRED  # waste is lost in preparation
            needed[ln.component_item_id] += frontier[item_id] * gross / batch
    return needed


async def explode(
    db: AsyncSession, quantities: dict[uuid.UUID, Decimal], on: date
) -> dict[uuid.UUID, Decimal]:
    """Base quantities of every ingredient (or semi-finished item without a recipe) needed
    for `quantities` (base units per item) under the recipes in force on `on`."""
    leaves: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    frontier = dict(quantities)
    for _ in range(MAX_DEPTH + 1):
        if not frontier:
            return dict(leaves)
        boms = await active_boms(db, set(frontier), on)
        for item_id, qty in frontier.items():
            if item_id not in boms:
                leaves[item_id] += qty
        frontier = await _expand_level(db, frontier, boms) if boms else {}
    raise InvalidCatalogReference("bom_too_deep")


async def _list_prices(
    db: AsyncSession, item_id: uuid.UUID, on: date
) -> list[tuple[uuid.UUID, int]]:
    stmt = (
        select(ItemPrice.channel_id, ItemPrice.price)
        .join(Channel, Channel.id == ItemPrice.channel_id)
        .where(
            ItemPrice.item_id == item_id,
            ItemPrice.outlet_id.is_(None),
            ItemPrice.valid_from <= on,
            or_(ItemPrice.valid_to.is_(None), ItemPrice.valid_to >= on),
            Channel.is_active,
        )
        .order_by(ItemPrice.channel_id, ItemPrice.valid_from.desc())
        .ext(distinct_on(ItemPrice.channel_id))
    )
    return [(c, p) for c, p in (await db.execute(stmt)).all()]


async def _margins(
    db: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID, on: date, cost: Decimal | None
) -> list[ChannelMargin]:
    tax = cast(TaxSettings, await settings.get_setting(db, tenant_id, "tax"))
    no_service = ServiceChargeSettings(enabled=False)
    out = []
    for channel_id, price in await _list_prices(db, item_id, on):
        # Margin is on the price without included taxes (the tax belongs to the state).
        net = calculate([price], tax=tax, service_charge=no_service, channel="").net
        margin = None if cost is None else (Decimal(net) - cost).quantize(MONEY)
        pct = None if cost is None or net <= 0 else (cost * HUNDRED / net).quantize(MONEY)
        out.append(
            ChannelMargin(
                channel_id=channel_id, price=price, net_price=net, margin=margin, cost_pct=pct
            )
        )
    return out


async def _with_standard_costs(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    """Ledger averages first; an item's standard cost fills the gap (gas, or before the first
    purchase), so one such line does not make the whole recipe cost unknown."""
    costs = await _cost_source(db, ids)
    if missing := ids - costs.keys():
        stmt = select(Item.id, Item.standard_cost).where(
            Item.id.in_(missing), Item.standard_cost.is_not(None)
        )
        for item_id, cost in (await db.execute(stmt)).all():
            if cost is not None:
                costs[item_id] = cost
    return costs


async def costing(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    on: date,
    language: str,
    show_cost: bool,
) -> Costing:
    """Ingredients and theoretical cost of 1 base unit of the item; margins per channel.
    Without catalog.cost.view, quantities are shown but costs and margins are not."""
    if await db.get(Item, item_id) is None:
        raise NotFoundError("item_not_found")
    bom = (await active_boms(db, {item_id}, on)).get(item_id)
    leaves = await explode(db, {item_id: Decimal(1)}, on) if bom else {}
    names = await item_names(db, tenant_id, language, leaves)
    costs = await _with_standard_costs(db, set(leaves)) if show_cost else {}
    lines = [
        CostLine(
            item_id=i,
            sku=names[i].sku,
            name=names[i].name,
            base_qty=qty.quantize(QTY),
            unit_code=names[i].unit_code,
            unit_cost=costs.get(i),
            cost=(qty * costs[i]).quantize(MONEY) if i in costs else None,
        )
        for i, qty in sorted(leaves.items(), key=lambda kv: names[kv[0]].name)
    ]
    missing = sorted(i for i in leaves if i not in costs) if show_cost else []
    known = bool(bom) and not missing
    total = sum((ln.cost or Decimal(0) for ln in lines), Decimal(0)) if known else None
    return Costing(
        item_id=item_id,
        on=on,
        bom_id=bom.id if bom else None,
        lines=lines,
        cost=total if show_cost else None,
        missing_costs=missing,
        cost_visible=show_cost,
        margins=await _margins(db, tenant_id, item_id, on, total) if show_cost else [],
    )


async def recipe_needs(
    db: AsyncSession, item_id: uuid.UUID, qty: Decimal, on: date
) -> tuple[uuid.UUID | None, dict[uuid.UUID, Decimal]]:
    """One level of the recipe in force on `on`: (recipe id, base quantity per component)
    to make `qty` base units of `item_id`. Production consumes this level only, because the
    semi-finished components were produced and stocked separately."""
    boms = await active_boms(db, {item_id}, on)
    if item_id not in boms:
        return None, {}
    return boms[item_id].id, dict(await _expand_level(db, {item_id: qty}, boms))


async def unit_needs(
    db: AsyncSession, ids: set[uuid.UUID], on: date
) -> dict[uuid.UUID, dict[uuid.UUID, Decimal]]:
    """For each item with a recipe in force: base quantity of each direct component per one
    base unit of the item (waste included). One query per step, whatever the item count."""
    boms = await active_boms(db, ids, on)
    if not boms:
        return {}
    lines = await _lines_by_bom(db, list(boms.values()))
    pairs = {(ln.component_item_id, ln.unit_id) for ls in lines.values() for ln in ls}
    pairs |= {(b.item_id, b.yield_unit_id) for b in boms.values()}
    factors = await base_factors(db, pairs)
    out: dict[uuid.UUID, dict[uuid.UUID, Decimal]] = {}
    for item_id, bom in boms.items():
        batch = bom.yield_qty * factors[(item_id, bom.yield_unit_id)]
        need: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
        for ln in lines[bom.id]:
            gross = ln.qty * factors[(ln.component_item_id, ln.unit_id)]
            need[ln.component_item_id] += gross / (1 - ln.waste_pct / HUNDRED) / batch
        out[item_id] = dict(need)
    return out


async def items_with_recipe(db: AsyncSession, on: date) -> set[uuid.UUID]:
    """Active items that have a recipe in force on `on`."""
    stmt = (
        select(Bom.item_id)
        .join(Item, Item.id == Bom.item_id)
        .where(
            Item.is_active,
            Bom.status == "active",
            Bom.valid_from <= on,
            or_(Bom.valid_to.is_(None), Bom.valid_to >= on),
        )
    )
    return set(await db.scalars(stmt))


async def consumption(
    db: AsyncSession, quantities: dict[uuid.UUID, Decimal], on: date
) -> tuple[dict[uuid.UUID, Decimal], dict[uuid.UUID, uuid.UUID]]:
    """What a sale takes out of stock (FR-SAL-002): recipes are expanded only through items
    that are not stocked themselves (a menu item, a sauce made to order); a stocked item
    (sambal made in the central kitchen) is taken as it is. Returns (base quantity per
    stocked item, recipe id used per expanded item)."""
    from app.modules.catalog.outlet_menu import expand_combos  # combos first (FR-CAT-011)

    taken: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    used: dict[uuid.UUID, uuid.UUID] = {}
    frontier = await expand_combos(db, dict(quantities))
    for _ in range(MAX_DEPTH + 1):
        if not frontier:
            return dict(taken), used
        rows = (
            await db.execute(select(Item.id, Item.is_stocked).where(Item.id.in_(frontier)))
        ).all()
        stocked = {i for i, s in rows if s}
        boms = await active_boms(db, set(frontier) - stocked, on)
        for item_id, qty in frontier.items():
            if item_id not in boms:
                taken[item_id] += qty  # stocked, or nothing to expand: taken as is
        used.update({i: b.id for i, b in boms.items()})
        frontier = await _expand_level(db, frontier, boms) if boms else {}
    raise InvalidCatalogReference("bom_too_deep")
