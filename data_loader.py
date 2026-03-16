import io
import pandas as pd
from config import DATASET_PATH, MAX_TRANSACTIONS

# IBM HI-Small_Trans.csv has two columns both named "Account"
# pandas auto-renames the second one to "Account.1"
IBM_COLUMN_MAP = {
    "Timestamp":          "timestamp",
    "Account":            "from_account",
    "Account.1":          "to_account",
    "Amount Paid":        "amount",
    "Amount Received":    "amount_received",
    "Payment Currency":   "payment_currency",
    "Receiving Currency": "receiving_currency",
    "Payment Format":     "payment_format",
    "From Bank":          "from_bank",
    "To Bank":            "to_bank",
    "Is Laundering":      "is_laundering",
}

REQUIRED_COLUMNS = {"from_account", "to_account", "amount", "timestamp"}


def _process(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=IBM_COLUMN_MAP)

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"CSV is missing required columns after rename: {missing}. "
            f"Columns found: {list(df.columns)}"
        )

    df["timestamp"] = pd.to_datetime(df["timestamp"], format="%Y/%m/%d %H:%M", errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)

    if "is_laundering" in df.columns:
        df["is_laundering"] = df["is_laundering"].fillna(0).astype(int)
    else:
        df["is_laundering"] = 0

    return df.head(MAX_TRANSACTIONS)


def load_dataset() -> pd.DataFrame:
    df = pd.read_csv(DATASET_PATH)
    return _process(df)


def load_from_bytes(data: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(data))
    return _process(df)
