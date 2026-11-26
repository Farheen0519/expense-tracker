import sqlite3
from .config import DB_PATH

def init_db() -> None:
    """Create the table and indexes if they don't exist. Runs once at startup."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        amount         REAL NOT NULL CHECK (amount > 0),
        category       TEXT NOT NULL,
        description    TEXT NOT NULL,
        merchant       TEXT,
        payment_method TEXT NOT NULL,
        expense_date   TEXT NOT NULL,          -- 'YYYY-MM-DD'
        raw_prompt     TEXT,
        created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exp_category ON expenses(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exp_date ON expenses(expense_date)")
    conn.commit()
    conn.close()


def get_conn():
    """FastAPI dependency: one connection per request, always closed."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row   # rows behave like dicts: row["amount"]
    try:
        yield conn
    finally:
        conn.close()