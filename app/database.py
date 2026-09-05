import sqlite3
from decimal import Decimal
from pathlib import Path

from app.config import settings


def connect() -> sqlite3.Connection:
    database = Path(settings.database_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                checkout_request_id TEXT PRIMARY KEY,
                merchant_request_id TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                amount TEXT NOT NULL,
                account_reference TEXT NOT NULL,
                status TEXT NOT NULL,
                result_description TEXT NOT NULL,
                mpesa_receipt_number TEXT,
                idempotency_key TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(payments)")
        }
        if "idempotency_key" not in columns:
            connection.execute("ALTER TABLE payments ADD COLUMN idempotency_key TEXT")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_idempotency_key
            ON payments(idempotency_key) WHERE idempotency_key IS NOT NULL
            """
        )


def insert_payment(payment: dict) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO payments (
                checkout_request_id, merchant_request_id, phone_number,
                amount, account_reference, status, result_description,
                mpesa_receipt_number, idempotency_key, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                payment.get("idempotency_key"),
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


def get_payment_by_idempotency_key(idempotency_key: str) -> dict | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM payments WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
    return dict(row) if row else None


def list_payments(
    limit: int = 20,
    status: str | None = None,
    search: str | None = None,
) -> list[dict]:
    filters = []
    parameters: list[str | int] = []
    if status:
        filters.append("status = ?")
        parameters.append(status)
    if search:
        filters.append("(account_reference LIKE ? OR phone_number LIKE ?)")
        term = f"%{search}%"
        parameters.extend([term, term])
    where_clause = f" WHERE {' AND '.join(filters)}" if filters else ""
    parameters.append(limit)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM payments{where_clause} ORDER BY created_at DESC LIMIT ?",
            parameters,
        ).fetchall()
    return [dict(row) for row in rows]


def payment_stats() -> dict:
    with connect() as connection:
        rows = connection.execute("SELECT status, amount FROM payments").fetchall()
    counts = {
        "PENDING": 0,
        "COMPLETED": 0,
        "FAILED": 0,
        "CANCELLED": 0,
        "REFUNDED": 0,
    }
    completed_value = Decimal("0")
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        if row["status"] == "COMPLETED":
            completed_value += Decimal(row["amount"])
    total = len(rows)
    return {
        "total_transactions": total,
        "pending": counts["PENDING"],
        "completed": counts["COMPLETED"],
        "failed": counts["FAILED"],
        "cancelled": counts["CANCELLED"],
        "refunded": counts["REFUNDED"],
        "completed_value": completed_value,
        "success_rate": round((counts["COMPLETED"] / total * 100), 2) if total else 0,
    }


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
