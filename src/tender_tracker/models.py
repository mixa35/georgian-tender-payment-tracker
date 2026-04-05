from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(slots=True)
class CompanyRecord:
    company_id: str
    company_name: str
    overdue_days_raw: str


@dataclass(slots=True)
class SearchResultItem:
    app_id: str
    company_id: str
    company_name: str
    tender_registration_number: str | None
    announcement_date: date | None
    row_text: str
    page_number: int
    total_pages: int


@dataclass(slots=True)
class SearchPage:
    items: list[SearchResultItem]
    page_number: int
    total_pages: int
    total_records: int
    no_records: bool
    raw_html: str = ""


@dataclass(slots=True)
class PaymentRecord:
    company_id: str
    company_name: str
    app_id: str
    tender_registration_number: str | None
    raw_amount: str
    cleaned_amount: float | None
    raw_payment_date: str
    parsed_payment_date: date | None
    payment_exists: bool
    tender_url: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RunSummary:
    companies_scanned: int = 0
    companies_skipped: int = 0
    tenders_discovered: int = 0
    tenders_fetched: int = 0
    rows_written: int = 0
    retries: int = 0
    parse_failures: int = 0


@dataclass(slots=True)
class RunState:
    run_id: str
    started_at: str
    command: str
    args: dict[str, Any]
    stage: str = "search"
    queued_companies: list[dict[str, Any]] = field(default_factory=list)
    queued_tenders: list[dict[str, Any]] = field(default_factory=list)
    processed_company_ids: list[str] = field(default_factory=list)
    completed_tender_ids: list[str] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)
    records: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunState":
        return cls(**payload)


def json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "__dict__"):
        return value.__dict__
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")
