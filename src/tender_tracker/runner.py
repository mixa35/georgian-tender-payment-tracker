from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from tender_tracker.config import AppSettings
from tender_tracker.excel import read_debtor_companies, write_output_workbook
from tender_tracker.models import CompanyRecord, PaymentRecord, RunState, SearchResultItem
from tender_tracker.state import RunStateStore
from tender_tracker.storage import BaseStorage
from tender_tracker.tender_client import TenderClientError, TenderPortalClient


def _serialize_record(record: PaymentRecord) -> dict:
    payload = asdict(record)
    payload["parsed_payment_date"] = record.parsed_payment_date.isoformat() if record.parsed_payment_date else None
    return payload


def _serialize_search_item(item: SearchResultItem) -> dict:
    payload = asdict(item)
    payload["announcement_date"] = item.announcement_date.isoformat() if item.announcement_date else None
    return payload


def _deserialize_record(payload: dict) -> PaymentRecord:
    parsed_date = payload.get("parsed_payment_date")
    return PaymentRecord(
        company_id=payload["company_id"],
        company_name=payload["company_name"],
        app_id=payload["app_id"],
        tender_registration_number=payload.get("tender_registration_number"),
        raw_amount=payload["raw_amount"],
        cleaned_amount=payload.get("cleaned_amount"),
        raw_payment_date=payload.get("raw_payment_date", ""),
        parsed_payment_date=datetime.fromisoformat(parsed_date).date() if parsed_date else None,
        payment_exists=payload.get("payment_exists", False),
        warnings=payload.get("warnings", []),
    )


def _deserialize_search_item(payload: dict) -> SearchResultItem:
    announcement = payload.get("announcement_date")
    return SearchResultItem(
        app_id=payload["app_id"],
        company_id=payload["company_id"],
        company_name=payload["company_name"],
        tender_registration_number=payload.get("tender_registration_number"),
        announcement_date=datetime.fromisoformat(announcement).date() if announcement else None,
        row_text=payload.get("row_text", ""),
        page_number=payload.get("page_number", 1),
        total_pages=payload.get("total_pages", 1),
    )


