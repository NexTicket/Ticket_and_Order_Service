"""
Transaction Service
This service handles creating and managing transaction records for the ticket system.
"""

import logging
import uuid
from datetime import datetime, timezone
from sqlmodel import Session, select
from typing import Optional, List

from models import Transactions, TransactionsCreate, TransactionsUpdate, TransactionStatus, UserOrder

logger = logging.getLogger(__name__)

class TransactionService:
    """Service for managing transaction records"""
    
    @staticmethod
    def create_transaction(
        session: Session, 
        order_id: str, 
        amount: float, 
        payment_method: str = "stripe", 
        transaction_reference: Optional[str] = None,
        status: TransactionStatus = TransactionStatus.PENDING
    ) -> Optional[Transactions]:
        """
        Create a new transaction record
        
        Args:
            session: Database session
            order_id: The order ID associated with this transaction
            amount: Transaction amount
            payment_method: Payment method (default: stripe)
            transaction_reference: Additional reference information about the transaction
            status: Transaction status (default: PENDING)
            
        Returns:
            The created transaction record or None if an error occurred
        """
        try:
            # First check if order exists
            order = session.get(UserOrder, order_id)
            if not order:
                logger.error(f"Cannot create transaction: Order {order_id} not found")
                return None
                
            # Create transaction record
            transaction_data = TransactionsCreate(
                order_id=order_id,
                amount=amount,
                payment_method=payment_method,
                transaction_reference=transaction_reference,
                status=status
            )
            
            transaction = Transactions(**transaction_data.dict())
            
            # Add and commit to database
            session.add(transaction)
            session.commit()
            session.refresh(transaction)
            
            logger.info(f"Created transaction {transaction.transaction_id} for order {order_id} with status {status}")
            return transaction
            
        except Exception as e:
            logger.error(f"Error creating transaction for order {order_id}: {str(e)}")
            session.rollback()
            return None
    
    @staticmethod
    def update_transaction_status(
        session: Session, 
        transaction_id: str, 
        status: TransactionStatus, 
        transaction_reference: Optional[str] = None
    ) -> Optional[Transactions]:
        """
        Update an existing transaction's status
        
        Args:
            session: Database session
            transaction_id: Transaction ID to update
            status: New transaction status
            transaction_reference: Optional reference information to add/update
            
        Returns:
            Updated transaction or None if an error occurred
        """
        try:
            # Find transaction by transaction_id
            stmt = select(Transactions).where(Transactions.transaction_id == transaction_id)
            transaction = session.exec(stmt).first()
            
            if not transaction:
                logger.error(f"Transaction {transaction_id} not found")
                return None
                
            # Update status and reference if provided
            transaction.status = status
            transaction.updated_at = datetime.now(timezone.utc)
            
            if transaction_reference:
                transaction.transaction_reference = transaction_reference
                
            # Commit changes
            session.add(transaction)
            session.commit()
            session.refresh(transaction)
            
            logger.info(f"Updated transaction {transaction_id} status to {status}")
            return transaction
            
        except Exception as e:
            logger.error(f"Error updating transaction {transaction_id}: {str(e)}")
            session.rollback()
            return None
            
    @staticmethod
    def get_order_transactions(session: Session, order_id: str) -> List[Transactions]:
        """
        Get all transactions for a specific order
        
        Args:
            session: Database session
            order_id: Order ID to find transactions for
            
        Returns:
            List of transactions for the order
        """
        stmt = select(Transactions).where(Transactions.order_id == order_id)
        return session.exec(stmt).all()
        
    @staticmethod
    def delete_transaction(session: Session, transaction_id: str) -> bool:
        """
        Delete a transaction record
        
        Args:
            session: Database session
            transaction_id: ID of the transaction to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Find transaction by transaction_id
            stmt = select(Transactions).where(Transactions.transaction_id == transaction_id)
            transaction = session.exec(stmt).first()
            
            if not transaction:
                logger.error(f"Cannot delete: Transaction {transaction_id} not found")
                return False
                
            # Delete the transaction
            session.delete(transaction)
            session.commit()
            
            logger.info(f"Deleted transaction {transaction_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting transaction {transaction_id}: {str(e)}")
            session.rollback()
            return False