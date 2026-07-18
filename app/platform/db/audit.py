from sqlalchemy import event
from sqlalchemy.orm import Session

from app.deps.context import account_id_ctx
from app.platform.db.mixins import TimestampMixin


def _current_account_id() -> str | None:
    value = account_id_ctx.get()
    return str(value) if value else None


@event.listens_for(Session, "before_flush")
def inject_audit_fields(session: Session, _flush_context, _instances) -> None:
    account_id = _current_account_id()
    if not account_id:
        return

    deleted = set(session.deleted)
    for entity in session.new:
        if isinstance(entity, TimestampMixin):
            if getattr(entity, "created_by", None) is None:
                entity.created_by = account_id
            if getattr(entity, "updated_by", None) is None:
                entity.updated_by = account_id

    for entity in session.dirty:
        if entity in deleted or not isinstance(entity, TimestampMixin):
            continue
        if session.is_modified(entity, include_collections=False):
            entity.updated_by = account_id
