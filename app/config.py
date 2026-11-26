import os

from dotenv import load_dotenv

load_dotenv()  # reads .env from the repo root into environment variables

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:4b")
DB_PATH = os.getenv("DB_PATH", "expenses.db")