"""
Utility functions for handling complex seat structures
"""
import json
from typing import List, Union
from models import SeatID


def seat_list_to_json_str(seats: List[SeatID]) -> str:
    """Convert list of SeatID objects to JSON string for storage"""
    return json.dumps([{"section": s.section, "row_id": s.row_id, "col_id": s.col_id} for s in seats])


def json_str_to_seat_list(json_str: str) -> List[SeatID]:
    """Parse JSON string to list of SeatID objects"""
    data = json.loads(json_str)
    return [SeatID(**seat_dict) for seat_dict in data]


def seat_to_redis_key(event_id: int, seat: SeatID) -> str:
    """Generate Redis key for a specific seat lock"""
    return f"seat_lock:{event_id}:{seat.to_string()}"


def seats_equal(seat1: Union[SeatID, dict], seat2: Union[SeatID, dict]) -> bool:
    """Check if two seats are equal"""
    if isinstance(seat1, dict):
        seat1 = SeatID(**seat1)
    if isinstance(seat2, dict):
        seat2 = SeatID(**seat2)
    
    return (seat1.section == seat2.section and 
            seat1.row_id == seat2.row_id and 
            seat1.col_id == seat2.col_id)


def find_seat_in_list(seat: SeatID, seat_list: List[SeatID]) -> int:
    """Find index of seat in list, return -1 if not found"""
    for i, s in enumerate(seat_list):
        if seats_equal(seat, s):
            return i
    return -1


def remove_seats_from_list(seats_to_remove: List[SeatID], seat_list: List[SeatID]) -> List[SeatID]:
    """Remove seats from a list"""
    result = []
    for seat in seat_list:
        if find_seat_in_list(seat, seats_to_remove) == -1:
            result.append(seat)
    return result


def seats_in_list(seats: List[SeatID], seat_list: List[SeatID]) -> List[SeatID]:
    """Return seats that are in the seat_list"""
    result = []
    for seat in seats:
        if find_seat_in_list(seat, seat_list) != -1:
            result.append(seat)
    return result
