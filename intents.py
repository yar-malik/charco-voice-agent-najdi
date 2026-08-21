"""Understanding a spoken order.

Matching against the menu, not against a general model of language. The menu
is small and known, so every item carries the phrases callers actually use for
it — including the ones a dictionary would not have, like "موية" for water.

The one case worth reading carefully is the correction. "بطاطس كبير، لا لا
خلها متوسط" is a single utterance containing an item, an option, a retraction
and a replacement. Split it wrong and the kitchen gets two portions of fries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TASHKEEL = re.compile(r"[ً-ْٰـ]")

# What a caller says to take something back, mid-sentence.
RETRACTIONS = ["لا لا", "لا،", "غلط", "الغي", "ألغي", "بدل", "خلها", "خليها", "عدل", "no wait", "actually"]

DONE = ["بس", "كذا بس", "خلاص", "هذا كل شي", "يكفي", "that's it", "thats it", "done"]

CONFIRM = ["إيه", "ايه", "نعم", "تمام", "زين", "أكيد", "اوكي", "أوكي", "yes", "ok"]

# Spoken quantities. Callers say "وجبتين", not "اثنين وجبة".
QUANTITY_WORDS = {
    "ثنتين": 2, "اثنين": 2, "اثنتين": 2, "وجبتين": 2, "حبتين": 2,
    "ثلاث": 3, "ثلاثة": 3, "تلاته": 3,
    "أربع": 4, "أربعة": 4, "اربع": 4,
    "خمس": 5, "خمسة": 5,
}

DUAL_SUFFIXES = ("تين", "ين")


@dataclass
class Intent:
    kind: str  # add | amend | remove | done | confirm | unknown
    sku: str | None = None
    quantity: int = 1
    options: dict[str, str] = field(default_factory=dict)
    text: str = ""


def normalise(text: str) -> str:
    text = TASHKEEL.sub("", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    return text.replace("ة", "ه").replace("ى", "ي").lower().strip()


def _quantity(said: str, phrase: str) -> int:
    """How many, from the words around the item."""
    for word, count in QUANTITY_WORDS.items():
        if normalise(word) in said:
            return count
    # "وجبتين" — the dual is a suffix, not a separate word
    head = said.split(phrase)[0] if phrase in said else said
    for token in head.split():
        if token.endswith(DUAL_SUFFIXES) and len(token) > 4:
            return 2
    digits = re.search(r"\b([1-9])\b", said)
    return int(digits.group(1)) if digits else 1


def _option_values(said: str, item: dict) -> dict[str, list[str]]:
    """Every option value the caller named, in the order they said them.

    Order is the whole point. "حار وعادي" is two portions; "كبير… لا لا
    متوسط" is one portion and a change of mind. Both look identical to a
    matcher that only records which words appeared.
    """
    found: dict[str, list[str]] = {}
    for option_name, spec in (item.get("options") or {}).items():
        hits: list[tuple[int, str]] = []
        for phrase, value in (spec.get("says_ar") or {}).items():
            at = said.find(normalise(phrase))
            while at != -1:
                hits.append((at, value))
                at = said.find(normalise(phrase), at + 1)
        if hits:
            hits.sort()
            ordered: list[str] = []
            for _, value in hits:
                if not ordered or ordered[-1] != value:
                    ordered.append(value)
            found[option_name] = ordered
    return found


def detect(said: str, menu: dict) -> list[Intent]:
    """Turn one utterance into the intents it contains, in order."""
    text = normalise(said)

    if any(normalise(w) in text for w in DONE):
        return [Intent(kind="done", text=said)]

    found: list[tuple[int, int, dict, str]] = []
    for item in menu["items"]:
        for phrase in item["says"]:
            at = text.find(normalise(phrase))
            if at != -1:
                found.append((at, at + len(normalise(phrase)), item, normalise(phrase)))
                break
    found.sort(key=lambda f: f[0])

    if not found:
        # An option with no item is a correction to the line just added.
        for item in menu["items"]:
            values = _option_values(text, item)
            if values and any(normalise(w) in text for w in RETRACTIONS):
                return [
                    Intent(
                        kind="amend",
                        options={name: vals[-1] for name, vals in values.items()},
                        text=said,
                    )
                ]
        if any(normalise(w) in text for w in CONFIRM):
            return [Intent(kind="confirm", text=said)]
        return [Intent(kind="unknown", text=said)]

    intents: list[Intent] = []
    for i, (at, item_end, item, phrase) in enumerate(found):
        # The words about this item run from the end of the previous item to
        # the start of the next. Arabic puts the count in front — "وجبتين
        # دجاج" — so a segment that begins at the item name has already lost
        # the quantity.
        start = found[i - 1][1] if i else 0
        stop = found[i + 1][0] if i + 1 < len(found) else len(text)
        segment = text[start:stop]

        quantity = _quantity(segment, phrase)
        values = _option_values(segment, item)
        retracted = any(normalise(w) in segment for w in RETRACTIONS)

        # "وحدة حارة ووحدة عادية" — one line each, because the kitchen cooks
        # them differently. But "كبير، لا لا متوسط" is one portion: the second
        # value replaces the first rather than joining it.
        split_on = next(
            (name for name, vals in values.items() if len(vals) > 1),
            None,
        )
        if split_on and not retracted and quantity >= len(values[split_on]):
            for value in values[split_on]:
                intents.append(
                    Intent(
                        kind="add",
                        sku=item["sku"],
                        quantity=1,
                        options={
                            name: (value if name == split_on else vals[-1])
                            for name, vals in values.items()
                        },
                        text=said,
                    )
                )
            continue

        intents.append(
            Intent(
                kind="add",
                sku=item["sku"],
                quantity=quantity,
                options={name: vals[-1] for name, vals in values.items()},
                text=said,
            )
        )
    return intents
