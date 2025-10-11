"""
Test file for the Transaction Service
"""

import pytest
from sqlmodel import Session, create_engine, SQLModel
from datetime import datetime, timezone
import uuid

from models import UserOrder, TransactionStatus, OrderStatus
from Order.services.transaction_service import TransactionService

# Use in-memory SQLite for testing
engine = create_engine("sqlite:///:memory:")

def setup_module():
    """Set up test database"""
    SQLModel.metadata.create_all(engine)

def teardown_module():
    """Clean up after tests"""
    SQLModel.metadata.drop_all(engine)

def test_create_transaction():
    """Test creating a transaction"""
    with Session(engine) as session:
        # First create a test order
        order_id = str(uuid.uuid4())
        test_order = UserOrder(
            id=order_id,
            firebase_uid="test_user",
            total_amount=100.0,
            status=OrderStatus.PENDING
        )
        session.add(test_order)
        session.commit()
        
        # Create a transaction
        transaction = TransactionService.create_transaction(
            session=session,
            order_id=order_id,
            amount=100.0,
            payment_method="test",
            transaction_reference="Test transaction",
            status=TransactionStatus.PENDING
        )
        
        # Verify transaction was created
        assert transaction is not None
        assert transaction.order_id == order_id
        assert transaction.amount == 100.0
        assert transaction.payment_method == "test"
        assert transaction.transaction_reference == "Test transaction"
        assert transaction.status == TransactionStatus.PENDING
        assert transaction.transaction_id is not None
        
        # Test getting transactions for an order
        transactions = TransactionService.get_order_transactions(session, order_id)
        assert len(transactions) == 1
        assert transactions[0].id == transaction.id
        
        # Test updating transaction status
        updated_transaction = TransactionService.update_transaction_status(
            session=session,
            transaction_id=transaction.transaction_id,
            status=TransactionStatus.SUCCESS,
            transaction_reference="Test successful"
        )
        
        assert updated_transaction is not None
        assert updated_transaction.status == TransactionStatus.SUCCESS
        assert updated_transaction.transaction_reference == "Test successful"
        
        # Test deleting a transaction
        result = TransactionService.delete_transaction(session, transaction.transaction_id)
        assert result is True
        
        # Verify it's gone
        remaining_transactions = TransactionService.get_order_transactions(session, order_id)
        assert len(remaining_transactions) == 0

if __name__ == "__main__":
    setup_module()
    try:
        test_create_transaction()
        print("All tests passed!")
    finally:
        teardown_module()