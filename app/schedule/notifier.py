"""Tracks calendar changes made outside the agent (via the REST API)
so the agent can be notified on the next chat turn."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.schedule.database import Base, SessionLocal

NOTIFY_THREAD = "hyperagent-main"


class CalendarNotification(Base):
    __tablename__ = "calendar_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(20), nullable=False)  # created / updated / deleted
    event_title = Column(String(200), nullable=False)
    event_id = Column(Integer, nullable=False)
    detail = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)

    @staticmethod
    def ensure_table():
        Base.metadata.create_all(bind=SessionLocal().bind, checkfirst=True)


def _add_notification(action: str, title: str, event_id: int, detail: str = ""):
    CalendarNotification.ensure_table()
    db = SessionLocal()
    db.add(
        CalendarNotification(
            action=action,
            event_title=title,
            event_id=event_id,
            detail=detail,
        )
    )
    db.commit()
    db.close()


def notify_created(title: str, event_id: int):
    _add_notification("created", title, event_id)


def notify_updated(title: str, event_id: int):
    _add_notification("updated", title, event_id)


def notify_deleted(title: str, event_id: int):
    _add_notification("deleted", title, event_id)


def drain_notifications() -> str | None:
    """Consume all pending notifications and return them as a human-readable
    message, or None if there are none."""
    CalendarNotification.ensure_table()
    db = SessionLocal()
    rows = db.query(CalendarNotification).order_by(CalendarNotification.id).all()
    if not rows:
        db.close()
        return None

    lines = ["🔔 **日历页面操作记录（对话外发生）：**"]
    for r in rows:
        icon = {"created": "➕", "updated": "✏️", "deleted": "🗑️"}.get(r.action, "📌")
        lines.append(f"  {icon} {r.action}「{r.event_title}」(ID: {r.event_id})")

    # 消费后删除
    for r in rows:
        db.delete(r)
    db.commit()
    db.close()
    return "\n".join(lines)
