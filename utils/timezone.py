"""Timezone utilities for consistent datetime handling."""

from datetime import datetime, timezone, timedelta

# IST timezone (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    """Get current datetime in IST."""
    return datetime.now(IST)

def utc_to_ist(utc_datetime):
    """Convert UTC datetime to IST."""
    if utc_datetime is None:
        return None
    
    if utc_datetime.tzinfo is None:
        # Assume UTC if no timezone info
        utc_datetime = utc_datetime.replace(tzinfo=timezone.utc)
    
    return utc_datetime.astimezone(IST)

def ist_to_utc(ist_datetime):
    """Convert IST datetime to UTC for storage."""
    if ist_datetime is None:
        return None
    
    if ist_datetime.tzinfo is None:
        # Assume IST if no timezone info
        ist_datetime = ist_datetime.replace(tzinfo=IST)
    
    return ist_datetime.astimezone(timezone.utc)

def format_ist_datetime(dt, format_str='%Y-%m-%d %H:%M'):
    """Format datetime in IST timezone."""
    if dt is None:
        return None
    
    ist_dt = utc_to_ist(dt)
    return ist_dt.strftime(format_str)

def format_ist_iso(dt):
    """Format datetime in IST as ISO string for JavaScript."""
    if dt is None:
        return None
    
    ist_dt = utc_to_ist(dt)
    return ist_dt.isoformat()