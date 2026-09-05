import csv
import secrets
from contextlib import asynccontextmanager
from io import StringIO
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import (
    get_payment,
    get_payment_by_idempotency_key,
    initialize_database,
    insert_payment,
    list_payments,
    payment_stats,
    update_payment,
)
from app.gateway import MpesaGateway
from app.models import (
    DemoCallbackRequest,
    PaymentResponse,
    PaymentStats,
    PaymentStatus,
    STKPushRequest,
    utc_now,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="A secure FastAPI gateway demonstrating M-Pesa STK Push and callback handling.",
    lifespan=lifespan,
)
gateway = MpesaGateway()
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


def serialize_payment(payment: dict) -> PaymentResponse:
    return PaymentResponse.model_validate(payment)


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "healthy", "service": settings.app_name, "simulation": settings.simulation_mode}


@app.post("/api/payments/stk-push", response_model=PaymentResponse, status_code=201)
async def initiate_payment(
    request: STKPushRequest,
    response: Response,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> PaymentResponse:
    idempotency_key = idempotency_key.strip()
    if len(idempotency_key) > 64:
        raise HTTPException(status_code=400, detail="Idempotency key is too long")
    if idempotency_key:
        existing = get_payment_by_idempotency_key(idempotency_key)
        if existing:
            response.status_code = 200
            return serialize_payment(existing)
    try:
        gateway_response = await gateway.initiate_stk_push(
            request.phone_number,
            request.amount,
            request.account_reference,
            request.description,
        )
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail="Payment provider unavailable") from exc

    now = utc_now()
    payment = {
        "checkout_request_id": gateway_response["CheckoutRequestID"],
        "merchant_request_id": gateway_response["MerchantRequestID"],
        "phone_number": request.phone_number,
        "amount": request.amount,
        "account_reference": request.account_reference,
        "status": PaymentStatus.pending.value,
        "result_description": gateway_response.get("CustomerMessage", "Request accepted"),
        "mpesa_receipt_number": None,
        "idempotency_key": idempotency_key or None,
        "created_at": now,
        "updated_at": now,
    }
    insert_payment(payment)
    return serialize_payment(get_payment(payment["checkout_request_id"]))


@app.get("/api/payments", response_model=list[PaymentResponse])
def payment_history(
    limit: int = Query(default=20, ge=1, le=100),
    status: PaymentStatus | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1, max_length=32),
) -> list[PaymentResponse]:
    status_value = status.value if status else None
    return [
        serialize_payment(payment)
        for payment in list_payments(limit, status_value, search)
    ]


@app.get("/api/payments/stats", response_model=PaymentStats)
def payment_analytics() -> PaymentStats:
    return PaymentStats.model_validate(payment_stats())


@app.get("/api/payments/export.csv")
def export_payments() -> StreamingResponse:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "checkout_request_id",
            "phone_number",
            "amount",
            "account_reference",
            "status",
            "mpesa_receipt_number",
            "created_at",
            "updated_at",
        ]
    )
    for payment in list_payments(100):
        writer.writerow(
            [
                payment["checkout_request_id"],
                payment["phone_number"],
                payment["amount"],
                payment["account_reference"],
                payment["status"],
                payment["mpesa_receipt_number"] or "",
                payment["created_at"],
                payment["updated_at"],
            ]
        )
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=payments.csv"},
    )


@app.get("/api/payments/{checkout_request_id}", response_model=PaymentResponse)
def payment_status(checkout_request_id: str) -> PaymentResponse:
    payment = get_payment(checkout_request_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return serialize_payment(payment)


@app.post("/api/payments/{checkout_request_id}/cancel", response_model=PaymentResponse)
def cancel_payment(checkout_request_id: str) -> PaymentResponse:
    payment = get_payment(checkout_request_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment["status"] != PaymentStatus.pending.value:
        raise HTTPException(status_code=409, detail="Only pending payments can be cancelled")
    updated = update_payment(
        checkout_request_id,
        PaymentStatus.cancelled.value,
        "Payment cancelled",
        None,
        utc_now().isoformat(),
    )
    return serialize_payment(updated)


@app.post("/api/payments/{checkout_request_id}/refund", response_model=PaymentResponse)
def refund_payment(checkout_request_id: str) -> PaymentResponse:
    payment = get_payment(checkout_request_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment["status"] != PaymentStatus.completed.value:
        raise HTTPException(status_code=409, detail="Only completed payments can be refunded")
    updated = update_payment(
        checkout_request_id,
        PaymentStatus.refunded.value,
        "Payment refunded in simulation mode",
        payment["mpesa_receipt_number"],
        utc_now().isoformat(),
    )
    return serialize_payment(updated)


@app.post("/api/payments/demo-callback", response_model=PaymentResponse)
def demo_callback(
    callback: DemoCallbackRequest,
    x_callback_token: str = Header(default=""),
) -> PaymentResponse:
    if not secrets.compare_digest(x_callback_token, settings.callback_token):
        raise HTTPException(status_code=401, detail="Invalid callback token")
    payment = get_payment(callback.checkout_request_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment["status"] != PaymentStatus.pending.value:
        raise HTTPException(status_code=409, detail="Payment is already finalized")
    status = PaymentStatus.completed.value if callback.successful else PaymentStatus.failed.value
    description = "Payment completed successfully" if callback.successful else "Payment cancelled by customer"
    receipt = f"SIM{secrets.token_hex(4).upper()}" if callback.successful else None
    updated = update_payment(
        callback.checkout_request_id,
        status,
        description,
        receipt,
        utc_now().isoformat(),
    )
    return serialize_payment(updated)


@app.post("/api/payments/callback")
def daraja_callback(payload: dict) -> dict:
    callback = payload.get("Body", {}).get("stkCallback", {})
    checkout_id = callback.get("CheckoutRequestID")
    if not checkout_id or not get_payment(checkout_id):
        raise HTTPException(status_code=404, detail="Payment not found")

    current_payment = get_payment(checkout_id)
    if current_payment["status"] != PaymentStatus.pending.value:
        return {"ResultCode": 0, "ResultDesc": "Callback already processed"}

    result_code = callback.get("ResultCode", 1)
    items = callback.get("CallbackMetadata", {}).get("Item", [])
    metadata = {item.get("Name"): item.get("Value") for item in items}
    update_payment(
        checkout_id,
        PaymentStatus.completed.value if result_code == 0 else PaymentStatus.failed.value,
        callback.get("ResultDesc", "Callback received"),
        metadata.get("MpesaReceiptNumber"),
        utc_now().isoformat(),
    )
    return {"ResultCode": 0, "ResultDesc": "Callback accepted"}
