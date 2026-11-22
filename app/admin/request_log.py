"""Zapis i odczyt logu zapytań do silnika uprawnień/kalkulatora (widoku "Wnioski" w
panelu administracyjnym). Zob. docstring ``app/db/models/request_log.py`` - tylko do
odczytu, bez edycji zapisanych wpisów.
"""

from sqlalchemy.orm import Session

from app.db.models.request_log import RequestLogEntry

_MAX_LIST_LIMIT = 200


def log_request(
    db: Session,
    *,
    endpoint: str,
    benefit_code: str | None,
    status_code: int,
    request_payload: dict,
    response_payload: dict,
    user_id: str | None = None,
) -> RequestLogEntry:
    entry = RequestLogEntry(
        endpoint=endpoint,
        benefit_code=benefit_code,
        status_code=status_code,
        request_payload=request_payload,
        response_payload=response_payload,
        user_id=user_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_request_log_entries(
    db: Session, *, benefit_code: str | None = None, limit: int = 50
) -> list[RequestLogEntry]:
    query = db.query(RequestLogEntry).order_by(RequestLogEntry.created_at.desc())
    if benefit_code is not None:
        query = query.filter(RequestLogEntry.benefit_code == benefit_code)
    return query.limit(min(limit, _MAX_LIST_LIMIT)).all()


def get_request_log_entry(db: Session, entry_id: int) -> RequestLogEntry | None:
    return db.query(RequestLogEntry).filter(RequestLogEntry.id == entry_id).one_or_none()
