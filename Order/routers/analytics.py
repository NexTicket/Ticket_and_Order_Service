from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func
from typing import Dict, Any, List
from database import get_session
from models import (
    UserOrder, UserTicket, Transaction, BulkTicket,
    OrderStatus, TicketStatus, TransactionStatus
)
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/dashboard")
def get_dashboard_analytics(session: Session = Depends(get_session)) -> Dict[str, Any]:
    """Get comprehensive dashboard analytics"""
    
    # Basic counts
    # Note: User count not available since Firebase manages users
    total_users = 0  # Would need to be fetched from Firebase Admin SDK
    # Note: Venues and Events are managed by external Event/Venue Service
    total_venues = 0  # Would be fetched from Event/Venue Service
    total_events = 0  # Would be fetched from Event/Venue Service
    total_bulk_tickets = len(session.exec(select(BulkTicket)).all())
    total_user_tickets = len(session.exec(select(UserTicket)).all())
    total_orders = len(session.exec(select(UserOrder)).all())
    
    # Order counts by status
    completed_orders = len(session.exec(
        select(UserOrder).where(UserOrder.status == OrderStatus.COMPLETED)
    ).all())
    
    # Recent activity (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_orders = len(session.exec(
        select(UserOrder).where(UserOrder.created_at >= week_ago)
    ).all())
    
    # Order status breakdown
    order_status_counts = {}
    for status in OrderStatus:
        count = len(session.exec(select(UserOrder).where(UserOrder.status == status)).all())
        order_status_counts[status.value] = count
    
    # Revenue calculation
    completed_orders_list = session.exec(
        select(UserOrder).where(UserOrder.status == OrderStatus.COMPLETED)
    ).all()
    total_revenue = sum(order.total_amount for order in completed_orders_list)
    
    return {
        "totals": {
            "users": total_users,
            "venues": total_venues,
            "events": total_events,
            "bulk_tickets": total_bulk_tickets,
            "user_tickets": total_user_tickets,
            "orders": total_orders,
        },
        "completed_orders": completed_orders,
        "recent_orders_7_days": recent_orders,
        "total_revenue": total_revenue,
        "order_status_breakdown": order_status_counts
    }

@router.get("/revenue/total")
def get_total_revenue(session: Session = Depends(get_session)) -> Dict[str, float]:
    """Get total revenue from completed orders"""
    completed_orders = session.exec(
        select(UserOrder).where(UserOrder.status == OrderStatus.COMPLETED)
    ).all()
    
    total_revenue = sum(order.total_amount for order in completed_orders)
    
    return {"total_revenue": total_revenue}

@router.get("/users/active")
def get_active_users(session: Session = Depends(get_session)) -> Dict[str, int]:
    """Get count of active Firebase users (based on recent activity)"""
    # For Firebase users, we don't have is_active field
    # Count users who have recent activity
    # Note: User count not available since Firebase manages users
    recent_users = 0  # Would need to be fetched from Firebase Admin SDK
    
    return {"active_users": recent_users}

@router.get("/tickets/summary")
def get_tickets_summary(session: Session = Depends(get_session)) -> Dict[str, Any]:
    """Get summary of ticket sales"""
    total_tickets = len(session.exec(select(UserTicket)).all())
    
    # Count tickets by status
    status_counts = {}
    for status in TicketStatus:
        count = len(session.exec(select(UserTicket).where(UserTicket.status == status)).all())
        status_counts[status.value] = count
    
    return {
        "total_tickets": total_tickets,
        "status_breakdown": status_counts
    }
