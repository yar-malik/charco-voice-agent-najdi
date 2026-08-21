"""The ordering conversation."""

from __future__ import annotations

import itertools

import intents as intent_mod
import order as order_mod

_ticket_numbers = itertools.count(3182)


class Agent:
    """One instance per call."""

    GREETING = "مطعم شاركو، معك عمر. تحت أمرك."

    def __init__(self, caller: str = "unknown", menu: dict | None = None) -> None:
        self.order = order_mod.Order(menu=menu, caller=caller)
        self.asked_for_extras = False
        self.ticket: dict | None = None

    def greeting(self) -> str:
        return self.GREETING

    def reply(self, said: str) -> str:
        if self.ticket:
            return "طلبك راح للمطبخ. تحتاج شي ثاني؟"

        found = intent_mod.detect(said, self.order.menu)

        # A correction usually arrives glued to the thing it corrects, so the
        # amend has to be applied after the add in the same utterance.
        for intent in found:
            if intent.kind == "add":
                self.order.add(intent.sku, quantity=intent.quantity, options=intent.options)
            elif intent.kind == "amend":
                self.order.amend_last(**intent.options)
            elif intent.kind == "remove":
                self.order.remove_last()

        kinds = {intent.kind for intent in found}

        if "done" in kinds or ("confirm" in kinds and self.asked_for_extras):
            return self._send()

        if "unknown" in kinds and not self.order.lines:
            return "ما ضبطت معي. تقدر تعيد الطلب؟"

        if not self.asked_for_extras and self.order.lines:
            self.asked_for_extras = True
            return "تمام. أضيف لك مقبلات أو مشروبات؟"

        if "amend" in kinds:
            line = self.order.lines[-1]
            option = " ".join(line.labels_ar.values())
            return f"عدّلتها {option}. الإجمالي {self.order.total:.2f} ريال. تحتاج شي ثاني؟"

        return f"{self.order.read_back_ar()} تحتاج شي ثاني؟"

    def _send(self) -> str:
        if not self.order.lines:
            return "ما عندنا شي في الطلب. تحب تطلب شي؟"
        self.ticket = self.order.ticket(number=next(_ticket_numbers))
        self.order.sent = True
        return (
            f"{self.order.read_back_ar()} "
            f"جاهز خلال {self.ticket['ready_minutes']} دقيقة. شكراً لك."
        )
