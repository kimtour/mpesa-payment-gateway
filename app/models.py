from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class PaymentStatus(str, Enum):
    pending = "PENDING"
    completed = "COMPLETED"
    failed = "FAILED"
    cancelled = "CANCELLED"
    refunded = "REFUNDED"


def normalize_phone(value: str) -> str:
    phone = "".join(character for character in value if character.isdigit())
    if phone.startswith("0") and len(phone) == 10:
        phone = "254" + phone[1:]
    elif phone.startswith("7") and len(phone) == 9:
        phone = "254" + phone
    if not phone.startswith("254") or len(phone) != 12:
        raise ValueError("Use a valid Kenyan mobile number")
    return phone


class STKPushRequest(BaseModel):
    phone_number: str = Field(examples=["0712345678"])
    amount: Decimal = Field(gt=0, le=150000, decimal_places=2)
    account_reference: str = Field(min_length=1, max_length=32, examples=["INV-1001"])
    description: str = Field(default="Payment", min_length=1, max_length=64)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return normalize_phone(value)


class PaymentResponse(BaseModel):
    checkout_request_id: str
    merchant_request_id: str
    phone_number: str
    amount: Decimal
    account_reference: str
    status: PaymentStatus
    result_description: str
    mpesa_receipt_number: str | None = None
    created_at: datetime
    updated_at: datetime
    idempotency_key: str | None = None


class PaymentStats(BaseModel):
    total_transactions: int
    pending: int
    completed: int
    failed: int
    cancelled: int
    refunded: int
    completed_value: Decimal
    success_rate: float


class DemoCallbackRequest(BaseModel):
    checkout_request_id: str
    successful: bool = True


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
