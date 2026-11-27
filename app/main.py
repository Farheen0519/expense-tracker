import sqlite3
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query, Response

from .db import get_conn, init_db
from .llm import LLMError, ollama_status, parse_expense
from .schemas import (
    CATEGORIES,
    PAYMENT_METHODS,
    ExpenseCreate,
    ExpenseOut,
    ParsedExpense,
    ParseRequest,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # create the table on startup if it doesn't exist
    yield


app = FastAPI(title="Expense Tracker", version="0.1.0", lifespan=lifespan)


# ---------- Utility routes ----------
@app.get("/health")
def health():
    return {"api": "ok", **ollama_status()}


@app.get("/meta")
def meta():
    """The UI reads the allowed values from here instead of hardcoding them."""
    return {"categories": CATEGORIES, "payment_methods": PAYMENT_METHODS}


# ---------- Step 5: parse and create ----------
@app.post("/expenses/parse", response_model=ParsedExpense)
def parse(req: ParseRequest):
    """LLM parses the text and returns a preview. Nothing is saved yet."""
    try:
        return parse_expense(req.prompt)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(body: ExpenseCreate, conn: sqlite3.Connection = Depends(get_conn)):
    """Save a confirmed (and possibly user-edited) expense."""
    cur = conn.execute(
        """
        INSERT INTO expenses
            (amount, category, description, merchant, payment_method, expense_date, raw_prompt)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            body.amount,
            body.category,
            body.description,
            body.merchant,
            body.payment_method,
            body.expense_date.isoformat(),
            body.raw_prompt,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM expenses WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


# ---------- Step 6: list and delete ----------
@app.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(100, ge=1, le=1000),
    conn: sqlite3.Connection = Depends(get_conn),
):
    sql = "SELECT * FROM expenses WHERE 1=1"
    params: list = []
    if category:
        sql += " AND category = ?"
        params.append(category)
    if start_date:
        sql += " AND expense_date >= ?"
        params.append(start_date.isoformat())
    if end_date:
        sql += " AND expense_date <= ?"
        params.append(end_date.isoformat())
    sql += " ORDER BY expense_date DESC, id DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@app.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    cur = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
    return Response(status_code=204)