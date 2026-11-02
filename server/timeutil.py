"""
Xử lý thời gian. Cột thời gian trong MySQL là DATETIME(3) → lưu đến mili giây (cần cho đo độ trễ).
Ra JSON / template luôn là chuỗi ISO 'YYYY-MM-DDTHH:MM:SS.mmm'.
"""
from datetime import datetime


def _ms(dt):
    return dt.replace(microsecond=dt.microsecond // 1000 * 1000)


def now_dt():
    return _ms(datetime.now())


def parse_time(value):
    """Chấp nhận datetime, '2026-10-13 10:17:07', '2026-10-13T10:17:07', '...07.512', '2026-10-13T10:17'."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).strip().replace(' ', 'T'))
    except ValueError:
        return None


def normalize_time(value):
    """Chuỗi thời gian từ Client/Website → datetime (làm tròn mili giây) để lưu / lọc trong MySQL."""
    dt = parse_time(value)
    return _ms(dt) if dt else None


def iso(dt):
    return dt.isoformat(timespec='milliseconds') if dt else None


def seconds_between(a, b):
    da, db = parse_time(a), parse_time(b)
    if da is None or db is None:
        return None
    return round((db - da).total_seconds(), 3)
