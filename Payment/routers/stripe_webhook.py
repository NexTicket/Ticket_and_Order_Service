import stripe
import os
import logging
from fastapi import APIRouter, Request, HTTPException, Header, Depends
from sqlmodel import Session
from typing import Dict, Any
import os
import logging
import traceback
import stripe
import json

from database import get_session
from Order.services.order_service import OrderService
from Order.services.transaction_service import TransactionService
from models import OrderStatus, TransactionStatus
from Payment.services.stripe_service import StripeService
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get Stripe webhook secret from environment variables
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
if not STRIPE_WEBHOOK_SECRET:
    logger.warning("STRIPE_WEBHOOK_SECRET environment variable not set")
    # For development/testing purposes only, use a dummy webhook secret
    if os.getenv("ENVIRONMENT", "development") != "production":
        logger.warning("Using a dummy webhook secret for development")
        STRIPE_WEBHOOK_SECRET = "whsec_dummy_for_development"

router = APIRouter()

@router.get("/webhooks/stripe/test")
async def test_stripe_webhook():
    """
    Test endpoint to verify the webhook route is properly configured.
    """
    logger.info("Test webhook endpoint called")
    return {
        "status": "success", 
        "message": "Webhook endpoint is accessible",
        "webhook_secret_configured": bool(STRIPE_WEBHOOK_SECRET),
        "stripe_api_key_configured": bool(os.getenv("STRIPE_SECRET_KEY"))
    }

