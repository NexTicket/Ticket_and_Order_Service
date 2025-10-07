from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from typing import List
from database import get_session
from models import (
    Transaction, TransactionCreate, TransactionRead, TransactionUpdate,
    UserOrder, OrderStatus, TransactionStatus
)

router = APIRouter()

@router.post("/", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(transaction: TransactionCreate, session: Session = Depends(get_session)):
    """Create a new transaction"""
    # Check if order exists
    order = session.get(UserOrder, transaction.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.status not in [OrderStatus.PENDING]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot create transaction for order with status: {order.status}"
        )
    
    db_transaction = Transaction.model_validate(transaction)
    session.add(db_transaction)
    session.commit()
    session.refresh(db_transaction)
    return db_transaction

@router.get("/", response_model=List[TransactionRead])
def get_transactions(
    skip: int = 0, 
    limit: int = 100,
    order_id: int = None,
    status: TransactionStatus = None,
    session: Session = Depends(get_session)
):
    """Get all transactions with optional filtering"""
    statement = select(Transaction).offset(skip).limit(limit)
    
    if order_id:
        statement = statement.where(Transaction.order_id == order_id)
    if status:
        statement = statement.where(Transaction.status == status)
    
    transactions = session.exec(statement).all()
    return transactions

@router.get("/{transaction_id}", response_model=TransactionRead)
def get_transaction(transaction_id: int, session: Session = Depends(get_session)):
    """Get a specific transaction by ID"""
    transaction = session.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction

@router.put("/{transaction_id}", response_model=TransactionRead)
def update_transaction(
    transaction_id: int,
    transaction_update: TransactionUpdate,
    session: Session = Depends(get_session)
):
    """Update a transaction"""
    transaction = session.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    transaction_data = transaction_update.model_dump(exclude_unset=True)
    for field, value in transaction_data.items():
        setattr(transaction, field, value)
    
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    
    # Update order status based on transaction status
    if transaction.status == TransactionStatus.SUCCESS:
        order = session.get(UserOrder, transaction.order_id)
        order.status = OrderStatus.COMPLETED
        session.add(order)
        session.commit()
    
    return transaction

@router.patch("/{transaction_id}/status", response_model=TransactionRead)
def update_transaction_status(
    transaction_id: int,
    new_status: TransactionStatus,
    session: Session = Depends(get_session)
):
    """Update transaction status"""
    transaction = session.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    transaction.status = new_status
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    
    # Update order status based on transaction status
    order = session.get(UserOrder, transaction.order_id)
    if new_status == TransactionStatus.SUCCESS:
        order.status = OrderStatus.COMPLETED
    elif new_status == TransactionStatus.FAILED:
        order.status = OrderStatus.CANCELLED
    
    session.add(order)
    session.commit()
    
    return transaction

@router.post("/{transaction_id}/refund", response_model=TransactionRead)
def process_refund(transaction_id: int, session: Session = Depends(get_session)):
    """Process a refund for a transaction"""
    transaction = session.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    if transaction.status != TransactionStatus.SUCCESS:
        raise HTTPException(
            status_code=400,
            detail="Can only refund successful transactions"
        )
    
    # Update transaction status
    transaction.status = TransactionStatus.REFUNDED
    session.add(transaction)
    
    # Update order status
    order = session.get(UserOrder, transaction.order_id)
    order.status = OrderStatus.CANCELLED
    session.add(order)
    
    session.commit()
    session.refresh(transaction)
    
    return transaction

@router.get("/order/{order_id}", response_model=List[TransactionRead])
def get_order_transactions(order_id: int, session: Session = Depends(get_session)):
    """Get all transactions for a specific order"""
    order = session.get(UserOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    statement = select(Transaction).where(Transaction.order_id == order_id)
    transactions = session.exec(statement).all()
    return transactions
