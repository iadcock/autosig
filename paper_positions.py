"""
Paper position tracking for simulated trading.
Maintains an in-memory index backed by JSONL persistence.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


POSITIONS_FILE = "data/paper_open_positions.jsonl"


class PositionLeg(BaseModel):
    """A single leg of an options position."""
    side: str  # BUY or SELL
    quantity: int
    strike: float
    option_type: str  # CALL or PUT
    expiration: str  # YYYY-MM-DD


class PaperPosition(BaseModel):
    """Represents a paper trading position."""
    position_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: Literal["OPEN", "CLOSED"] = "OPEN"
    opened_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    closed_at: Optional[str] = None
    source_post_id: str = ""
    underlying: str
    instrument_type: Literal["STOCK", "OPTION", "SPREAD", "INDEX_OPTION"]
    legs: List[PositionLeg] = Field(default_factory=list)
    quantity: int = 1
    open_intent: Dict[str, Any] = Field(default_factory=dict)
    close_intent: Optional[Dict[str, Any]] = None


# In-memory position cache
_positions_cache: List[PaperPosition] = []
_cache_loaded: bool = False


def _ensure_file_exists() -> None:
    """Ensure the positions file and directory exist."""
    os.makedirs(os.path.dirname(POSITIONS_FILE), exist_ok=True)
    if not os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, "w") as f:
            pass  # Create empty file


def load_positions() -> List[PaperPosition]:
    """Load all positions from JSONL file into memory."""
    global _positions_cache, _cache_loaded
    
    _ensure_file_exists()
    _positions_cache = []
    
    try:
        with open(POSITIONS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    # Convert leg dicts to PositionLeg objects
                    if "legs" in data and data["legs"]:
                        data["legs"] = [PositionLeg(**leg) if isinstance(leg, dict) else leg for leg in data["legs"]]
                    _positions_cache.append(PaperPosition(**data))
    except Exception as e:
        print(f"Error loading positions: {e}")
        _positions_cache = []
    
    _cache_loaded = True
    return _positions_cache


def _get_positions() -> List[PaperPosition]:
    """Get positions, loading from file if needed."""
    global _cache_loaded
    if not _cache_loaded:
        load_positions()
    return _positions_cache


def _save_all_positions() -> None:
    """Rewrite the entire positions file from cache."""
    _ensure_file_exists()
    with open(POSITIONS_FILE, "w") as f:
        for pos in _positions_cache:
            f.write(pos.model_dump_json() + "\n")


def append_open_position(position: PaperPosition) -> None:
    """Add a new open position and persist it."""
    global _positions_cache
    _get_positions()  # Ensure loaded
    _positions_cache.append(position)
    
    # Append to file
    _ensure_file_exists()
    with open(POSITIONS_FILE, "a") as f:
        f.write(position.model_dump_json() + "\n")


def mark_position_closed(position_id: str, close_intent: Dict[str, Any]) -> bool:
    """Mark a position as closed and update the file."""
    positions = _get_positions()
    
    for pos in positions:
        if pos.position_id == position_id and pos.status == "OPEN":
            pos.status = "CLOSED"
            pos.closed_at = datetime.utcnow().isoformat()
            pos.close_intent = close_intent
            _save_all_positions()
            return True
    
    return False


def get_open_positions() -> List[PaperPosition]:
    """Get all currently open positions."""
    return [p for p in _get_positions() if p.status == "OPEN"]


def get_open_positions_for_ticker(ticker: str) -> List[PaperPosition]:
    """Get all open positions for a specific ticker."""
    return [
        p for p in _get_positions() 
        if p.status == "OPEN" and p.underlying.upper() == ticker.upper()
    ]


def _normalize_leg_signature(legs: List[PositionLeg]) -> tuple:
    """Create a normalized signature for leg comparison."""
    if not legs:
        return ()
    
    sorted_legs = sorted(
        legs,
        key=lambda l: (l.expiration, l.strike, l.option_type, l.side)
    )
    
    return tuple(
        (leg.expiration, leg.strike, leg.option_type, leg.side, leg.quantity)
        for leg in sorted_legs
    )


def _legs_match(pos_legs: List[PositionLeg], signal_legs: List[Dict]) -> bool:
    """Check if position legs match signal legs (ignoring side direction)."""
    if not pos_legs or not signal_legs:
        return False
    
    if len(pos_legs) != len(signal_legs):
        return False
    
    # Normalize position legs
    pos_normalized = sorted(
        [(l.expiration, l.strike, l.option_type) for l in pos_legs]
    )
    
    # Normalize signal legs
    signal_normalized = sorted([
        (l.get("expiration", ""), l.get("strike", 0), l.get("option_type", ""))
        for l in signal_legs
    ])
    
    return pos_normalized == signal_normalized


def find_open_position_for_exit(parsed_signal: Dict[str, Any]) -> Optional[PaperPosition]:
    """
    Find an open position that matches an EXIT signal.
    
    Matching priority:
    1. Exact match: ticker + exact leg signature
    2. Fallback: ticker + most recent OPEN position
    3. None if no match
    """
    ticker = parsed_signal.get("ticker", "").upper()
    if not ticker:
        return None
    
    open_positions = get_open_positions_for_ticker(ticker)
    if not open_positions:
        return None
    
    # Sort by opened_at descending (most recent first)
    open_positions.sort(key=lambda p: p.opened_at, reverse=True)
    
    signal_legs = parsed_signal.get("legs", [])
    
    # Try exact leg match first
    if signal_legs:
        for pos in open_positions:
            if _legs_match(pos.legs, signal_legs):
                return pos
    
    # Fallback to most recent open position for this ticker
    return open_positions[0] if open_positions else None


def clear_all_positions() -> None:
    """Clear all positions (for testing)."""
    global _positions_cache, _cache_loaded
    _positions_cache = []
    _cache_loaded = True
    _ensure_file_exists()
    with open(POSITIONS_FILE, "w") as f:
        pass
