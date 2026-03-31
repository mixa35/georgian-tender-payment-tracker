from __future__ import annotations

import calendar
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import Workbook, load_workbook

from tender_tracker.config import ExcelSettings
from tender_tracker.models import CompanyRecord, PaymentRecord

NO_RECORDS_TEXT = "ჩანაწერები არ არის"


def _normalize_company_id(value: object) -> str:
    digits = "".join(ch for ch in str(value).strip() if ch.isdigit())
    return digits.zfill(9) if digits else ""


def _normalize_company_name(value: object) -> str:
    return " ".join(str(value or "").split())


def _is_positive_overdue(value: object) -> bool:
    text = str(value or "").strip()
    if not text or text.startswith("-"):
        return False
    normalized = text.replace(",", ".")
    try:
        return Decimal(normalized) > 0
    except InvalidOperation:
        return False


def read_debtor_companies(workbook_path: Path, excel_settings: ExcelSettings) -> tuple[list[CompanyRecord], list[str]]:
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        sheet = workbook[excel_settings.input_sheet_name] if excel_settings.input_sheet_name else workbook.active

        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return [], []

        header = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
        index = {name: idx for idx, name in enumerate(header)}
        company_id_index = index[excel_settings.company_id_column]
        company_name_index = index[excel_settings.company_name_column]
        overdue_index = index[excel_settings.overdue_days_column]

        unique_by_company: dict[str, CompanyRecord] = {}
        unique_company_names: dict[str, str] = {}
        for row in rows[1:]:
            company_id = _normalize_company_id(row[company_id_index])
            company_name = _normalize_company_name(row[company_name_index])
            overdue_raw = str(row[overdue_index] or "").strip()
            if not company_id or not company_name or not _is_positive_overdue(overdue_raw):
                continue
            unique_by_company.setdefault(
                company_id,
                CompanyRecord(company_id=company_id, company_name=company_name, overdue_days_raw=overdue_raw),
            )
            unique_company_names.setdefault(company_name.casefold(), company_name)

        companies = sorted(unique_by_company.values(), key=lambda item: item.company_name.casefold())
        names = sorted(unique_company_names.values(), key=str.casefold)
        return companies, names
    finally:
        workbook.close()


def build_sheet_name(now: datetime) -> str:
    return f"{now.day} {calendar.month_abbr[now.month]}"


def write_output_workbook(
    workbook_path: Path,
    records: list[PaymentRecord],
    unique_company_names: list[str],
    run_started_at: datetime,
) -> str:
    workbook = load_workbook(workbook_path, keep_vba=True) if workbook_path.exists() else Workbook()

    sheet_name = build_sheet_name(run_started_at)
    if sheet_name in workbook.sheetnames:
        workbook.remove(workbook[sheet_name])
    sheet = workbook.create_sheet(title=sheet_name, index=0)

    headers = {
        "A1": "თანხა",
        "B1": "თარიღი",
        "C1": "კომპანია",
        "D1": "თანხა_რიცხვი",
        "E1": "თარიღი_თარიღად",
        "G1": "ყველა კომპანია",
    }
    for cell, value in headers.items():
        sheet[cell] = value

    for row_index, record in enumerate(records, start=2):
        sheet[f"A{row_index}"] = record.raw_amount
        sheet[f"B{row_index}"] = record.raw_payment_date
        sheet[f"C{row_index}"] = record.company_name
        sheet[f"D{row_index}"] = (
            f'=IF(A{row_index}="{NO_RECORDS_TEXT}","{NO_RECORDS_TEXT}",'
            f'IF(A{row_index}="","",VALUE(SUBSTITUTE(SUBSTITUTE(A{row_index}," ლარი",""),"`",""))))'
        )
        sheet[f"E{row_index}"] = (
            f'=IF(B{row_index}="","",DATE(MID(B{row_index},7,4),MID(B{row_index},4,2),LEFT(B{row_index},2)))'
        )

    for name_row, company_name in enumerate(unique_company_names, start=2):
        sheet[f"G{name_row}"] = company_name

    workbook.save(workbook_path)
    workbook.close()
    return sheet_name
