import base64
import secrets
from datetime import datetime
from decimal import Decimal

import httpx

from app.config import settings


class MpesaGateway:
    def __init__(self) -> None:
        self.base_url = (
            "https://sandbox.safaricom.co.ke"
            if settings.mpesa_environment == "sandbox"
            else "https://api.safaricom.co.ke"
        )

    async def initiate_stk_push(
        self,
        phone_number: str,
        amount: Decimal,
        account_reference: str,
        description: str,
    ) -> dict:
        if settings.simulation_mode:
            suffix = secrets.token_hex(6).upper()
            return {
                "MerchantRequestID": f"SIM-MERCHANT-{suffix}",
                "CheckoutRequestID": f"ws_CO_SIM_{suffix}",
                "ResponseCode": "0",
                "ResponseDescription": "Simulation request accepted",
                "CustomerMessage": "Enter your M-Pesa PIN on your phone",
            }

        token = await self._access_token()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password_value = f"{settings.mpesa_shortcode}{settings.mpesa_passkey}{timestamp}"
        password = base64.b64encode(password_value.encode()).decode()
        payload = {
            "BusinessShortCode": settings.mpesa_shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone_number,
            "PartyB": settings.mpesa_shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": settings.mpesa_callback_url,
            "AccountReference": account_reference,
            "TransactionDesc": description,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.base_url}/mpesa/stkpush/v1/processrequest",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            return response.json()

    async def _access_token(self) -> str:
        if not settings.mpesa_consumer_key or not settings.mpesa_consumer_secret:
            raise RuntimeError("Daraja credentials are missing")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials",
                auth=(settings.mpesa_consumer_key, settings.mpesa_consumer_secret),
            )
            response.raise_for_status()
            return response.json()["access_token"]
