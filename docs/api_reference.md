# API Reference — tenders.procurement.gov.ge

## Base URL
https://tenders.procurement.gov.ge/public/library/controller.php

## Endpoint 1: Search Tenders by Company ID

**Method:** POST  
**URL:** https://tenders.procurement.gov.ge/public/library/controller.php  
**Content-Type:** application/x-www-form-urlencoded

### Request Body Parameters

| Parameter              | Value                        | Notes |
|------------------------|------------------------------|-------|
| action                 | search_app                   | fixed |
| app_t                  | 0                            | fixed |
| search                 | (empty)                      | fixed |
| app_reg_id             | (empty)                      | leave empty when searching by company |
| app_shems_id           | 0                            | fixed |
| org_a                  | (empty)                      | procuring entity ID — leave empty |
| app_monac_id           | 0                            | fixed |
| org_b                  | <COMPANY_ID>                 | 9-digit Georgian company identification code |
| app_particip_status_id | 200                          | 200 = "ხელშეკრულება დადებული" (contract awarded) |
| app_donor_id           | 0                            | fixed |
| app_status             | 0                            | 0 = all statuses |
| app_agr_status         | 10                           | 10 = active, 20 = completed, 0 = all |
| app_type               | 0                            | fixed |
| app_basecode           | 0                            | fixed |
| app_date_type          | 1                            | fixed |
| app_date_from          | (empty)                      | fixed |
| app_date_tlll          | (empty)                      | NOTE: typo in field name — "tlll" not "till" |
| app_amount_from        | (empty)                      | fixed |
| app_amount_to          | (empty)                      | fixed |
| app_currency           | 2                            | fixed |
| app_pricelist          | 0                            | fixed |

### app_particip_status_id values
- 0   = all
- 200 = ხელშეკრულება დადებული (contract awarded)
- 100 = დისკვალიფიცირებული (disqualified)

### app_agr_status values
- 0  = all
- 10 = მიმდინარე ხელშეკრულება (active contract)
- 20 = შესრულებული ხელშეკრულება (completed contract)
- 30 = შეუსრულებელი ხელშეკრულება (failed contract)
- 40 = მიმდინარე ხელშეკრულება - საგარანტიო პერიოდი (warranty period)

### Response
HTML fragment containing:
- `<table id="list_apps_by_subject">` with `<tbody>` containing result rows
- Each result row: `<tr id="A<NUMERIC_ID>">` — the numeric part of the id attribute IS the app_id for the next call
- Example: `<tr id="A678938">` → app_id = 678938
- 4 rows returned per page
- Pagination info embedded in a button's text: "45873 ჩანაწერი (გვერდი: 1/11469)" = total_records (page: current/total)
- Pagination buttons: id="btn_first", id="btn_prev", id="btn_next", id="btn_last"
- When no results: single row with text "ჩანაწერები არ არის"

### Extracting tender IDs from response
Parse the HTML, select all `tr[id]` inside `#list_apps_by_subject tbody`.
Strip the leading "A" from the id attribute to get the numeric app_id.

### Pagination
To get the next page, resubmit the same POST — the page parameter name was not confirmed.
Observe the total page count from the pagination button text using regex: digits after "/" in "(გვერდი: N/TOTAL)".

---

## Endpoint 2: Get Contract & Payment Data for a Tender

**Method:** GET  
**URL:** https://tenders.procurement.gov.ge/public/library/controller.php?action=agr_docs&app_id=<NUMERIC_ID>

### Response Structure
HTML fragment. The key element is `<div id="agency_docs">` which contains exactly 3 child divs:

**Child div 0** (class: ui-state-highlight) — Contract summary:
- Winner company name
- Contract number + signing date + value (format varies, e.g. "N56 30.03.2026 / 19540.8 ლარი")
- Contract validity period

**Child div 1** (class: pad4px) — Documents list:
- `<table id="last_docs">` listing uploaded PDF documents

**Child div 2** (class: ui-state-highlight) — PAYMENT TABLE (this is "div:last-of-type"):
- Contains the payments table

### Payment Table Structure
CSS selector: `#agency_docs > div:last-of-type > table`

Row 0 (header, uses `<td>` not `<th>`):
| Col 0  | Col 1 | Col 2    | Col 3            | Col 4           |
|--------|-------|----------|------------------|-----------------|
| თანხა  | წელი  | კვარტალი | გადახდის თარიღი  | თარიღი/ავტორი   |
| Amount | Year  | Quarter  | Payment Date     | Date/Author     |

Row 1+ (data rows, one per payment received):
| Col 0                          | Col 1 | Col 2 | Col 3      | Col 4              |
|--------------------------------|-------|-------|------------|--------------------|
| "7`500.00 ლარი" + funding src  | 2026  | 1     | 12.03.2026 | 12.03.2026–author  |

**When no payments exist:**
Table has 2 rows: header row + single row with one cell containing "ჩანაწერები არ არის"

**When payments exist:**
Table has header row + N data rows (one per payment).
The LAST data row = most recent payment.
Target: `tbody > tr:nth-last-child(1)` or just the last `<tr>` in the table.

### Parsing the amount (Col 0)
- Full textContent includes Georgian funding source label appended without separator
- The text NODE value (direct text node, not children) = clean amount string: "7`500.00 ლარი"
- Alternatively: extract via regex up to "ლარი"
- To convert to number: remove backtick ` (thousands separator), remove " ლარი", parse as float

### Parsing the payment date (Col 3)
- Format: DD.MM.YYYY (e.g. "12.03.2026")
- Col 4 also contains the date at the start if col 3 parsing fails
