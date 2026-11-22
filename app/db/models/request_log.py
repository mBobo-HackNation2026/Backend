"""Log zapytań do silnika uprawnień/kalkulatora - widoczny w panelu administracyjnym.

Tylko do odczytu (zob. ``app/admin/request_log.py``): panel pokazuje, co zostało
wysłane do silnika i jaki wynik zwrócił, ale NIE pozwala edytować zapisanych wpisów -
edycja cudzych zadeklarowanych danych "po fakcie" fałszowałaby historię oceny. Pętla
feedbacku (oznaczanie wpisu jako błędnego i wykorzystanie tego do poprawy reguł) jest
świadomie odłożona na później - zob. pamięć projektu `project-ebobo-admin-request-log`.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RequestLogEntry(Base):
    __tablename__ = "request_log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    endpoint: Mapped[str] = mapped_column(
        String(100)
    )  # "eligibility_check" | "calculate" | "compare_parental_leave"
    benefit_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status_code: Mapped[int] = mapped_column(Integer)
    request_payload: Mapped[dict] = mapped_column(JSON)
    response_payload: Mapped[dict] = mapped_column(JSON)
