import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import (
    get_payment,
    initialize_database,
    insert_payment,
    list_payments,
    update_payment,
)
from app.gateway import MpesaGateway
from app.models import DemoCallbackRequest, PaymentResponse, PaymentStatus, STKPushRequest, utc_now


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
async def initiate_payment(request: STKPushRequest) -> PaymentResponse:
    try:
        response = await gateway.initiate_stk_push(
            request.phone_number,
            request.amount,
            request.account_reference,
            request.description,
        )
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail="Payment provider unavailable") from exc

    now = utc_now()
    payment = {
        "checkout_request_id": response["CheckoutRequestID"],
        "merchant_request_id": response["MerchantRequestID"],
        "phone_number": request.phone_number,
        "amount": request.amount,
        "account_reference": request.account_reference,
        "status": PaymentStatus.pending.value,
        "result_description": response.get("CustomerMessage", "Request accepted"),
        "mpesa_receipt_number": None,
        "created_at": now,
        "updated_at": now,
    }
    insert_payment(payment)
    return serialize_payment(get_payment(payment["checkout_request_id"]))


@app.get("/api/payments", response_model=list[PaymentResponse])
def payment_history(limit: int = Query(default=20, ge=1, le=100)) -> list[PaymentResponse]:
    return [serialize_payment(payment) for payment in list_payments(limit)]


@app.get("/api/payments/{checkout_request_id}", response_model=PaymentResponse)
def payment_status(checkout_request_id: str) -> PaymentResponse:
    payment = get_payment(checkout_request_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return serialize_payment(payment)


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
