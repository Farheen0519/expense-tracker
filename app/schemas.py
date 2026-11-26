from datetime import date, datetime
from typing import Literal, get_args

from pydantic import BaseModel, Field, field_validator

Category = Literal[
    "Food", "Transport", "Bills", "Shopping", "Health", "Entertainment", "Other"
]
PaymentMethod = Literal["UPI", "Cash", "Card", "Net Banking", "Other"]

CATEGORIES: list[str] = list(get_args(Category))
PAYMENT_METHODS: list[str] = list(get_args(PaymentMethod))


class ParseRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=500)


class ParsedExpense(BaseModel):
    """What the LLM parser returns and what the UI shows for confirmation."""

    amount: float = Field(gt=0, le=10_000_000, description="Amount in INR")
    category: Category = "Other"
    description: str = Field(min_length=1, max_length=200)
    merchant: str | None = Field(default=None, max_length=100)
    payment_method: PaymentMethod = "Other"
    expense_date: date

    @field_validator("amount")
    @classmethod
    def round_amount(cls, v: float) -> float:
        return round(v, 2)

    @field_validator("merchant")
    @classmethod
    def blank_merchant_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ExpenseCreate(ParsedExpense):
    """A confirmed expense, ready to save."""

    raw_prompt: str | None = Field(default=None, max_length=500)


class ExpenseOut(ExpenseCreate):
    """What the API returns, including the database-generated fields."""

    id: int
    created_at: datetime