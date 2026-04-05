from __future__ import annotations

from datetime import date
import re

from bs4 import BeautifulSoup

from tender_tracker.models import PaymentRecord, SearchPage, SearchResultItem

NO_RECORDS_TEXT = "ჩანაწერები არ არის"
PAGE_PATTERN = re.compile(r"(\d+)\s+ჩანაწერი.*?გვერდი:\s*(\d+)/(\d+)", re.DOTALL)
DATE_PATTERN = re.compile(r"(\d{2}\.\d{2}\.\d{4})")
TENDER_PATTERN = re.compile(r"\b([A-Z0-9]{3,4}\d{4,})\b")
AMOUNT_PATTERN = re.compile(r"([0-9`.,]+)\s*ლარი")
ANNOUNCEMENT_LABEL_PATTERN = re.compile(r"შესყიდვის გამოცხადების თარიღი:\s*(\d{2}\.\d{2}\.\d{4})")


class ParseError(RuntimeError):
    """Raised when a tender response cannot be parsed safely."""


def parse_ddmmyyyy(value: str | None) -> date | None:
    if not value:
        return None
    match = DATE_PATTERN.search(value)
    if not match:
        return None
    day, month, year = match.group(1).split(".")
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def parse_pagination_text(text: str) -> tuple[int, int, int]:
    match = PAGE_PATTERN.search(text)
    if not match:
        return 0, 0, 0
    total_records, current_page, total_pages = match.groups()
    return int(current_page), int(total_pages), int(total_records)


def extract_tender_registration_number(text: str) -> str | None:
    match = TENDER_PATTERN.search(text)
    return match.group(1) if match else None


def extract_announcement_date(text: str) -> date | None:
    match = ANNOUNCEMENT_LABEL_PATTERN.search(text)
    if match:
        return parse_ddmmyyyy(match.group(1))
    return parse_ddmmyyyy(text)


def parse_search_page(html: str, company_id: str, company_name: str) -> SearchPage:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    page_number, total_pages, total_records = parse_pagination_text(text)
    table = soup.select_one("#list_apps_by_subject tbody")
    no_records = NO_RECORDS_TEXT in text and not soup.select("#list_apps_by_subject tbody tr[id]")
    items: list[SearchResultItem] = []

    if table:
        for row in table.select("tr[id]"):
            row_id = row.get("id", "")
            if not row_id.startswith("A"):
                continue
            row_text = " ".join(row.stripped_strings)
            items.append(
                SearchResultItem(
                    app_id=row_id[1:],
                    company_id=company_id,
                    company_name=company_name,
                    tender_registration_number=extract_tender_registration_number(row_text),
                    announcement_date=extract_announcement_date(row_text),
                    row_text=row_text,
                    page_number=page_number or 1,
                    total_pages=total_pages or 1,
                )
            )

    if items and total_pages == 0:
        page_number = 1
        total_pages = 1
        total_records = len(items)

    return SearchPage(
        items=items,
        page_number=page_number,
        total_pages=total_pages,
        total_records=total_records,
        no_records=no_records or (not items and NO_RECORDS_TEXT in text),
        raw_html=html,
    )


def extract_amount_text(text: str) -> str:
    cleaned = " ".join(text.replace("\xa0", " ").split())
    match = AMOUNT_PATTERN.search(cleaned)
    if not match:
        return cleaned
    return f"{match.group(1).replace(' ', '')} ლარი"


def parse_amount_number(raw_amount: str) -> float | None:
    if not raw_amount or raw_amount == NO_RECORDS_TEXT:
        return None
    cleaned = raw_amount.replace("ლარი", "").replace("`", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_payment_record(html: str, search_item: SearchResultItem | None = None) -> PaymentRecord:
    soup = BeautifulSoup(html, "html.parser")
    payment_table = soup.select_one("#agency_docs > div:last-of-type > table")
    if payment_table is None:
        raise ParseError("Payment table not found in agr_docs response")

    rows = payment_table.select("tbody > tr") or payment_table.select("tr")
    company_id = search_item.company_id if search_item else ""
    company_name = search_item.company_name if search_item else ""
    app_id_for_url = search_item.app_id if search_item else ""
    tender_url = (
        f"https://tenders.procurement.gov.ge/public/?go={app_id_for_url}&lang=ge"
        if app_id_for_url
        else None
    )
    if len(rows) < 2:
        return PaymentRecord(
            company_id=company_id,
            company_name=company_name,
            app_id=search_item.app_id if search_item else "",
            tender_registration_number=search_item.tender_registration_number if search_item else None,
            raw_amount=NO_RECORDS_TEXT,
            cleaned_amount=None,
            raw_payment_date="",
            parsed_payment_date=None,
            payment_exists=False,
            tender_url=tender_url,
            warnings=[],
        )

    last_row = rows[-1]
    last_row_text = " ".join(last_row.stripped_strings)
    warnings: list[str] = []
    tender_registration_number = search_item.tender_registration_number if search_item else None
    app_id = search_item.app_id if search_item else ""

    if NO_RECORDS_TEXT in last_row_text:
        return PaymentRecord(
            company_id=company_id,
            company_name=company_name,
            app_id=app_id,
            tender_registration_number=tender_registration_number,
            raw_amount=NO_RECORDS_TEXT,
            cleaned_amount=None,
            raw_payment_date="",
            parsed_payment_date=None,
            payment_exists=False,
            tender_url=tender_url,
            warnings=warnings,
        )

    cells = last_row.find_all("td")
    if len(cells) < 4:
        raise ParseError("Payment row did not contain enough cells")

    raw_amount = extract_amount_text(cells[0].get_text(" ", strip=True))
    raw_date = cells[3].get_text(" ", strip=True)
    parsed_date = parse_ddmmyyyy(raw_date)

    if parsed_date is None and len(cells) > 4:
        fallback = parse_ddmmyyyy(cells[4].get_text(" ", strip=True))
        if fallback:
            parsed_date = fallback
            raw_date = fallback.strftime("%d.%m.%Y")
            warnings.append("Used author column as payment-date fallback")

    amount_number = parse_amount_number(raw_amount)
    if amount_number is None:
        warnings.append("Could not convert payment amount to numeric value")

    return PaymentRecord(
        company_id=company_id,
        company_name=company_name,
        app_id=app_id,
        tender_registration_number=tender_registration_number,
        raw_amount=raw_amount,
        cleaned_amount=amount_number,
        raw_payment_date=raw_date,
        parsed_payment_date=parsed_date,
        payment_exists=True,
        tender_url=tender_url,
        warnings=warnings,
    )


def is_recent_tender(search_item: SearchResultItem, threshold_year: int = 2022) -> bool:
    registration = search_item.tender_registration_number
    if registration and len(registration) > 3:
        numeric_part = re.sub(r"\D", "", registration[3:])
        if numeric_part:
            return int(numeric_part) > (threshold_year - 1)
    if search_item.announcement_date is not None:
        return search_item.announcement_date.year >= threshold_year
    return True
