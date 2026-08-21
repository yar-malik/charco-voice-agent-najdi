"""The order, and the arithmetic under it.

The interesting part of a phone order is not adding items. It is the
correction — "بطاطس كبير. لا لا، خلها متوسط" — which arrives in the same
breath as the thing it corrects. An order model that can only append forces
the agent to start again; this one can amend the last line, which is what the
caller expects because it is what a person behind the counter would do.

Prices are VAT-inclusive, the way they are displayed in Saudi Arabia. The VAT
line on the receipt is the tax already contained in the total, not something
added on top of it — get that backwards and every receipt is wrong by 15%.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

MENU_PATH = Path("menu.json")


def load_menu(path: Path = MENU_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class Line:
    sku: str
    name_ar: str
    name_en: str
    quantity: int
    unit_price: float
    options: dict[str, str] = field(default_factory=dict)
    #: Arabic label for each chosen option, filled in by Order.add — the
    #: option values are English identifiers and must never be read out.
    labels_ar: dict[str, str] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return round(self.unit_price * self.quantity, 2)

    def spoken_ar(self) -> str:
        parts = [self.name_ar]
        if self.quantity > 1:
            parts.insert(0, f"{self.quantity}")
        if self.labels_ar:
            parts.append(" ".join(self.labels_ar.values()))
        return " ".join(parts)


class Order:
    """One caller's order, from greeting to ticket."""

    def __init__(self, menu: dict | None = None, *, caller: str = "unknown") -> None:
        self.menu = menu or load_menu()
        self.caller = caller
        self.lines: list[Line] = []
        self.sent = False
        self._by_sku = {item["sku"]: item for item in self.menu["items"]}

    # ------------------------------------------------------------ pricing

    def _unit_price(self, item: dict, options: dict[str, str]) -> float:
        price = float(item["price"])
        for option_name, chosen in options.items():
            spec = (item.get("options") or {}).get(option_name) or {}
            price += float((spec.get("price_delta") or {}).get(chosen, 0.0))
        return round(price, 2)

    @property
    def total(self) -> float:
        return round(sum(line.total for line in self.lines), 2)

    @property
    def vat(self) -> float:
        """The VAT already inside the total, not an addition to it."""
        rate = float(self.menu["restaurant"]["vat_rate"])
        return round(self.total - self.total / (1 + rate), 2)

    # ------------------------------------------------------------- edits

    def add(self, sku: str, *, quantity: int = 1, options: dict[str, str] | None = None) -> Line:
        item = self._by_sku[sku]
        chosen = dict(options or {})
        # Fill in anything the caller did not specify, so a line always prices.
        for option_name, spec in (item.get("options") or {}).items():
            chosen.setdefault(option_name, spec.get("default", ""))
        chosen = {k: v for k, v in chosen.items() if v}

        line = Line(
            sku=sku,
            name_ar=item["name_ar"],
            name_en=item["name_en"],
            quantity=quantity,
            unit_price=self._unit_price(item, chosen),
            options=chosen,
            labels_ar=self._labels(item, chosen),
        )
        self.lines.append(line)
        return line

    def _labels(self, item: dict, options: dict[str, str]) -> dict[str, str]:
        labels = {}
        for option_name, value in options.items():
            spec = (item.get("options") or {}).get(option_name) or {}
            labels[option_name] = (spec.get("label_ar") or {}).get(value, value)
        return labels

    def amend_last(self, **options: str) -> Line | None:
        """Change an option on the most recent line, and reprice it.

        This is the "no wait, make it medium" case. Nothing is removed and
        re-added, because the caller does not think of it as two actions.
        """
        if not self.lines:
            return None
        line = self.lines[-1]
        line.options.update(options)
        item = self._by_sku[line.sku]
        line.unit_price = self._unit_price(item, line.options)
        line.labels_ar = self._labels(item, line.options)
        return line

    def remove_last(self) -> Line | None:
        return self.lines.pop() if self.lines else None

    # ------------------------------------------------------------ output

    def read_back_ar(self) -> str:
        """What the agent says before sending it to the kitchen."""
        if not self.lines:
            return "ما عندنا شي في الطلب لين الحين."
        items = "، و".join(line.spoken_ar() for line in self.lines)
        return f"طلبك: {items}. الإجمالي {self.total:.2f} ريال."

    def ticket(self, *, number: int, ready_minutes: int = 20) -> dict:
        """The ticket, in the shape a point-of-sale system expects."""
        return {
            "ticket": number,
            "caller": self.caller,
            "lines": [
                {
                    "sku": line.sku,
                    "name": line.name_en,
                    "name_ar": line.name_ar,
                    "quantity": line.quantity,
                    "options": line.options,
                    "total": line.total,
                }
                for line in self.lines
            ],
            "vat": self.vat,
            "total": self.total,
            "currency": "SAR",
            "ready_minutes": ready_minutes,
            "fulfilment": "pickup",
        }
