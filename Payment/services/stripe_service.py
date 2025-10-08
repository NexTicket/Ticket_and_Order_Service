import stripe
import os
from typing import Dict, Any
from fastapi import HTTPException

# Initialize Stripe with the secret key from environment
stripe_key = os.getenv("STRIPE_SECRET_KEY")
if not stripe_key:
    print("WARNING: STRIPE_SECRET_KEY environment variable not set")
    # Use a dummy test key for development if not set
    stripe_key = "sk_test_dummy"

stripe.api_key = stripe_key
print(f"Stripe API initialized with key: {stripe_key[:4]}...{stripe_key[-4:] if stripe_key else ''}")

class StripeService:
    @staticmethod
    async def create_payment_intent(amount: int, order_id: str, user_id: str) -> Dict[str, Any]:

        print(f"Creating payment intent for order_id: {order_id}, amount: {amount} cents")
        
        # Verify minimum amount (Stripe requires at least 50 cents equivalent)
        if amount < 50:
            raise HTTPException(
                status_code=400, 
                detail=f"Amount {amount} cents is below Stripe's minimum requirement of 50 cents"
            )
            
        try:
            if not stripe.api_key or stripe.api_key == "sk_test_dummy":
                print("WARNING: Using test Stripe environment")
                # Mock a payment intent response for testing when no Stripe key is available
                return {
                    'client_secret': f"pi_test_{order_id}_secret",
                    'payment_intent_id': f"pi_test_{order_id}"
                }
                
            # Create the actual payment intent with Stripe
            intent = stripe.PaymentIntent.create(
                amount=amount,  # amount in cents
                currency='lkr',  # Sri Lankan Rupee
                automatic_payment_methods={
                    'enabled': True,
                },
                metadata={
                    'order_id': order_id,
                    'user_id': user_id
                }
            )
            
            result = {
                'client_secret': intent.client_secret,
                'payment_intent_id': intent.id
            }
            print(f"Payment intent created: {result}")
            return result
        except stripe.error.StripeError as e:
            error_msg = f"Stripe error: {str(e)}"
            print(f"ERROR: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)
    
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
