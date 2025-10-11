"""
Order Cleanup Service
This service handles the automatic expiration of pending orders that have exceeded their timeout.
Redis keys are automatically expired based on TTL, so we only need to update the database.
"""

import logging
from datetime import datetime, timezone, timedelta
from sqlmodel import Session, select, update
from models import UserOrder, OrderStatus, TransactionStatus
from database import engine
from Database.redis_client import ORDER_EXPIRATION_SECONDS
from Order.services.transaction_service import TransactionService

logger = logging.getLogger(__name__)

def cleanup_expired_orders():
    """
    Find and process expired pending orders:
    1. Find all pending orders that have exceeded their expiration time
    2. Update their status to EXPIRED in the database
    3. Remove corresponding seat locks from Redis
    """
    logger.info("Running expired order cleanup job")
    
    # Calculate the expiration threshold time
    expiration_threshold = datetime.now(timezone.utc) - timedelta(seconds=ORDER_EXPIRATION_SECONDS)
    
    try:
        with Session(engine) as session:
            # Query for expired pending orders
            expired_orders_query = select(UserOrder).where(
                UserOrder.status == OrderStatus.PENDING,
                UserOrder.created_at < expiration_threshold
            )
            
            expired_orders = session.exec(expired_orders_query).all()
            
            if not expired_orders:
                logger.info("No expired orders found")
                return
                
            logger.info(f"Found {len(expired_orders)} expired orders to process")
            
            for order in expired_orders:
                try:
                    # Update order status to EXPIRED
                    order.status = OrderStatus.EXPIRED
                    order.updated_at = datetime.now(timezone.utc)
                    session.add(order)
                    
                    # Create or update transaction record for the expired order
                    try:
                        # Check for existing transactions
                        existing_transactions = TransactionService.get_order_transactions(session, order.id)
                        
                        if existing_transactions:
                            # Update existing transactions
                            for transaction in existing_transactions:
                                TransactionService.update_transaction_status(
                                    session=session,
                                    transaction_id=transaction.transaction_id,
                                    status=TransactionStatus.FAILED,
                                    transaction_reference="Order expired"
                                )
                        else:
                            # Create a new transaction record for the expired order
                            TransactionService.create_transaction(
                                session=session,
                                order_id=order.id,
                                amount=order.total_amount,
                                payment_method="system",
                                status=TransactionStatus.FAILED,
                                transaction_reference="Order expired automatically"
                            )
                        logger.info(f"Transaction record created/updated for expired order {order.id}")
                    except Exception as tx_error:
                        logger.error(f"Error creating transaction for expired order {order.id}: {str(tx_error)}")
                    
                    # No need to handle Redis, as keys will automatically expire
                    # based on ORDER_EXPIRATION_SECONDS
                    
                    logger.info(f"Expired order {order.id} processed (status updated to EXPIRED)")
                    
                except Exception as e:
                    logger.error(f"Error processing expired order {order.id}: {str(e)}")
                    # Continue with other orders even if one fails
            
            # Commit all the changes to the database
            session.commit()
            logger.info(f"Successfully processed {len(expired_orders)} expired orders")
            
    except Exception as e:
        logger.error(f"Error during expired orders cleanup: {str(e)}")