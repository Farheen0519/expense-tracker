import os
from datetime import date

import httpx
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="Expense Tracker", page_icon="💸", layout="centered")


def api(method: str, path: str, **kwargs):
    """Call the FastAPI backend. Shows an error and returns None on failure."""
    try:
        r = httpx.request(method, f"{API_URL}{path}", timeout=120, **kwargs)
    except httpx.ConnectError:
        st.error("Cannot reach the API. Start it with: python -m uvicorn app.main:app --reload")
        return None
    except httpx.TimeoutException:
        st.error("The request timed out. The model may still be loading, try again.")
        return None
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        st.error(str(detail))
        return None
    return r


# ---------- Sidebar: status ----------
with st.sidebar:
    st.header("Status")
    health = api("GET", "/health")
    if health:
        h = health.json()
        st.write("API: ✅")
        st.write(f"Ollama: {'✅' if h['ollama'] else '❌ not running'}")
        if h["ollama"]:
            st.write(f"Model `{h['model']}`: {'✅' if h['model_available'] else '❌ not pulled'}")
    st.caption(f"API: {API_URL}")

# Allowed categories / payment methods come from the API, not hardcoded here
meta_resp = api("GET", "/meta")
if meta_resp is None:
    st.stop()
meta = meta_resp.json()
CATEGORIES = meta["categories"]
PAYMENT_METHODS = meta["payment_methods"]

st.title("💸 Expense Tracker")
tab_add, tab_list = st.tabs(["Add expense", "My expenses"])

# ---------- Tab 1: add ----------
with tab_add:
    if msg := st.session_state.pop("saved_msg", None):
        st.success(msg)

    prompt = st.text_area(
        "Describe your expense",
        placeholder="spent 450 on lunch with Rahul yesterday via UPI",
        height=100,
    )
    if st.button("Parse", type="primary", disabled=not prompt.strip()):
        with st.spinner("Reading your expense..."):
            r = api("POST", "/expenses/parse", json={"prompt": prompt})
        if r:
            preview = r.json()
            preview["raw_prompt"] = prompt.strip()
            st.session_state["preview"] = preview
            # new number each parse, so the form below resets to the new values
            st.session_state["preview_n"] = st.session_state.get("preview_n", 0) + 1

    p = st.session_state.get("preview")
    if p:
        n = st.session_state["preview_n"]
        st.subheader("Check and confirm")
        st.caption("Fix anything the model got wrong before saving.")
        with st.form(f"confirm_{n}"):
            amount = st.number_input(
                "Amount (₹)", min_value=0.01, value=float(p["amount"]), step=10.0, format="%.2f"
            )
            description = st.text_input("Description", value=p["description"])
            merchant = st.text_input("Merchant / person", value=p.get("merchant") or "")
            c1, c2 = st.columns(2)
            category = c1.selectbox(
                "Category",
                CATEGORIES,
                index=CATEGORIES.index(p["category"]) if p["category"] in CATEGORIES else 0,
            )
            payment = c2.selectbox(
                "Payment method",
                PAYMENT_METHODS,
                index=(
                    PAYMENT_METHODS.index(p["payment_method"])
                    if p["payment_method"] in PAYMENT_METHODS
                    else 0
                ),
            )
            exp_date = st.date_input(
                "Date", value=date.fromisoformat(p["expense_date"]), max_value=date.today()
            )
            save = st.form_submit_button("Save expense", type="primary")

        if save:
            body = {
                "amount": amount,
                "category": category,
                "description": description.strip() or "Expense",
                "merchant": merchant.strip() or None,
                "payment_method": payment,
                "expense_date": exp_date.isoformat(),
                "raw_prompt": p.get("raw_prompt"),
            }
            r = api("POST", "/expenses", json=body)
            if r:
                st.session_state["preview"] = None
                st.session_state["saved_msg"] = f"Saved ₹{amount:,.2f} for {body['description']}."
                st.rerun()

        if st.button("Discard"):
            st.session_state["preview"] = None
            st.rerun()


# ---------- Tab 2: list ----------
with tab_list:
    f1, f2, f3 = st.columns(3)
    category_filter = f1.selectbox("Category", ["All"] + CATEGORIES)
    start = f2.date_input("From", value=date.today().replace(day=1))
    end = f3.date_input("To", value=date.today())

    params = {"limit": 500, "start_date": start.isoformat(), "end_date": end.isoformat()}
    if category_filter != "All":
        params["category"] = category_filter

    r = api("GET", "/expenses", params=params)
    if r:
        rows = r.json()
        if not rows:
            st.info("No expenses in this range.")
        else:
            df = pd.DataFrame(rows)[
                ["id", "expense_date", "amount", "category", "description", "merchant", "payment_method"]
            ]
            st.metric("Total", f"₹{df['amount'].sum():,.2f}", help=f"{len(df)} expenses")
            st.dataframe(df, hide_index=True)

            st.divider()
            labels = {
                row["id"]: f"#{row['id']} · {row['expense_date']} · ₹{row['amount']:,.2f} · {row['description']}"
                for row in rows
            }
            to_delete = st.selectbox("Delete an expense", list(labels), format_func=labels.get)
            if st.button("Delete"):
                if api("DELETE", f"/expenses/{to_delete}") is not None:
                    st.rerun()