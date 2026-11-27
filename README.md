# Expense Tracker

A local, privacy-first expense tracker. Type an expense in plain English, a small LLM running on your own GPU turns it into structured data, you review and confirm it, and it is saved to a database. Amounts are in INR.

> `spent 450 on lunch with Rahul yesterday via UPI` -> **₹450 · Food · Lunch · Rahul · UPI · yesterday's date**

No cloud APIs, no per-request cost, and your spending data never leaves your machine.

## Features (Phase 1)

- Natural-language expense entry, parsed by a local LLM (Qwen via Ollama)
- Review-and-edit step before anything is saved (human in the loop)
- Schema-constrained JSON output, so the model can only return valid categories and payment methods
- Dates resolved in Python, not by the model (small models are unreliable at date math)
- Handles Indian-style amounts: `1.2k`, `2 lakh`; treats GPay / PhonePe / Paytm as UPI
- REST API with validation (FastAPI + Pydantic)
- Streamlit UI with an "Add expense" tab and a "My expenses" tab (filter, total, delete)
- SQLite storage, with the original sentence kept in `raw_prompt` for tuning the parser later

## How it works

```
Streamlit UI -> FastAPI -> Ollama (Qwen) -> Pydantic validation -> you confirm -> SQLite
```

1. You type a sentence and click **Parse**.
2. FastAPI sends it to Ollama with a system prompt (rules, allowed categories, examples) and a JSON schema.
3. The model returns fields such as amount, category, description, merchant, payment method, and a relative day (`today` / `yesterday` / `day_before_yesterday`) or an explicit date.
4. Python resolves the real date, and Pydantic validates everything.
5. The UI shows an editable form. You fix anything wrong and click **Save**.
6. The expense is stored in SQLite.

**The LLM only does language understanding.** Dates, validation, storage, and (later) totals and analysis are done by ordinary code, so they are exact.

## Tech stack