class TenderTrackerApp:
    def __init__(
        self,
        settings: AppSettings,
        storage: BaseStorage,
        state_store: RunStateStore,
        client: TenderPortalClient,
        logger,
        work_root: Path,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.state_store = state_store
        self.client = client
        self.logger = logger
        self.work_root = work_root
        self.local_input = self.work_root / "input.xlsx"
        self.local_output = self.work_root / "output.xlsm"
        self.local_debug = self.work_root / "debug"

    def _download_input(self) -> tuple[list[CompanyRecord], list[str]]:
        found = self.storage.download_file(self.settings.storage.onedrive.input_path, self.local_input)
        if not found:
            raise FileNotFoundError("Input workbook was not found in configured storage")
        return read_debtor_companies(self.local_input, self.settings.excel)

    def _download_output_if_present(self) -> None:
        self.storage.download_file(self.settings.storage.onedrive.output_path, self.local_output)

    def _upload_output(self) -> None:
        if self.local_output.exists():
            self.storage.upload_file(self.local_output, self.settings.storage.onedrive.output_path)

    def _upload_log(self) -> None:
        for handler in self.logger.handlers:
            filename = getattr(handler, "baseFilename", None)
            if filename:
                local_path = Path(filename)
                if local_path.exists():
                    remote_path = f"{self.settings.storage.onedrive.logs_root.rstrip('/')}/{local_path.name}"
                    self.storage.upload_file(local_path, remote_path)
                break

    def _prepare_debug_workspace(self) -> None:
        if not self.local_debug.exists():
            return
        for path in self.local_debug.glob("*.html"):
            path.unlink()

    def _upload_debug_artifacts(self, run_id: str) -> None:
        if not self.local_debug.exists():
            return
        remote_root = f"{self.settings.storage.onedrive.debug_root.rstrip('/')}/{run_id}"
        for path in self.local_debug.glob("*.html"):
            self.storage.upload_file(path, f"{remote_root}/{path.name}")

    def _append_summary(self, state: RunState, **increments: int) -> None:
        for key, value in increments.items():
            state.summary[key] = state.summary.get(key, 0) + value

    def _eligible_cached_record(self, payload: dict | None) -> PaymentRecord | None:
        if not payload or "cached_at" not in payload:
            return None
        cached_at = datetime.fromisoformat(payload["cached_at"])
        age = datetime.now(UTC) - cached_at
        if age > timedelta(hours=self.settings.scraper.cache_ttl_hours):
            return None
        return _deserialize_record(payload)

    def _collect_targets(self, state: RunState, companies: list[CompanyRecord]) -> list[SearchResultItem]:
        seen_app_ids = set(state.completed_tender_ids)
        seen_reg_ids = {
            record.get("tender_registration_number")
            for record in state.records
            if record.get("tender_registration_number")
        }
        targets: list[SearchResultItem] = []

        for company in companies:
            if company.company_id in state.processed_company_ids:
                continue
            self._append_summary(state, companies_scanned=1)
            try:
                company_results: list[SearchResultItem] = []
                for status_id in self.settings.scraper.contract_status_ids:
                    company_results.extend(self.client.search_company(company, status_id))
            except TenderClientError as exc:
                state.failures[company.company_id] = str(exc)
                self._append_summary(state, companies_skipped=1)
                state.processed_company_ids.append(company.company_id)
                self.state_store.save(state)
                continue

            for item in company_results:
                reg_id = item.tender_registration_number
                if item.app_id in seen_app_ids or (reg_id and reg_id in seen_reg_ids):
                    continue
                seen_app_ids.add(item.app_id)
                if reg_id:
                    seen_reg_ids.add(reg_id)
                targets.append(item)
                state.queued_tenders.append(_serialize_search_item(item))
                self._append_summary(state, tenders_discovered=1)

            state.processed_company_ids.append(company.company_id)
            self.state_store.save(state)
        return targets

    def _fetch_targets(self, state: RunState, targets: list[SearchResultItem]) -> list[PaymentRecord]:
        records = [_deserialize_record(payload) for payload in state.records]
        if not targets:
            return records

        pending_checkpoint = 0

        def on_success(record: PaymentRecord) -> None:
            nonlocal pending_checkpoint
            records.append(record)
            state.records.append(_serialize_record(record))
            state.completed_tender_ids.append(record.app_id)
            self._append_summary(state, tenders_fetched=1)
            self.state_store.store_cache(record)
            pending_checkpoint += 1
            if pending_checkpoint >= 10:
                self.state_store.save(state)
                pending_checkpoint = 0

        def on_failure(item: SearchResultItem, exc: Exception) -> None:
            self.logger.exception("Failed to fetch tender %s", item.app_id)
            state.failures[item.app_id] = str(exc)
            self._append_summary(state, parse_failures=1)
            self.state_store.save(state)

        uncached: list[SearchResultItem] = []
        for item in targets:
            cached = self._eligible_cached_record(self.state_store.read_cache(item.app_id))
            if cached:
                on_success(cached)
            else:
                uncached.append(item)

        self.client.fetch_tender_details_concurrent(uncached, on_success=on_success, on_failure=on_failure)
        self.state_store.save(state)
        return records

    def _write_workbook(self, state: RunState, records: list[PaymentRecord], unique_company_names: list[str]) -> str:
        self._download_output_if_present()
        run_time = datetime.now(ZoneInfo(self.settings.excel.timezone))
        sheet_name = write_output_workbook(self.local_output, records, unique_company_names, run_time)
        self._append_summary(state, rows_written=len(records), retries=self.client.retry_count)
        self._upload_output()
        return sheet_name

    def run(self) -> dict:
        self._prepare_debug_workspace()
        companies, unique_company_names = self._download_input()
        state = self.state_store.create("run", {"mode": "run"}, companies)
        self.client.initialize()
        targets = self._collect_targets(state, companies)
        state.stage = "detail"
        self.state_store.save(state)
        records = self._fetch_targets(state, targets)
        sheet_name = self._write_workbook(state, records, unique_company_names)
        state.stage = "completed"
        self.state_store.save(state)
        self._upload_debug_artifacts(state.run_id)
        self._upload_log()
        return {"run_id": state.run_id, "sheet_name": sheet_name, "summary": state.summary}

    def run_company(self, company_id: str, company_name: str | None = None) -> dict:
        self._prepare_debug_workspace()
        display_name = company_name or company_id
        companies = [CompanyRecord(company_id=company_id, company_name=display_name, overdue_days_raw="manual")]
        state = self.state_store.create("company", {"company_id": company_id, "company_name": display_name}, companies)
        self.client.initialize()
        targets = self._collect_targets(state, companies)
        state.stage = "detail"
        self.state_store.save(state)
        records = self._fetch_targets(state, targets)
        sheet_name = self._write_workbook(state, records, [display_name])
        state.stage = "completed"
        self.state_store.save(state)
        self._upload_debug_artifacts(state.run_id)
        self._upload_log()
        return {"run_id": state.run_id, "sheet_name": sheet_name, "summary": state.summary}

    def run_tender(self, app_id: str) -> dict:
        self.client.initialize()
        item = SearchResultItem(
            app_id=app_id,
            company_id="",
            company_name="",
            tender_registration_number=None,
            announcement_date=None,
            row_text="",
            page_number=1,
            total_pages=1,
        )
        record = self.client.fetch_tender_details(item)
        self._upload_log()
        return {"record": _serialize_record(record)}

    def run_regid(self, reg_id: str) -> dict:
        self.client.initialize()
        matches = self.client.search_regid(reg_id)
        if not matches:
            self._upload_log()
            return {"record": None}
        record = self.client.fetch_tender_details(matches[0])
        self._upload_log()
        return {"record": _serialize_record(record)}

    def resume(self, run_id: str) -> dict:
        self._prepare_debug_workspace()
        state = self.state_store.load(run_id)
        self.client.initialize()
        targets = [_deserialize_search_item(payload) for payload in state.queued_tenders if payload["app_id"] not in state.completed_tender_ids]
        records = self._fetch_targets(state, targets)
        unique_names = sorted({payload["company_name"] for payload in state.records if payload.get("company_name")}, key=str.casefold)
        sheet_name = self._write_workbook(state, records, unique_names)
        state.stage = "completed"
        self.state_store.save(state)
        self._upload_debug_artifacts(state.run_id)
        self._upload_log()
        return {"run_id": state.run_id, "sheet_name": sheet_name, "summary": state.summary}

    def smoke_test(self, company_id: str | None = None, app_id: str | None = None) -> dict:
        self._prepare_debug_workspace()
        self.client.initialize()
        if app_id:
            return self.run_tender(app_id)
        if not company_id:
            raise ValueError("Smoke test requires either company_id or app_id")
        company = CompanyRecord(company_id=company_id, company_name=company_id, overdue_days_raw="manual")
        results: list[SearchResultItem] = []
        for status_id in self.settings.scraper.contract_status_ids:
            results.extend(self.client.search_company(company, status_id))
        preview = [_serialize_search_item(result) for result in results[:5]]
        self._upload_log()
        return {"company_id": company_id, "count": len(results), "matches": preview}


def create_app(
    settings: AppSettings,
    storage: BaseStorage,
    state_store: RunStateStore,
    client: TenderPortalClient,
    logger,
) -> TenderTrackerApp:
    work_root = Path("work")
    work_root.mkdir(parents=True, exist_ok=True)
    return TenderTrackerApp(settings=settings, storage=storage, state_store=state_store, client=client, logger=logger, work_root=work_root)


def write_github_summary(result: dict) -> None:
    summary_target = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_target:
        return
    path = Path(summary_target)
    path.write_text("## Tender Tracker Run\n\n```json\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
