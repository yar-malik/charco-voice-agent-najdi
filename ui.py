"""A Streamlit tester for the ordering agent.

    streamlit run ui.py

Type an order in Arabic, hear the reply, and watch the ticket build up beside
it. Useful for handing to someone who is not going to run a phone line but
does need to tell you whether the agent understood them.
"""

from __future__ import annotations

import json

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

import agent as agent_mod  # noqa: E402
import voho  # noqa: E402

st.set_page_config(page_title="Charco — Najdi ordering agent", page_icon="🍗")

if "agent" not in st.session_state:
    st.session_state.agent = agent_mod.Agent(caller="+966500000000")
    st.session_state.turns = [("agent", st.session_state.agent.greeting())]

convo: agent_mod.Agent = st.session_state.agent

st.title("مطعم شاركو")
st.caption("Order in Saudi Arabic. The agent replies in Najdi, and the ticket builds on the right.")

speak = st.sidebar.toggle("Speak the replies", value=True)
st.sidebar.caption(f"Voice: `{voho.DEFAULT_VOICE}` · model `{voho.DEFAULT_MODEL}`")
if st.sidebar.button("Start a new call"):
    st.session_state.clear()
    st.rerun()

left, right = st.columns([3, 2])

with left:
    for who, text in st.session_state.turns:
        with st.chat_message("assistant" if who == "agent" else "user"):
            st.markdown(f"<div dir='rtl'>{text}</div>", unsafe_allow_html=True)

    if said := st.chat_input("اكتب طلبك…"):
        st.session_state.turns.append(("caller", said))
        reply = convo.reply(said)
        st.session_state.turns.append(("agent", reply))

        if speak:
            try:
                st.session_state.audio = voho.speak(reply)
            except voho.VohoError as exc:
                st.session_state.audio = None
                st.warning(str(exc))
        st.rerun()

    if st.session_state.get("audio"):
        st.audio(st.session_state.audio, format="audio/mp3")

with right:
    st.subheader("Ticket")
    if not convo.order.lines:
        st.caption("Nothing ordered yet.")
    for line in convo.order.lines:
        options = " · ".join(line.labels_ar.values())
        st.write(f"**{line.quantity}×** {line.name_en} {options} — {line.total:.2f}")
    if convo.order.lines:
        st.divider()
        st.write(f"VAT 15% — {convo.order.vat:.2f}")
        st.write(f"**Total — {convo.order.total:.2f} SAR**")
    if convo.ticket:
        st.success(f"Sent to the kitchen · ticket #{convo.ticket['ticket']}")
        st.code(json.dumps(convo.ticket, ensure_ascii=False, indent=2), language="json")