| Layer | Choice |
|---|---|
| LLM runtime | [Ollama](https://ollama.com) |
| Model | `qwen3.5:4b` (about 3 GB, runs 100% on a 6 GB GPU) |
| API | FastAPI + Pydantic |
| Database | SQLite via Python's built-in `sqlite3` |
| UI | Streamlit |
| Config | `python-dotenv` and a `.env` file |

## Project structure

```
expense-tracker/
├── app/
│   ├── __init__.py
│   ├── config.py          # reads settings from .env
│   ├── db.py              # sqlite3 connection + table creation
│   ├── schemas.py         # Pydantic models and allowed values
│   ├── llm.py             # Ollama call, prompt, date resolution
│   └── main.py            # FastAPI routes
├── ui/
│   └── streamlit_app.py   # Streamlit interface
├── .env.example           # sample settings (copy to .env)
├── .gitignore
├── requirements.txt
├── LICENSE
└── README.md
```

`expenses.db` is created automatically the first time the API starts.

## Prerequisites

- Python 3.10 or newer
- [Ollama](https://ollama.com/download) installed
- A GPU with about 4 GB of free VRAM is recommended (developed on an RTX 4050 with 6 GB). A CPU also works, but is slower.

## Setup

**1. Clone and create a virtual environment**
```powershell
git clone https://github.com/Farheen0519/expense-tracker.git
cd expense-tracker
python -m venv .venv
.venv\Scripts\activate
```

**2. Install dependencies**
```powershell
python -m pip install -r requirements.txt
```
Use `python -m pip` rather than `pip`. On Windows machines with an Application Control policy, `pip.exe` can be blocked while `python -m pip` works (see Troubleshooting).

**3. Pull the model**
```powershell
ollama pull qwen3.5:4b
```
Check that it uses your GPU while loaded: run `ollama ps` and look for `100% GPU`.

**4. Create your settings file**
```powershell
copy .env.example .env
```
The defaults work as they are. Edit `.env` to change the model or database path.

## Run

Use two terminals, both with the virtual environment activated, from the repository root.

**Terminal 1: API**
```powershell
python -m uvicorn app.main:app --reload
```
Interactive API docs: http://127.0.0.1:8000/docs

**Terminal 2: UI**
```powershell
python -m streamlit run ui/streamlit_app.py
```
The app opens at http://localhost:8501. If Streamlit asks for an email on the first run, press Enter.

The sidebar shows whether the API, Ollama and the model are ready.

## Try these prompts

- `spent 450 on lunch with Rahul yesterday via UPI`
- `auto 80 cash`
- `paid 1.2k electricity bill on 5th Nov by net banking`
- `bought medicines for 340 on phonepe`
- `coffee 120 day before yesterday`

The first parse after starting can take 10-20 seconds while the model loads into VRAM. After that it usually takes 1-3 seconds.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | API, Ollama and model status |
| GET | `/meta` | Allowed categories and payment methods |
| POST | `/expenses/parse` | LLM parses text and returns a preview (nothing saved) |
| POST | `/expenses` | Save a confirmed expense |
| GET | `/expenses` | List expenses. Filters: `category`, `start_date`, `end_date`, `limit` |
| DELETE | `/expenses/{id}` | Delete an expense |

## Configuration

Settings are read from `.env`. Restart the API after changing them, because `--reload` only watches `.py` files.

| Variable | Default | Meaning |
|---|---|---|
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Where Ollama is listening |
| `OLLAMA_MODEL` | `qwen3.5:4b` | Model used for parsing |
| `DB_PATH` | `expenses.db` | SQLite file location |
| `API_URL` | `http://127.0.0.1:8000` | Where the UI finds the API (optional) |

## Data model

Table `expenses`:

| Column | Type | Notes |
|---|---|---|
| `id` | integer | primary key |
| `amount` | real | INR, must be greater than 0 |
| `category` | text | Food, Transport, Bills, Shopping, Health, Entertainment, Other |
| `description` | text | short phrase, e.g. "Lunch" |
| `merchant` | text | optional |
| `payment_method` | text | UPI, Cash, Card, Net Banking, Other |
| `expense_date` | text | `YYYY-MM-DD` |
| `raw_prompt` | text | the original sentence, optional |
| `created_at` | text | UTC timestamp, set automatically |

## Troubleshooting

**"An Application Control policy has blocked this file" (Windows)**
Some Windows policies (Smart App Control, AppLocker) block small `.exe` launchers and compiled extension files.
- Run tools through Python instead of their `.exe`: `python -m pip`, `python -m uvicorn`, `python -m streamlit`.
- The error names the blocked file. Use that to find which package is affected.
- If you are on a personal laptop, check Windows Security, then App & browser control, then Smart App Control. On a work or college laptop, ask IT.

**"Cannot reach Ollama" (502 on Parse)**
Start the Ollama app and check http://127.0.0.1:11434/api/tags in a browser.

**"Model not found"**
Run `ollama pull <model>` for the name in `OLLAMA_MODEL`.

**Ollama returns a 400 error mentioning `think`**
Your Ollama version or model does not support the flag. Remove the `"think": False` line in `app/llm.py`.

**The first parse is very slow**
The model is loading into memory. Later parses are much faster, and `keep_alive` keeps it loaded for 30 minutes.

**Weird `streamlit` import errors**
Make sure no file in the project is named `streamlit.py`. It would shadow the real library. The UI file is `streamlit_app.py`.

**The model gets a category or amount wrong**
Fix it in the confirm form before saving. To improve it, add an example to the system prompt in `app/llm.py`, or try a larger model through `OLLAMA_MODEL`.

## Roadmap

- **Phase 2: Analytics.** Spending by category, week and month, top merchants, month-over-month comparison, budgets with alerts, charts.
- **Phase 3: Smarter features.** Multiple expenses in one sentence, plain-English questions answered with read-only SQL, monthly written summaries, recurring and unusual expense detection.
- **Later.** Move to PostgreSQL, receipt photo reading with a vision model, CSV export.

## License

See [LICENSE](LICENSE).
