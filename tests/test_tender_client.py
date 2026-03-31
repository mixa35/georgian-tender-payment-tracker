from pathlib import Path

from tender_tracker.config import load_settings
from tender_tracker.logging_utils import build_logger
from tender_tracker.models import CompanyRecord
from tender_tracker.tender_client import TenderPortalClient


class DummyResponse:
    def __init__(self, text: str):
        self.text = text
        self.encoding = "utf-8"


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
    assert captured["payload"]["app_agr_status"] == "10"
