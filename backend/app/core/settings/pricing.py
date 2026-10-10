"""Document totals: service charge and taxes (FR-TEN-004, FR-TEN-005, docs/05 section 6).

Everything is integer minor units (IDR has none) and integer basis points, so there is no
float rounding anywhere. Rounding is half-up, once per tax per document, on the document's
taxable base (docs/05 rule 3). Tax-inclusive prices are split into net plus tax so that
net + taxes always equals what the customer paid, to the rupiah.
"""

import uuid
from dataclasses import dataclass, field

from app.core.settings.schemas import ServiceChargeSettings, TaxRule, TaxSettings

BP = 10_000


def round_half_up_div(numerator: int, denominator: int) -> int:
    """numerator / denominator rounded half away from zero, in integers only."""
    sign = -1 if (numerator < 0) != (denominator < 0) else 1
    n, d = abs(numerator), abs(denominator)
    return sign * ((2 * n + d) // (2 * d))


@dataclass(frozen=True)
class TaxLine:
    rule_id: str
    amount: int
    inclusive: bool


@dataclass(frozen=True)
class Totals:
    gross_lines: int  # sum of line totals as priced (may include tax)
    net: int  # lines without tax
    service_charge: int
    taxes: list[TaxLine] = field(default_factory=list)

    @property
    def tax_total(self) -> int:
        return sum(t.amount for t in self.taxes)

    @property
    def total(self) -> int:
        return self.net + self.service_charge + self.tax_total


def _applicable(rules: list[TaxRule], outlet_id: uuid.UUID | None) -> list[TaxRule]:
    return sorted(
        (
            r
            for r in rules
            if r.active
            and (r.outlet_ids is None or (outlet_id is not None and outlet_id in r.outlet_ids))
        ),
        key=lambda r: (r.order, r.id),
    )


def calculate(
    line_totals: list[int],
    *,
    tax: TaxSettings,
    service_charge: ServiceChargeSettings,
    channel: str,
    outlet_id: uuid.UUID | None = None,
) -> Totals:
    gross = sum(line_totals)
    rules = _applicable(tax.rules, outlet_id)
    inclusive = [r for r in rules if r.price_includes_tax]
    exclusive = [r for r in rules if not r.price_includes_tax]

    # 1. Split inclusive tax out of the prices: net = gross / (1 + sum of inclusive rates).
    incl_bp = sum(r.rate_bp for r in inclusive)
    net = round_half_up_div(gross * BP, BP + incl_bp)
    amounts = [round_half_up_div(net * rule.rate_bp, BP) for rule in inclusive]
    if inclusive:
        # Rounding can leave net + taxes a rupiah off the price paid. The difference goes to
        # the largest-rate tax (never to a 0 % one, which would turn negative), so
        # net + taxes == gross exactly.
        largest = max(range(len(inclusive)), key=lambda i: inclusive[i].rate_bp)
        amounts[largest] += gross - net - sum(amounts)
    tax_lines = [TaxLine(r.id, a, inclusive=True) for r, a in zip(inclusive, amounts, strict=True)]

    # 2. Service charge on the net amount, when enabled for this channel.
    sc_on = service_charge.enabled and (
        not service_charge.channels or channel in service_charge.channels
    )
    sc = round_half_up_div(net * service_charge.rate_bp, BP) if sc_on else 0

    # 3. Exclusive taxes on net (plus service charge where the rule says so), in rule order.
    for rule in exclusive:
        base = net + (sc if rule.applies_to_service_charge and service_charge.before_tax else 0)
        tax_lines.append(
            TaxLine(rule.id, round_half_up_div(base * rule.rate_bp, BP), inclusive=False)
        )

    return Totals(gross_lines=gross, net=net, service_charge=sc, taxes=tax_lines)
