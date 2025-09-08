import stripe
import os
from typing import Dict, Any
from fastapi import HTTPException

# Initialize Stripe with the secret key from environment
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

class StripeService:
    @staticmethod
    async def create_payment_intent(amount: int, order_id: int) -> Dict[str, Any]:

        try:
            intent = stripe.PaymentIntent.create(
                amount=amount,
                currency='lkr',  # You can change this to 'lkr' for Sri Lankan Rupee
                automatic_payment_methods={
                    'enabled': True,
                },
                metadata={
                    'order_id': str(order_id)
                }
            )
            
            return {
                'client_secret': intent.client_secret,
                'payment_intent_id': intent.id
            }
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")
    
    @staticmethod
    async def retrieve_payment_intent(payment_intent_id: str) -> Dict[str, Any]:
        """Retrieve payment intent details from Stripe"""
        try:
            return stripe.PaymentIntent.retrieve(payment_intent_id)
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")
    
    @staticmethod
    async def verify_payment_success(payment_intent_id: str) -> bool:
        """Verify if payment was successful"""
        try:
            intent = await StripeService.retrieve_payment_intent(payment_intent_id)
            return intent.status == 'succeeded'
        except Exception:
            return False
