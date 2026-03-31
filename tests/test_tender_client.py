from pathlib import Path

import pytest

import tender_tracker.tender_client as tender_client_module
from tender_tracker.config import load_settings
from tender_tracker.logging_utils import build_logger
from tender_tracker.models import CompanyRecord, SearchResultItem
from tender_tracker.parsers import ParseError
from tender_tracker.tender_client import TenderClientError, TenderPortalClient


class DummyResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.encoding = "utf-8"
        self.status_code = status_code


def test_lookup_supplier_prefers_exact_company_code(tmp_path: Path):
    settings = load_settings("config/settings.yaml")
    logger = build_logger(tmp_path / "test.log", "INFO")
    client = TenderPortalClient(settings, logger=logger)

    def fake_request(method: str, url: str, **kwargs):
        assert method == "GET"
        assert "list_org.php" in url
        return DummyResponse("65178|Company A|405114406|\n70000|Other Company|999999999|\n")

    client._request = fake_request  # type: ignore[method-assign]
    assert client._lookup_supplier("405114406") == ("65178", "Company A")


def test_search_company_uses_supplier_lookup_result(tmp_path: Path):
    settings = load_settings("config/settings.yaml")
    logger = build_logger(tmp_path / "test.log", "INFO")
    client = TenderPortalClient(settings, logger=logger)
    company = CompanyRecord(company_id="405114406", company_name="Name", overdue_days_raw="1")
    captured = {}

    def fake_lookup(company_id: str):
        assert company_id == "405114406"
        return ("65178", "Company A")

    def fake_search_all_pages(payload, company_id, company_name):
        captured["payload"] = payload
        captured["company_id"] = company_id
        captured["company_name"] = company_name
        return []

    client._lookup_supplier = fake_lookup  # type: ignore[method-assign]
    client._search_all_pages = fake_search_all_pages  # type: ignore[method-assign]
    client.search_company(company, 10)

    assert captured["payload"]["org_b"] == "Company A"
    assert captured["payload"]["app_monac_id"] == "65178"
    assert captured["payload"]["app_particip_status_id"] == "200"
    assert captured["payload"]["app_status"] == "0"
    assert captured["payload"]["app_agr_status"] == "10"


def test_request_does_not_retry_non_retriable_http_4xx(tmp_path: Path):
    settings = load_settings("config/settings.yaml")
    settings.scraper.retry_count = 3
    settings.scraper.retry_backoff_seconds = 0
    logger = build_logger(tmp_path / "test.log", "INFO")
    client = TenderPortalClient(settings, logger=logger)
    calls = {"count": 0}

    def fake_request(method: str, url: str, timeout: int, **kwargs):
        calls["count"] += 1
        return DummyResponse("missing", status_code=404)

    client.session.request = fake_request  # type: ignore[method-assign]

    with pytest.raises(TenderClientError, match="HTTP 404"):
        client._request("GET", "https://example.com")

    assert calls["count"] == 1
    assert client.retry_count == 0


def test_request_retries_retriable_http_5xx(tmp_path: Path):
    settings = load_settings("config/settings.yaml")
    settings.scraper.retry_count = 2
    settings.scraper.retry_backoff_seconds = 0
    logger = build_logger(tmp_path / "test.log", "INFO")
    client = TenderPortalClient(settings, logger=logger)
    calls = {"count": 0}

    def fake_request(method: str, url: str, timeout: int, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return DummyResponse("server error", status_code=500)
        return DummyResponse("ok", status_code=200)

    client.session.request = fake_request  # type: ignore[method-assign]

    response = client._request("GET", "https://example.com")

    assert response.status_code == 200
    assert calls["count"] == 2
    assert client.retry_count == 1


def test_fetch_tender_details_captures_parse_error_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    settings = load_settings("config/settings.yaml")
    settings.scraper.debug_html_capture = False
    logger = build_logger(tmp_path / "test.log", "INFO")
    debug_dir = tmp_path / "debug"
    client = TenderPortalClient(settings, logger=logger, debug_dir=debug_dir)
    item = SearchResultItem(
        app_id="572720",
        company_id="448056228",
        company_name="Test Co",
        tender_registration_number="NAT240008087",
        announcement_date=None,
        row_text="",
        page_number=1,
        total_pages=1,
    )

    def fake_request(method: str, url: str, **kwargs):
        return DummyResponse("<html><body>broken</body></html>", status_code=200)

    def fake_parse_payment_record(html: str, search_item: SearchResultItem | None = None):
        raise ParseError("Payment table did not contain a data row")

    client._request = fake_request  # type: ignore[method-assign]
    monkeypatch.setattr(tender_client_module, "parse_payment_record", fake_parse_payment_record)

    with pytest.raises(ParseError, match="Payment table did not contain a data row"):
        client.fetch_tender_details(item)

    captured = debug_dir / "agr_docs_parse_error_572720.html"
    assert captured.exists()
    assert "broken" in captured.read_text(encoding="utf-8")
