import os
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import PaymentTransaction, User
from app.services.payments import (
    activate_pro_subscription,
    create_or_update_pending_transaction,
    create_payment_session,
    mark_transaction_status,
    normalize_payment_method,
    serialize_payment_debug,
    verify_payment_signature,
)

router = APIRouter(tags=["payments"])
ENABLE_PAYMENT_SIMULATION = os.getenv("ENABLE_PAYMENT_SIMULATION", "false").lower() == "true"
PAYMENT_SIMULATION_TOKEN = os.getenv("PAYMENT_SIMULATION_TOKEN", "").strip()


def _method_aliases_for_query(method: str) -> list[str]:
    if method == "cardpayment":
        return ["cardpayment", "card"]
    return [method]


class CreatePaymentRequest(BaseModel):
    method: str = Field(pattern="^(easypaisa|jazzcash|cardpayment|card)$")
    amount_pkr: int = Field(default=2000, ge=100, le=500000)


class CreatePaymentResponse(BaseModel):
    provider: str
    reference: str
    checkout_url: str


class WebhookPayload(BaseModel):
    method: str = Field(pattern="^(easypaisa|jazzcash|cardpayment|card)$")
    reference: str
    signature: str
    status: str
    amount_pkr: int = Field(ge=100, le=500000)
    provider_txn_id: str | None = None


class SimulateWebhookRequest(BaseModel):
    method: str = Field(pattern="^(easypaisa|jazzcash|cardpayment|card)$")
    reference: str | None = None
    status: str = Field(default="success")


@router.post("/create-payment", response_model=CreatePaymentResponse)
@router.post("/payments/create-payment", response_model=CreatePaymentResponse)
def create_payment(
    payload: CreatePaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CreatePaymentResponse:
    try:
        method = normalize_payment_method(payload.method)
        session = create_payment_session(current_user, method, payload.amount_pkr)
        create_or_update_pending_transaction(
            db=db,
            user_id=current_user.id,
            method=method,
            reference=session["reference"],
            amount_pkr=payload.amount_pkr,
        )
        return CreatePaymentResponse(**session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/payment-webhook")
@router.post("/payments/payment-webhook")
async def payment_webhook(payload: WebhookPayload, db: Session = Depends(get_db)) -> dict:
    method = normalize_payment_method(payload.method)
    query_methods = _method_aliases_for_query(method)
    is_signature_valid = verify_payment_signature(
        method=method,
        reference=payload.reference,
        status=payload.status,
        signature=payload.signature,
        amount_pkr=payload.amount_pkr,
    )
    if not is_signature_valid:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    transaction = (
        db.query(PaymentTransaction)
        .filter(
            PaymentTransaction.reference == payload.reference,
            PaymentTransaction.method.in_(query_methods),
        )
        .first()
    )
    if not transaction:
        raise HTTPException(status_code=404, detail="Unknown payment reference")

    if transaction.amount_pkr != payload.amount_pkr:
        raise HTTPException(status_code=400, detail="Invalid payment amount")

    normalized_status = payload.status.lower()
    mark_transaction_status(
        db=db,
        reference=payload.reference,
        status=normalized_status,
        provider_txn_id=payload.provider_txn_id,
    )

    if normalized_status not in {"success", "paid", "completed"}:
        return {"received": True, "upgraded": False, "timestamp": datetime.utcnow().isoformat()}

    activate_pro_subscription(
        db=db,
        user_id=transaction.user_id,
        provider=method,
        provider_ref=payload.reference,
        days=30,
    )
    return {"received": True, "upgraded": True, "timestamp": datetime.utcnow().isoformat()}


@router.post("/payments/simulate-success")
def simulate_success(
    payload: SimulateWebhookRequest,
    request: Request,
    x_simulation_token: str | None = Header(default=None, alias="X-Simulation-Token"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not ENABLE_PAYMENT_SIMULATION:
        raise HTTPException(status_code=403, detail="Payment simulation is disabled")

    client_ip = request.client.host if request.client else ""
    if client_ip not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="Payment simulation is allowed only from localhost")

    if not PAYMENT_SIMULATION_TOKEN or x_simulation_token != PAYMENT_SIMULATION_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid simulation token")

    method = normalize_payment_method(payload.method)
    query_methods = _method_aliases_for_query(method)

    transaction = None
    if payload.reference:
        transaction = (
            db.query(PaymentTransaction)
            .filter(
                PaymentTransaction.reference == payload.reference,
                PaymentTransaction.user_id == current_user.id,
                PaymentTransaction.method.in_(query_methods),
            )
            .first()
        )
    else:
        transaction = (
            db.query(PaymentTransaction)
            .filter(
                PaymentTransaction.user_id == current_user.id,
                PaymentTransaction.method.in_(query_methods),
                PaymentTransaction.status == "pending",
            )
            .order_by(PaymentTransaction.created_at.desc())
            .first()
        )
    if not transaction:
        raise HTTPException(status_code=404, detail="No matching pending payment found")

    webhook_payload = serialize_payment_debug(
        method=transaction.method,
        reference=transaction.reference,
        amount_pkr=transaction.amount_pkr,
        status=payload.status,
    )
    verified = verify_payment_signature(
        method=transaction.method,
        reference=transaction.reference,
        status=payload.status,
        signature=webhook_payload["signature"],
        amount_pkr=transaction.amount_pkr,
    )
    if not verified:
        raise HTTPException(status_code=400, detail="Signature verification failed")

    mark_transaction_status(
        db=db,
        reference=transaction.reference,
        status=payload.status.lower(),
        provider_txn_id=f"sim-{transaction.reference}",
    )
    if payload.status.lower() in {"success", "paid", "completed"}:
        activate_pro_subscription(
            db=db,
            user_id=current_user.id,
            provider=transaction.method,
            provider_ref=transaction.reference,
            days=30,
        )
    return {"ok": True, "reference": transaction.reference, "status": payload.status.lower()}
