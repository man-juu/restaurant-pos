"""Food-cost alert (FR-CAT-012): a menu item whose theoretical food cost (HPP) on any sales
channel is above its target (the item's own, else the tenant default). Costs move with
receipts and price changes, so the alerts job re-checks; the alert names the channel and
the ingredient that costs the most. Only members who may see costs are told."""

import uuid
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Tenant
from app.core.notifications.service import Condition, sync
from app.core.settings import service as settings
from app.core.settings.schemas import CatalogSettings
from app.modules.catalog.boms import item_names
from app.modules.catalog.costing import costing, items_with_recipe
from app.modules.catalog.models import Channel, Item
from app.modules.catalog.permissions import COST_VIEW
from app.modules.catalog.prices import tenant_today

LINK = "/catalog"


async def scan_food_cost(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    default = cast(CatalogSettings, await settings.get_setting(db, tenant_id, "catalog"))
    today = await tenant_today(db, tenant_id)
    language = await db.scalar(select(Tenant.language).where(Tenant.id == tenant_id)) or "en"
    ids = await items_with_recipe(db, today)
    menu = (
        await db.execute(
            select(Item.id, Item.target_food_cost_bp).where(Item.id.in_(ids), Item.type == "menu")
        )
    ).all()
    channels = dict((await db.execute(select(Channel.id, Channel.name))).all())
    names = await item_names(db, tenant_id, language, {i for i, _ in menu})
    found = []
    for item_id, own in menu:
        target_bp = own or default.target_food_cost_bp
        if not target_bp:
            continue
        cost = await costing(
            db, tenant_id=tenant_id, item_id=item_id, on=today, language=language, show_cost=True
        )
        over = [m for m in cost.margins if m.cost_pct is not None and m.cost_pct * 100 > target_bp]
        if not over:
            continue
        worst = max(over, key=lambda m: m.cost_pct or 0)
        top = max(cost.lines, key=lambda ln: ln.cost or 0) if cost.lines else None
        found.append(
            Condition(
                None,
                item_id,
                details={
                    "item": names[item_id].name,
                    "channel": channels.get(worst.channel_id, ""),
                    "pct": f"{worst.cost_pct:.1f}",
                    "target": f"{target_bp / 100:.1f}",
                    "cause": top.name if top else "",
                },
                link=LINK,
            )
        )
    await sync(db, tenant_id, "food_cost_above_target", found, permission=COST_VIEW)
