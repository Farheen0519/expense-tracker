"""Turns a free-text expense sentence into a validated ParsedExpense using Ollama.

- Ollama's `format` parameter takes a JSON schema, so the model can only emit
  valid JSON with allowed category / payment values.
- The model never does date math. It says "today" / "yesterday" /
  "day_before_yesterday" or copies an explicit date; Python resolves the rest.
"""

from datetime import date, datetime, timedelta
from typing import Literal

import httpx
from pydantic import BaseModel, ValidationError

from .config import OLLAMA_MODEL, OLLAMA_URL
from .schemas import CATEGORIES, PAYMENT_METHODS, Category, ParsedExpense, PaymentMethod


class LLMError(Exception):
    """Raised when the model can't be reached or returns something unusable."""


class LLMExtraction(BaseModel):
    """The raw shape the model must produce (also sent to Ollama as the JSON schema)."""

    amount: float
    category: Category
    description: str
    merchant: str  # "" when there is none
    payment_method: PaymentMethod
    relative_day: Literal["today", "yesterday", "day_before_yesterday"]
    explicit_date: str  # "YYYY-MM-DD" or ""


def _system_prompt(today: date) -> str:
    return f"""You extract expense details from a short sentence written by an Indian user.
Today's date is {today.isoformat()}. All amounts are in Indian rupees (INR).

Return JSON with these fields:
- amount: number only, no currency symbol. "2k" = 2000, "1.5k" = 1500, "2 lakh" = 200000.
- category: one of {CATEGORIES}.
- description: a short phrase (2-6 words), e.g. "Lunch", "Auto fare", "Electricity bill".
- merchant: the shop, app or person if mentioned (e.g. "Swiggy", "Rahul"), otherwise "".
- payment_method: one of {PAYMENT_METHODS}. Use "UPI" for GPay/PhonePe/Paytm. Use "Other" if not mentioned.
- relative_day: "today", "yesterday" or "day_before_yesterday". Use "today" if no day is mentioned.
- explicit_date: only if a specific calendar date is stated, as YYYY-MM-DD (assume the year {today.year} if none is given). Otherwise "".

Category guide: Food = meals, groceries, snacks, tea/coffee, Swiggy/Zomato. Transport = auto, cab, Uber, Ola, bus, metro, petrol, fuel. Bills = rent, electricity, water, recharge, internet, EMI, subscriptions. Shopping = clothes, gadgets, household items. Health = medicine, doctor, gym. Entertainment = movies, games, outings, OTT. Other = anything else.

Examples:
"spent 450 on lunch with Rahul yesterday via UPI" ->
{{"amount": 450, "category": "Food", "description": "Lunch", "merchant": "Rahul", "payment_method": "UPI", "relative_day": "yesterday", "explicit_date": ""}}
"auto 80 cash" ->
{{"amount": 80, "category": "Transport", "description": "Auto fare", "merchant": "", "payment_method": "Cash", "relative_day": "today", "explicit_date": ""}}
"paid 1.2k electricity bill on 5th Nov by net banking" ->
{{"amount": 1200, "category": "Bills", "description": "Electricity bill", "merchant": "", "payment_method": "Net Banking", "relative_day": "today", "explicit_date": "{today.year}-11-05"}}
"""


def resolve_date(extraction: LLMExtraction, today: date) -> date:
    """Pick the final expense date. A valid, non-future explicit date wins."""
    explicit = extraction.explicit_date.strip()
    if explicit:
        try:
            parsed = datetime.strptime(explicit, "%Y-%m-%d").date()
            if parsed <= today:
                return parsed
        except ValueError:
            pass  # bad format: fall back to relative_day
    offsets = {"today": 0, "yesterday": 1, "day_before_yesterday": 2}
    return today - timedelta(days=offsets[extraction.relative_day])


def parse_expense(prompt: str, today: date | None = None) -> ParsedExpense:
    today = today or date.today()
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": _system_prompt(today)},
            {"role": "user", "content": prompt.strip()},
        ],
        "format": LLMExtraction.model_json_schema(),  # forces valid JSON in this shape
        "stream": False,
        "think": False,  # skip the reasoning phase (remove if Ollama rejects it)
        "options": {"temperature": 0},  # same input gives the same output
        "keep_alive": "30m",  # keep the model loaded in VRAM between requests
    }

    try:
        resp = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
    except httpx.ConnectError as e:
        raise LLMError(f"Cannot reach Ollama at {OLLAMA_URL}. Is Ollama running?") from e
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise LLMError(f"Model '{OLLAMA_MODEL}' not found. Run: ollama pull {OLLAMA_MODEL}") from e
        raise LLMError(f"Ollama returned an error: {e.response.text[:200]}") from e
    except httpx.TimeoutException as e:
        raise LLMError("Ollama took too long to respond (the model may still be loading).") from e

    try:
        content = resp.json()["message"]["content"]
        x = LLMExtraction.model_validate_json(content)
        return ParsedExpense(
            amount=x.amount,
            category=x.category,
            description=x.description.strip() or "Expense",
            merchant=x.merchant,
            payment_method=x.payment_method,
            expense_date=resolve_date(x, today),
        )
    except (KeyError, ValueError, ValidationError) as e:
        raise LLMError("Couldn't understand that expense. Try: 'lunch 250 upi'.") from e


def ollama_status() -> dict:
    """Used by /health so the UI can show whether Ollama and the model are ready."""
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        resp.raise_for_status()
        names = [m.get("name", "") for m in resp.json().get("models", [])]
        wanted = OLLAMA_MODEL if ":" in OLLAMA_MODEL else f"{OLLAMA_MODEL}:latest"
        return {"ollama": True, "model": OLLAMA_MODEL, "model_available": wanted in names}
    except httpx.HTTPError:
        return {"ollama": False, "model": OLLAMA_MODEL, "model_available": False}