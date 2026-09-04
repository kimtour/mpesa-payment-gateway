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