@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request, 
    stripe_signature: str = Header(None),
    session: Session = Depends(get_session)
):
    """
    This endpoint listens for events from Stripe. It's the secure way
    to confirm that a payment has succeeded and complete the order.
    """
    logger.info("Received Stripe webhook request")
    
    if not STRIPE_WEBHOOK_SECRET:
        logger.error("Stripe webhook secret is not configured")
        raise HTTPException(status_code=500, detail="Stripe webhook secret is not configured.")
        
    # Get the raw request body as Stripe requires it for verification
    try:
        payload = await request.body()
        logger.info(f"Received payload of length: {len(payload)}")
    except Exception as e:
        logger.error(f"Error reading request body: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Could not read request body: {str(e)}")

    # 1. Verify the event signature
    try:
        logger.info(f"Stripe signature header: {stripe_signature[:20]}..." if stripe_signature else "None")
        logger.info(f"Using webhook secret: {STRIPE_WEBHOOK_SECRET[:5]}..." if STRIPE_WEBHOOK_SECRET else "None")
        
        event = stripe.Webhook.construct_event(
            payload=payload, 
            sig_header=stripe_signature, 
            secret=STRIPE_WEBHOOK_SECRET
        )
        logger.info(f"Successfully verified event: {event.get('type')}")
    except ValueError as e:
        # Invalid payload
        logger.error(f"Invalid payload: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        logger.error(f"Invalid signature: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid signature: {e}")
    except Exception as e:
        # Catch all for any other errors during verification
        logger.error(f"Unexpected error verifying webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error verifying webhook: {str(e)}")

    # 2. Handle the 'payment_intent.succeeded' event
    if event['type'] == 'payment_intent.succeeded':
        try:
            logger.info("Processing payment_intent.succeeded event")
            payment_intent = event['data']['object'] # contains a stripe.PaymentIntent
            logger.info(f"Payment intent ID: {payment_intent.get('id')}")
            
            # Log full payment intent details for debugging
            logger.info(f"Payment intent metadata: {payment_intent.get('metadata', {})}")
            
            # Extract the order_id you stored in the metadata
            order_id = payment_intent.get('metadata', {}).get('order_id')
            
            if not order_id:
                # We need the order_id to proceed
                logger.error("Missing order_id in payment intent metadata")
                raise HTTPException(status_code=400, detail="Missing order_id in payment intent metadata.")
            
            logger.info(f"Found order_id in metadata: {order_id}")
            
            payment_intent_id = payment_intent.get('id')
            if not payment_intent_id:
                logger.error("Missing payment intent ID")
                raise HTTPException(status_code=400, detail="Missing payment intent ID.")
                
            logger.info(f"Payment intent ID: {payment_intent_id}")
        except Exception as e:
            logger.error(f"Error processing payment intent: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error processing payment intent: {str(e)}")

        try:
            # Get the order to verify it exists
            logger.info(f"Looking up order with ID: {order_id}")
            order = OrderService.get_order(session, order_id)
            if not order:
                logger.error(f"Order {order_id} not found")
                raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
            
            logger.info(f"Found order with ID: {order_id}, status: {order.status}")
            logger.info(f"Order payment_intent_id: {order.payment_intent_id}")
            
            # Complete the order using the existing complete_order method
            logger.info(f"Processing order completion for order_id: {order_id}, payment_intent_id: {payment_intent_id}")
            
            # Create a transaction record for this payment
            try:
                # First, create a transaction record using TransactionService
                logger.info(f"Creating transaction record for order: {order_id}")
                order = OrderService.get_order(session, order_id)
                if order:
                    # Create a transaction or update existing one if it exists
                    existing_transactions = TransactionService.get_order_transactions(session, order_id)
                    
                    if existing_transactions:
                        # Update the existing transaction status
                        for transaction in existing_transactions:
                            TransactionService.update_transaction_status(
                                session=session,
                                transaction_id=transaction.transaction_id,
                                status=TransactionStatus.SUCCESS,
                                transaction_reference=f"Payment successful: {payment_intent_id}"
                            )
                    else:
                        # Create a new transaction if none exists
                        TransactionService.create_transaction(
                            session=session,
                            order_id=order_id,
                            amount=order.total_amount,
                            payment_method="stripe",
                            transaction_reference=f"Payment successful: {payment_intent_id}",
                            status=TransactionStatus.SUCCESS
                        )
                    logger.info(f"Transaction record created/updated successfully for order: {order_id}")
                
                # Then complete the order
                completed_order = await OrderService.complete_order(
                    session=session, 
                    order_id=order_id,
                    payment_intent_id=payment_intent_id
                )
                logger.info(f"Order {order_id} completed successfully")
            except Exception as inner_e:
                logger.error(f"Error in OrderService.complete_order: {str(inner_e)}")
                logger.error(f"Exception type: {type(inner_e).__name__}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                raise inner_e
            
        except Exception as e:
            # If your database update fails, log the error and tell Stripe
            # to retry later by returning a 500 error
            logger.error(f"Error completing order {order_id}: {str(e)}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            session.rollback()
            raise HTTPException(status_code=500, detail=f"Server error during order completion: {str(e)}")
    
    elif event['type'] == 'payment_intent.payment_failed':
        payment_intent = event['data']['object']
        order_id = payment_intent.get('metadata', {}).get('order_id')
        
        if order_id:
            logger.info(f"Payment failed for order {order_id}")
            try:
                # Get the order to create a failed transaction
                order = OrderService.get_order(session, order_id)
                if order:
                    # Create or update transaction record for the failed payment
                    existing_transactions = TransactionService.get_order_transactions(session, order_id)
                    
                    if existing_transactions:
                        # Update the existing transaction status
                        for transaction in existing_transactions:
                            TransactionService.update_transaction_status(
                                session=session,
                                transaction_id=transaction.transaction_id,
                                status=TransactionStatus.FAILED,
                                transaction_reference="Payment failed"
                            )
                    else:
                        # Create a new transaction for the failed payment
                        TransactionService.create_transaction(
                            session=session,
                            order_id=order_id,
                            amount=order.total_amount,
                            payment_method="stripe",
                            transaction_reference="Payment failed",
                            status=TransactionStatus.FAILED
                        )
                
                # Cancel the order
                OrderService.cancel_order(session, order_id)
                logger.info(f"Order {order_id} cancelled due to payment failure")
            except Exception as e:
                logger.error(f"Error cancelling order {order_id}: {str(e)}")
                session.rollback()
    
    else:
        # For other event types, just log them
        logger.info(f"Received unhandled event type: {event['type']}")

    # If we get to this point, it means we've successfully processed the webhook
    # or it was an event type we don't need to handle specially
    
    # Always return 200 OK for webhooks that we've processed (even just by logging them)
    # This prevents Stripe from retrying webhooks unnecessarily
    logger.info(f"Successfully processed webhook event: {event.get('type')}")
    return {"status": "success", "event_type": event.get('type')}