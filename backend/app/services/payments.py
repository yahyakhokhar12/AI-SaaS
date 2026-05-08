import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.models import PaymentTransaction, Subscription, User

load_dotenv()

PAYMENT_RETURN_URL = os.getenv("PAYMENT_RETURN_URL", "http://localhost:5173/billing")
EASYPAISA_MERCHANT_ID = os.getenv("EASYPAISA_MERCHANT_ID", "")
EASYPAISA_SECRET = os.getenv("EASYPAISA_SECRET", "")
EASYPAISA_GATEWAY_URL = os.getenv("EASYPAISA_GATEWAY_URL", "https://easypaisa.example/pay")

JAZZCASH_MERCHANT_ID = os.getenv("JAZZCASH_MERCHANT_ID", "")
JAZZCASH_SECRET = os.getenv("JAZZCASH_SECRET", "")
JAZZCASH_GATEWAY_URL = os.getenv("JAZZCASH_GATEWAY_URL", "https://jazzcash.example/pay")

CARD_GATEWAY_MERCHANT_ID = os.getenv("CARD_GATEWAY_MERCHANT_ID", "")
CARD_GATEWAY_SECRET = os.getenv("CARD_GATEWAY_SECRET", "")
CARD_GATEWAY_URL = os.getenv("CARD_GATEWAY_URL", "https://card-gateway.example/pay")


def normalize_payment_method(method: str) -> str:
    normalized = method.strip().lower()
    if normalized == "card":
        return "cardpayment"
    return normalized


def _merchant_id_for_method(method: str) -> str:
    method = normalize_payment_method(method)
    if method == "easypaisa":
        return EASYPAISA_MERCHANT_ID or "dev-easypaisa-merchant"
    if method == "jazzcash":
        return JAZZCASH_MERCHANT_ID or "dev-jazzcash-merchant"
    if method == "cardpayment":
        return CARD_GATEWAY_MERCHANT_ID or "dev-card-merchant"
    raise ValueError("Unsupported payment method")


def _secret_for_method(method: str) -> str:
    method = normalize_payment_method(method)
    if method == "easypaisa":
        return EASYPAISA_SECRET or "dev-easypaisa-secret"
    if method == "jazzcash":
        return JAZZCASH_SECRET or "dev-jazzcash-secret"
    if method == "cardpayment":
        return CARD_GATEWAY_SECRET or "dev-card-secret"
    raise ValueError("Unsupported payment method")


def _gateway_url_for_method(method: str) -> str:
    method = normalize_payment_method(method)
    if method == "easypaisa":
        return EASYPAISA_GATEWAY_URL
    if method == "jazzcash":
        return JAZZCASH_GATEWAY_URL
    if method == "cardpayment":
        return CARD_GATEWAY_URL
    raise ValueError("Unsupported payment method")


def _sign_payload(secret: str, payload: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_payment_session(user: User, method: str, amount_pkr: int) -> dict:
    method = normalize_payment_method(method)
    merchant_id = _merchant_id_for_method(method)
    secret = _secret_for_method(method)
    gateway_url = _gateway_url_for_method(method)
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    reference = f"{method}-{user.id}-{now}"
    signature = _sign_payload(secret, f"{reference}|{amount_pkr}")
    return {
        "provider": method,
        "reference": reference,
        "checkout_url": (
            f"{gateway_url}?merchant={merchant_id}&ref={reference}&amount={amount_pkr}"
            f"&sig={signature}&return={PAYMENT_RETURN_URL}"
        ),
    }


def create_or_update_pending_transaction(
    db: Session,
    user_id: int,
    method: str,
    reference: str,
    amount_pkr: int,
) -> PaymentTransaction:
    method = normalize_payment_method(method)
    transaction = db.query(PaymentTransaction).filter(PaymentTransaction.reference == reference).first()
    now = datetime.now(timezone.utc)
    if transaction is None:
        transaction = PaymentTransaction(
            user_id=user_id,
            method=method,
            reference=reference,
            amount_pkr=amount_pkr,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        db.add(transaction)
    else:
        transaction.method = method
        transaction.amount_pkr = amount_pkr
        transaction.status = "pending"
        transaction.updated_at = now
    db.commit()
    db.refresh(transaction)
    return transaction


def verify_payment_signature(method: str, reference: str, status: str, signature: str, amount_pkr: int) -> bool:
    try:
        secret = _secret_for_method(method)
    except ValueError:
        return False
    if not secret:
        return False
    signing_payload = f"{reference}|{status.lower()}|{amount_pkr}"
    expected = _sign_payload(secret, signing_payload)
    return hmac.compare_digest(expected, signature)


def mark_transaction_status(
    db: Session,
    reference: str,
    status: str,
    provider_txn_id: str | None = None,
) -> PaymentTransaction | None:
    transaction = db.query(PaymentTransaction).filter(PaymentTransaction.reference == reference).first()
    if transaction is None:
        return None
    transaction.status = status
    transaction.provider_txn_id = provider_txn_id
    transaction.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(transaction)
    return transaction


def activate_pro_subscription(db: Session, user_id: int, provider: str, provider_ref: str, days: int = 30) -> None:
    subscription = db.query(Subscription).filter(Subscription.user_id == user_id).first()
    expiry = datetime.now(timezone.utc) + timedelta(days=days)
    if subscription is None:
        subscription = Subscription(
            user_id=user_id,
            plan="pro",
            status="active",
            provider=provider,
            provider_ref=provider_ref,
            expiry=expiry,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(subscription)
    else:
        subscription.plan = "pro"
        subscription.status = "active"
        subscription.provider = provider
        subscription.provider_ref = provider_ref
        subscription.expiry = expiry
        subscription.updated_at = datetime.now(timezone.utc)
    db.commit()


def serialize_payment_debug(method: str, reference: str, amount_pkr: int, status: str) -> dict[str, Any]:
    method = normalize_payment_method(method)
    secret = _secret_for_method(method)
    return {
        "method": method,
        "reference": reference,
        "amount_pkr": amount_pkr,
        "status": status,
        "signature": _sign_payload(secret, f"{reference}|{status.lower()}|{amount_pkr}"),
    }
