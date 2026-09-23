from datetime import date, datetime
from zoneinfo import ZoneInfo
import os

def local_today() -> date:
    return datetime.now(ZoneInfo(os.environ.get("APP_TIMEZONE", "Asia/Yekaterinburg"))).date()

def deadline_state(due_date: date, status: str, today: date) -> str:
    if status == "done":
        return "closed"
    days = (due_date - today).days
    if days < 0:
        return "overdue"
    if days <= 7:
        return "due_soon"
    return "upcoming"

def reminder_offset(due_date: date, today: date) -> str | None:
    days = (due_date - today).days
    if days < 0:
        return "overdue"
    if days <= 1:
        return "1_day"
    if days <= 3:
        return "3_days"
    if days <= 7:
        return "7_days"
    return None

