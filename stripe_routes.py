"""
stripe_routes.py — Stripe subscription billing blueprint.

Routes:
  POST /stripe/checkout  — create Stripe Checkout session, redirect user
  GET  /stripe/success   — post-checkout success page
  GET  /stripe/cancel    — user cancelled checkout
  POST /stripe/webhook   — Stripe webhook handler (signature-verified)
  POST /stripe/portal    — redirect to Stripe Customer Portal

Env vars required (set in Render dashboard):
  STRIPE_SECRET_KEY      — sk_live_... or sk_test_...
  STRIPE_PRICE_ID        — price_... for the DM Pro monthly recurring price
  STRIPE_WEBHOOK_SECRET  — whsec_... from the Stripe webhook endpoint config
"""

import os
import logging

import stripe
from flask import Blueprint, request, redirect, url_for, render_template, jsonify
from flask_login import login_required, current_user

import db_manager

log = logging.getLogger("dnd.stripe")

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID      = os.environ.get("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

stripe_bp = Blueprint("stripe_bp", __name__, url_prefix="/stripe")


# ── Checkout ──────────────────────────────────────────────────────────────────

@stripe_bp.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    if not stripe.api_key:
        return jsonify({"error": "Stripe not configured"}), 500

    # Create or retrieve a Stripe Customer
    customer_id = current_user.stripe_customer_id
    if not customer_id:
        customer    = stripe.Customer.create(email=current_user.email)
        customer_id = customer.id
        db_manager.update_user_subscription(
            current_user.id, current_user.subscription_status,
            stripe_customer_id=customer_id,
        )

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        subscription_data={"trial_period_days": 3},
        success_url=url_for("stripe_bp.stripe_success", _external=True)
                    + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=url_for("stripe_bp.stripe_cancel", _external=True),
        client_reference_id=str(current_user.id),
        allow_promotion_codes=True,
    )
    return redirect(session.url, code=303)


# ── Success / Cancel pages ────────────────────────────────────────────────────

@stripe_bp.route("/success")
def stripe_success():
    return render_template("stripe_success.html")


@stripe_bp.route("/cancel")
def stripe_cancel():
    return render_template("stripe_cancel.html")


# ── Customer Portal ───────────────────────────────────────────────────────────

@stripe_bp.route("/portal", methods=["GET", "POST"])
@login_required
def portal():
    if not current_user.stripe_customer_id:
        return redirect(url_for("stripe_bp.checkout"), code=303)

    portal_session = stripe.billing_portal.Session.create(
        customer=current_user.stripe_customer_id,
        return_url=url_for("gm_index", _external=True),
    )
    return redirect(portal_session.url, code=303)


# ── Webhook ───────────────────────────────────────────────────────────────────

@stripe_bp.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_data()   # raw bytes — must be read before any parsing
    sig     = request.headers.get("Stripe-Signature", "")

    if not STRIPE_WEBHOOK_SECRET:
        log.warning("STRIPE_WEBHOOK_SECRET not set — skipping signature check (dev only)")
        try:
            event = stripe.Event.construct_from(
                stripe.util.convert_to_stripe_object(request.get_json()), stripe.api_key
            )
        except Exception as e:
            log.error("Webhook parse error: %s", e)
            return "Bad request", 400
    else:
        try:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        except stripe.error.SignatureVerificationError:
            log.warning("Stripe webhook signature verification failed")
            return "Forbidden", 403

    _handle_event(event)
    return "", 200


def _handle_event(event):
    obj = event.data.object

    if event.type == "checkout.session.completed":
        if obj.get("mode") == "subscription":
            user_id     = obj.get("client_reference_id")
            customer_id = obj.get("customer")
            sub_id      = obj.get("subscription")
            if user_id:
                db_manager.update_user_subscription(
                    int(user_id), "active",
                    stripe_customer_id=customer_id,
                    stripe_sub_id=sub_id,
                )
                log.info("User %s activated subscription %s", user_id, sub_id)

    elif event.type in ("customer.subscription.updated", "customer.subscription.deleted"):
        customer_id = obj.get("customer")
        raw_status  = obj.get("status", "canceled")
        # Map Stripe statuses to our internal statuses
        status = {
            "active":    "active",
            "trialing":  "trialing",
            "past_due":  "past_due",
            "unpaid":    "past_due",
            "canceled":  "free",
            "incomplete": "free",
            "incomplete_expired": "free",
        }.get(raw_status, "free")

        row = db_manager.get_user_by_stripe_customer(customer_id)
        if row:
            db_manager.update_user_subscription(row["id"], status)
            log.info("User %s subscription status → %s", row["id"], status)

    elif event.type == "invoice.payment_failed":
        customer_id = obj.get("customer")
        row = db_manager.get_user_by_stripe_customer(customer_id)
        if row:
            db_manager.update_user_subscription(row["id"], "past_due")
            log.warning("Payment failed for user %s", row["id"])

    else:
        log.debug("Unhandled Stripe event: %s", event.type)
