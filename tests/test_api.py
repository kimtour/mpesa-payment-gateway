from unittest.mock import AsyncMock


def create_payment(client, reference="INV-1001", key=None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(
        "/api/payments/stk-push",
        headers=headers,
        json={
            "phone_number": "0712345678",
            "amount": 100,
            "account_reference": reference,
            "description": "Test payment",
        },
    )


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_stk_push_and_callback(client):
    response = client.post(
        "/api/payments/stk-push",
        json={
            "phone_number": "0712345678",
            "amount": 100,
            "account_reference": "INV-1001",
            "description": "Test payment",
        },
    )
    assert response.status_code == 201
    payment = response.json()
    assert payment["status"] == "PENDING"
    assert payment["phone_number"] == "254712345678"

    callback = client.post(
        "/api/payments/demo-callback",
        headers={"X-Callback-Token": "demo-callback-token"},
        json={"checkout_request_id": payment["checkout_request_id"], "successful": True},
    )
    assert callback.status_code == 200
    assert callback.json()["status"] == "COMPLETED"
    assert callback.json()["mpesa_receipt_number"].startswith("SIM")


def test_rejects_invalid_amount(client):
    response = client.post(
        "/api/payments/stk-push",
        json={
            "phone_number": "0712345678",
            "amount": 0,
            "account_reference": "INV-1002",
        },
    )
    assert response.status_code == 422


def test_callback_requires_token(client):
    response = client.post(
        "/api/payments/demo-callback",
        json={"checkout_request_id": "missing", "successful": True},
    )
    assert response.status_code == 401


def test_idempotency_returns_original_payment(client):
    first = create_payment(client, key="checkout-1001")
    second = create_payment(client, reference="DIFFERENT", key="checkout-1001")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["checkout_request_id"] == first.json()["checkout_request_id"]
    assert second.json()["account_reference"] == "INV-1001"


def test_rejects_long_idempotency_key(client):
    response = create_payment(client, key="x" * 65)
    assert response.status_code == 400


def test_filter_search_stats_and_csv_export(client):
    completed = create_payment(client, reference="ORDER-ALPHA").json()
    create_payment(client, reference="ORDER-BETA")
    client.post(
        "/api/payments/demo-callback",
        headers={"X-Callback-Token": "demo-callback-token"},
        json={"checkout_request_id": completed["checkout_request_id"], "successful": True},
    )

    filtered = client.get("/api/payments", params={"status": "COMPLETED"})
    searched = client.get("/api/payments", params={"search": "BETA"})
    stats = client.get("/api/payments/stats").json()
    exported = client.get("/api/payments/export.csv")

    assert len(filtered.json()) == 1
    assert filtered.json()[0]["account_reference"] == "ORDER-ALPHA"
    assert len(searched.json()) == 1
    assert searched.json()[0]["account_reference"] == "ORDER-BETA"
    assert stats["total_transactions"] == 2
    assert stats["completed"] == 1
    assert stats["pending"] == 1
    assert stats["completed_value"] == "100"
    assert stats["success_rate"] == 50.0
    assert exported.status_code == 200
    assert "attachment; filename=payments.csv" in exported.headers["content-disposition"]
    assert "ORDER-ALPHA" in exported.text


def test_cancel_pending_payment(client):
    payment = create_payment(client).json()
    endpoint = f'/api/payments/{payment["checkout_request_id"]}/cancel'

    cancelled = client.post(endpoint)
    repeated = client.post(endpoint)

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert repeated.status_code == 409


def test_refund_completed_payment(client):
    payment = create_payment(client).json()
    client.post(
        "/api/payments/demo-callback",
        headers={"X-Callback-Token": "demo-callback-token"},
        json={"checkout_request_id": payment["checkout_request_id"], "successful": True},
    )
    endpoint = f'/api/payments/{payment["checkout_request_id"]}/refund'

    refunded = client.post(endpoint)
    repeated = client.post(endpoint)

    assert refunded.status_code == 200
    assert refunded.json()["status"] == "REFUNDED"
    assert refunded.json()["mpesa_receipt_number"].startswith("SIM")
    assert repeated.status_code == 409


def test_payment_action_not_found(client):
    assert client.get("/api/payments/missing").status_code == 404
    assert client.post("/api/payments/missing/cancel").status_code == 404
    assert client.post("/api/payments/missing/refund").status_code == 404


def test_failed_payment_cannot_be_refunded(client):
    payment = create_payment(client).json()
    failed = client.post(
        "/api/payments/demo-callback",
        headers={"X-Callback-Token": "demo-callback-token"},
        json={"checkout_request_id": payment["checkout_request_id"], "successful": False},
    )

    assert failed.json()["status"] == "FAILED"
    assert client.post(
        f'/api/payments/{payment["checkout_request_id"]}/refund'
    ).status_code == 409


def test_daraja_callback_is_idempotent(client):
    payment = create_payment(client).json()
    payload = {
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": payment["checkout_request_id"],
                "ResultCode": 0,
                "ResultDesc": "Processed",
                "CallbackMetadata": {
                    "Item": [{"Name": "MpesaReceiptNumber", "Value": "QWE123XYZ"}]
                },
            }
        }
    }

    accepted = client.post("/api/payments/callback", json=payload)
    repeated = client.post("/api/payments/callback", json=payload)

    assert accepted.json()["ResultDesc"] == "Callback accepted"
    assert repeated.json()["ResultDesc"] == "Callback already processed"
    assert client.get(
        f'/api/payments/{payment["checkout_request_id"]}'
    ).json()["mpesa_receipt_number"] == "QWE123XYZ"


def test_provider_error_returns_bad_gateway(client, monkeypatch):
    from app import main

    monkeypatch.setattr(
        main.gateway,
        "initiate_stk_push",
        AsyncMock(side_effect=RuntimeError("provider unavailable")),
    )
    response = create_payment(client)
    assert response.status_code == 502
