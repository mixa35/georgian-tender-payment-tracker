from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import random
import re
import threading
import time
from pathlib import Path
from typing import Callable

import requests

from tender_tracker.config import AppSettings
from tender_tracker.models import CompanyRecord, PaymentRecord, SearchPage, SearchResultItem
from tender_tracker.parsers import ParseError, parse_payment_record, parse_search_page

PAGE_PARAM_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("page", "2"),
    ("p", "2"),
    ("pg", "2"),
    ("page_num", "2"),
    ("app_page", "2"),
    ("cur_page", "2"),
    ("btn_next", "1"),
)


class TenderClientError(RuntimeError):
    """Raised when the tender portal cannot be queried reliably."""


class TenderPortalClient:
    def __init__(
        self,
        settings: AppSettings,
        *,
        logger,
        debug_dir: Path | None = None,
    ) -> None:
        self.settings = settings
        self.logger = logger
        self.debug_dir = debug_dir
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": settings.scraper.browser_user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ka-GE,ka;q=0.9,en;q=0.8",
                "Referer": "https://tenders.procurement.gov.ge/public/?lang=ge",
                "Origin": "https://tenders.procurement.gov.ge",
            }
        )
        self._last_request_at = 0.0
        self._request_lock = threading.Lock()
        self._page_param_name = settings.scraper.page_param_name.strip()
        self.retry_count = 0

    def initialize(self) -> None:
        self._request("GET", "https://tenders.procurement.gov.ge/public/?lang=ge")

    def _throttle(self) -> None:
        with self._request_lock:
            elapsed = time.monotonic() - self._last_request_at
            delay = self.settings.scraper.min_request_interval_seconds - elapsed
            if delay > 0:
                time.sleep(delay)
            self._last_request_at = time.monotonic()

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(self.settings.scraper.retry_count + 1):
            try:
                self._throttle()
                response = self.session.request(
                    method,
                    url,
                    timeout=self.settings.scraper.request_timeout_seconds,
                    **kwargs,
                )
                response.encoding = "utf-8"
                if response.status_code >= 500:
                    raise TenderClientError(f"Server error {response.status_code}: {response.text[:300]}")
                response.raise_for_status()
                return response
            except Exception as exc:
                last_error = exc
                self.retry_count += 1
                if attempt >= self.settings.scraper.retry_count:
                    break
                backoff = self.settings.scraper.retry_backoff_seconds * (2**attempt) + random.uniform(0.0, 0.3)
                time.sleep(backoff)
        raise TenderClientError(str(last_error)) from last_error

    def _capture_debug_html(self, name: str, html: str) -> None:
        if not self.debug_dir:
            return
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        (self.debug_dir / name).write_text(html, encoding="utf-8")

    def _post_search(self, payload: dict[str, str]) -> str:
        response = self._request("POST", self.settings.scraper.base_url, data=payload)
        if self.settings.scraper.debug_html_capture:
            self._capture_debug_html(f"search_{int(time.time() * 1000)}.html", response.text)
        return response.text

    def _search_page(self, payload: dict[str, str], company_id: str, company_name: str) -> SearchPage:
        return parse_search_page(self._post_search(payload), company_id, company_name)

    def _base_search_payload(self) -> dict[str, str]:
        return {
            "action": "search_app",
            "app_t": "0",
            "search": "",
            "app_reg_id": "",
            "app_shems_id": "0",
            "org_a": "",
            "app_monac_id": "0",
            "org_b": "",
            "app_particip_status_id": str(self.settings.scraper.app_particip_status_id),
            "app_donor_id": "0",
            "app_status": str(self.settings.scraper.app_status_id),
            "app_agr_status": "10",
            "app_type": "0",
            "app_basecode": "0",
            "app_date_type": "1",
            "app_date_from": "",
            "app_date_tlll": "",
            "app_amount_from": "",
            "app_amount_to": "",
            "app_currency": "2",
            "app_pricelist": "0",
        }

    def _lookup_supplier(self, company_id: str) -> tuple[str, str] | None:
        response = self._request(
            "GET",
            "https://tenders.procurement.gov.ge/public/library/list_org.php",
            params={"q": company_id, "limit": "20", "timestamp": "0", "orgtype": "1"},
        )
        response.encoding = "utf-8"
        best_match: tuple[str, str] | None = None
        for line in response.text.splitlines():
            parts = [part.strip() for part in line.split("|")]
            if len(parts) < 3:
                continue
            supplier_id, supplier_name, supplier_code = parts[:3]
            if supplier_code == company_id:
                return supplier_id, supplier_name
            if best_match is None:
                best_match = (supplier_id, supplier_name)
        return best_match

    def _infer_page_param_from_html(self, html: str) -> str | None:
        patterns = [
            r"([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*2",
            r"([A-Za-z_][A-Za-z0-9_]*)=2",
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                candidate = match.group(1)
                if candidate.lower() not in {"action", "app_t", "app_status"}:
                    return candidate
        return None

    def _resolve_page_param(self, payload: dict[str, str], first_page: SearchPage, company_id: str, company_name: str) -> str:
        guessed = self._infer_page_param_from_html(first_page.raw_html)
        if guessed:
            return guessed

        first_ids = [item.app_id for item in first_page.items]
        for candidate, value in PAGE_PARAM_CANDIDATES:
            probe_payload = dict(payload)
            probe_payload[candidate] = value
            page = self._search_page(probe_payload, company_id, company_name)
            probe_ids = [item.app_id for item in page.items]
            if page.page_number == 2 or (probe_ids and probe_ids != first_ids):
                self.logger.info("Resolved pagination parameter as %s", candidate)
                return candidate
        raise TenderClientError("Could not resolve search pagination parameter")

    def _search_all_pages(self, payload: dict[str, str], company_id: str, company_name: str) -> list[SearchResultItem]:
        first_page = self._search_page(payload, company_id, company_name)
        if first_page.no_records or first_page.total_pages == 0:
            return []
        if first_page.total_pages >= self.settings.scraper.max_pages_per_company:
            raise TenderClientError(
                f"Skipping company {company_id or company_name} because result pages reached {first_page.total_pages}"
            )

        results = list(first_page.items)
        if first_page.total_pages <= 1:
            return results

        if not self._page_param_name:
            self._page_param_name = self._resolve_page_param(payload, first_page, company_id, company_name)

        for page_number in range(2, first_page.total_pages + 1):
            page_payload = dict(payload)
            page_payload[self._page_param_name] = str(page_number)
            page = self._search_page(page_payload, company_id, company_name)
            results.extend(page.items)
        return results

    def search_company(self, company: CompanyRecord, contract_status_id: int) -> list[SearchResultItem]:
        payload = self._base_search_payload()
        supplier_match = self._lookup_supplier(company.company_id)
        if supplier_match is not None:
            supplier_id, supplier_name = supplier_match
            payload["org_b"] = supplier_name
            payload["app_monac_id"] = supplier_id
        else:
            self.logger.warning("Supplier lookup did not resolve company %s; falling back to raw company ID", company.company_id)
            payload["org_b"] = company.company_id
        payload["app_agr_status"] = str(contract_status_id)
        return self._search_all_pages(payload, company.company_id, company.company_name)

    def search_regid(self, reg_id: str) -> list[SearchResultItem]:
        payload = self._base_search_payload()
        payload["app_reg_id"] = reg_id
        payload["org_b"] = ""
        return self._search_all_pages(payload, "", reg_id)

    def fetch_tender_details(self, search_item: SearchResultItem) -> PaymentRecord:
        response = self._request(
            "GET",
            self.settings.scraper.base_url,
            params={"action": "agr_docs", "app_id": search_item.app_id},
        )
        if self.settings.scraper.debug_html_capture:
            self._capture_debug_html(f"agr_docs_{search_item.app_id}.html", response.text)
        try:
            return parse_payment_record(response.text, search_item)
        except ParseError:
            self._capture_debug_html(f"agr_docs_parse_error_{search_item.app_id}.html", response.text)
            raise

    def fetch_tender_details_concurrent(
        self,
        targets: list[SearchResultItem],
        *,
        on_success: Callable[[PaymentRecord], None],
        on_failure: Callable[[SearchResultItem, Exception], None],
    ) -> None:
        with ThreadPoolExecutor(max_workers=self.settings.scraper.detail_fetch_concurrency) as executor:
            future_to_item = {executor.submit(self.fetch_tender_details, item): item for item in targets}
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    record = future.result()
                except Exception as exc:
                    on_failure(item, exc)
                else:
                    on_success(record)
