import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATE_FILE = Path(os.environ.get("STATE_FILE", str(DATA_DIR / "runtime_state.json")))
DRUG_REFERENCE_FILE = DATA_DIR / "drug_reference.json"
PHARMACY_FILE = DATA_DIR / "pharmacies.json"

DEFAULT_REPEAT_MINUTES = 10
MAX_REMINDER_ATTEMPTS = 3
DEFAULT_REMINDER_INTERVAL_SECONDS = 30
