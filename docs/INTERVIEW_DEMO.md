# M-Pesa Gateway Interview Demo

## Open these links

- Working application: https://mpesa-payment-gateway.onrender.com
- Interactive API documentation: https://mpesa-payment-gateway.onrender.com/docs
- Visual showcase: https://mpesa-payment-gateway-demo.onrender.com
- Source code: https://github.com/kimtour/mpesa-payment-gateway

## Demonstrate the payment lifecycle

1. Enter `0712345678`, `100` and an account reference.
2. Select **Send STK Push** and point out the `PENDING` transaction.
3. Select **Complete** to simulate the M-Pesa callback.
4. Show the `COMPLETED` status and simulated receipt number.
5. Open Swagger and identify the health, initiation, history, status and callback endpoints.

## Explain the architecture

The browser sends a validated REST request to FastAPI. The gateway either calls the Safaricom Daraja API or creates a safe simulated response. SQLite stores the pending transaction. A later callback updates the record to completed or failed, which models the asynchronous behavior of real mobile payments.

## Explain quality and delivery

Pydantic validates input, pytest covers unit and integration behavior, GitHub Actions runs the automated checks and builds the Docker image, and Render hosts the container. Environment variables keep deployment settings and real credentials outside source control.

## Production improvements

Use PostgreSQL instead of ephemeral SQLite, store secrets in a managed vault, add OAuth or API-key authentication, enforce rate limits, validate provider callback signatures, add idempotency keys, centralize logs and metrics, and deploy behind an API gateway.
