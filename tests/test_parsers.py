from datetime import date

from tender_tracker.models import SearchResultItem
from tender_tracker.parsers import (
    NO_RECORDS_TEXT,
    extract_tender_registration_number,
    is_recent_tender,
    parse_payment_record,
    parse_pagination_text,
    parse_search_page,
)


SEARCH_HTML = """
<button><span>45873 ჩანაწერი (გვერდი: 1/11469)</span></button>
<table id="list_apps_by_subject" class="ktable">
  <tbody>
    <tr id="A678938">
      <td></td>
      <td>
        <p class="status">ხელშეკრულება დადებულია</p>
        <p>განცხადების ნომერი: <strong>B2B260000023</strong></p>
        <p>შესყიდვის გამოცხადების თარიღი: 20.03.2026</p>
      </td>
    </tr>
  </tbody>
</table>
"""

NO_RESULTS_HTML = """
<button><span>0 ჩანაწერი (გვერდი: 0/0)</span></button>
<table id="list_apps_by_subject"><tbody><tr><td>ჩანაწერები არ არის</td></tr></tbody></table>
"""

PAYMENT_HTML = """
<div id="agency_docs">
  <div class="ui-state-highlight">summary</div>
  <div class="pad4px"><table id="last_docs"></table></div>
  <div class="ui-state-highlight">
    <table>
      <tbody>
        <tr>
          <td>თანხა</td><td>წელი</td><td>კვარტალი</td><td>გადახდის თარიღი</td><td>თარიღი/ავტორი</td>
        </tr>
        <tr>
          <td>7`500.00 ლარისაკუთარი შემოსავლები</td>
          <td>2026</td>
          <td>1</td>
          <td>12.03.2026</td>
          <td>12.03.2026–Author</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
"""

MULTI_PAYMENT_HTML = """
<div id="agency_docs">
  <div></div><div></div>
  <div>
    <table>
      <tbody>
        <tr><td>თანხა</td><td>წელი</td><td>კვარტალი</td><td>გადახდის თარიღი</td><td>თარიღი/ავტორი</td></tr>
        <tr><td>1`000.00 ლარი</td><td>2025</td><td>4</td><td>01.12.2025</td><td>01.12.2025-A</td></tr>
        <tr><td>2`500.00 ლარი</td><td>2026</td><td>1</td><td></td><td>12.03.2026-Author</td></tr>
      </tbody>
    </table>
  </div>
</div>
"""

NO_PAYMENT_HTML = """
<div id="agency_docs">
  <div></div><div></div>
  <div>
    <table>
      <tbody>
        <tr><td>თანხა</td><td>წელი</td><td>კვარტალი</td><td>გადახდის თარიღი</td><td>თარიღი/ავტორი</td></tr>
        <tr><td colspan="5">ჩანაწერები არ არის</td></tr>
      </tbody>
    </table>
  </div>
</div>
"""

SINGLE_ROW_PAYMENT_HTML = """
<div id="agency_docs">
  <div></div><div></div>
  <div>
    <table>
      <tbody>
        <tr>
          <td>3`200.00 ლარი</td>
          <td>2026</td>
          <td>1</td>
          <td>15.04.2026</td>
          <td>15.04.2026-Author</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
"""

EMPTY_TBODY_HTML = """
<div id="agency_docs">
  <div></div><div></div>
  <div><table><tbody></tbody></table></div>
</div>
"""


def test_parse_pagination_text():
    current, total, count = parse_pagination_text("45873 ჩანაწერი (გვერდი: 1/11469)")
    assert (current, total, count) == (1, 11469, 45873)


def test_parse_search_page_extracts_results():
    page = parse_search_page(SEARCH_HTML, "123456789", "Test Co")
    assert page.total_pages == 11469
    assert page.items[0].app_id == "678938"
    assert page.items[0].tender_registration_number == "B2B260000023"
    assert page.items[0].announcement_date == date(2026, 3, 20)


def test_parse_search_page_handles_no_results():
    page = parse_search_page(NO_RESULTS_HTML, "123456789", "Test Co")
    assert page.no_records is True
    assert page.items == []


def test_parse_payment_record_extracts_latest_payment():
    item = SearchResultItem(
        app_id="678938",
        company_id="123456789",
        company_name="Test Co",
        tender_registration_number="B2B260000023",
        announcement_date=date(2026, 3, 20),
        row_text="",
        page_number=1,
        total_pages=1,
    )
    record = parse_payment_record(PAYMENT_HTML, item)
    assert record.raw_amount == "7`500.00 ლარი"
    assert record.cleaned_amount == 7500.0
    assert record.parsed_payment_date == date(2026, 3, 12)


def test_parse_payment_record_uses_fallback_date_from_author_column():
    item = SearchResultItem(
        app_id="678938",
        company_id="123456789",
        company_name="Test Co",
        tender_registration_number="B2B260000023",
        announcement_date=date(2026, 3, 20),
        row_text="",
        page_number=1,
        total_pages=1,
    )
    record = parse_payment_record(MULTI_PAYMENT_HTML, item)
    assert record.raw_amount == "2`500.00 ლარი"
    assert record.parsed_payment_date == date(2026, 3, 12)
    assert record.warnings


def test_parse_payment_record_handles_no_payment_rows():
    item = SearchResultItem(
        app_id="678938",
        company_id="123456789",
        company_name="Test Co",
        tender_registration_number="B2B260000023",
        announcement_date=date(2026, 3, 20),
        row_text="",
        page_number=1,
        total_pages=1,
    )
    record = parse_payment_record(NO_PAYMENT_HTML, item)
    assert record.raw_amount == NO_RECORDS_TEXT
    assert record.payment_exists is False


def test_parse_payment_record_single_row_no_header():
    item = SearchResultItem(
        app_id="678938",
        company_id="123456789",
        company_name="Test Co",
        tender_registration_number="B2B260000023",
        announcement_date=date(2026, 3, 20),
        row_text="",
        page_number=1,
        total_pages=1,
    )
    record = parse_payment_record(SINGLE_ROW_PAYMENT_HTML, item)
    assert record.payment_exists is True
    assert record.cleaned_amount == 3200.0
    assert record.parsed_payment_date == date(2026, 4, 15)


def test_parse_payment_record_empty_tbody_returns_no_records():
    item = SearchResultItem(
        app_id="678938",
        company_id="123456789",
        company_name="Test Co",
        tender_registration_number=None,
        announcement_date=None,
        row_text="",
        page_number=1,
        total_pages=1,
    )
    record = parse_payment_record(EMPTY_TBODY_HTML, item)
    assert record.payment_exists is False
    assert record.raw_amount == NO_RECORDS_TEXT


def test_recent_tender_uses_registration_number_threshold():
    item = SearchResultItem(
        app_id="1",
        company_id="123456789",
        company_name="Test Co",
        tender_registration_number="NAT260006620",
        announcement_date=date(2021, 1, 1),
        row_text="",
        page_number=1,
        total_pages=1,
    )
    assert is_recent_tender(item, threshold_year=2022) is True


def test_extract_tender_registration_number():
    assert extract_tender_registration_number("foo NAT260006620 bar") == "NAT260006620"
