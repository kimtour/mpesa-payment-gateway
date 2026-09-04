import sqlite3
from pathlib import Path

from app.config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
    checkout_request_id TEXT PRIMARY KEY,
    merchant_request_id TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    amount TEXT NOT NULL,
    account_reference TEXT NOT NULL,
    status TEXT NOT NULL,
    result_description TEXT NOT NULL,
    mpesa_receipt_number TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    database = Path(settings.database_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with connect() as connection:
        connection.executescript(SCHEMA)


def insert_payment(payment: dict) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO payments (
                checkout_request_id, merchant_request_id, phone_number,
                amount, account_reference, status, result_description,
                mpesa_receipt_number, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payment["checkout_request_id"],
                payment["merchant_request_id"],
                payment["phone_number"],
                str(payment["amount"]),
                payment["account_reference"],
                payment["status"],
                payment["result_description"],
                payment.get("mpesa_receipt_number"),
                payment["created_at"].isoformat(),
                payment["updated_at"].isoformat(),
            ),
        )


def get_payment(checkout_request_id: str) -> dict | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM payments WHERE checkout_request_id = ?",
            (checkout_request_id,),
        ).fetchone()
    return dict(row) if row else None


def list_payments(limit: int = 20) -> list[dict]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM payments ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def update_payment(
    checkout_request_id: str,
    status: str,
    description: str,
    receipt: str | None,
    updated_at: str,
) -> dict | None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE payments
            SET status = ?, result_description = ?, mpesa_receipt_number = ?, updated_at = ?
            WHERE checkout_request_id = ?
            """,
            (status, description, receipt, updated_at, checkout_request_id),
        )
    return get_payment(checkout_request_id)
