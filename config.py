from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "raw"
CLEAN_DIR = BASE_DIR / "clean"
PDF_DIR = BASE_DIR / "pdfs"

# -------------------------
# PDF files (auto-discover)
# -------------------------
PDFS = list(PDF_DIR.glob("*.pdf"))

# -------------------------
# Chunking Settings
# -------------------------
CHUNK_SIZE = 500
CHUNK_OVERLAP = 200
MAX_PAGES = 100

# -------------------------
# Database Config
# -------------------------
POSTGRES = {
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST"),
    "port": os.getenv("POSTGRES_PORT"),
}

NEO4J = {
    "uri": os.getenv("NEO4J_URI"),
    "user": os.getenv("NEO4J_USER"),
    "password": os.getenv("NEO4J_PASSWORD"),
}

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")

REGIONS = os.getenv("REGIONS", "").split(",") if os.getenv("REGIONS") else []
