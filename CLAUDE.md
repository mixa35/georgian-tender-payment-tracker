# Georgian Government Tender Payment Tracker

## Project Purpose
This tool replaces a Power Automate Desktop UI-automation flow.
It reads debtor company IDs from an Excel file, queries the Georgian
Government Tenders portal via direct HTTP calls (no browser needed),
extracts the latest government payment received by each company on
their active/completed tenders, and writes results to an output Excel file.

## Key Facts
- Target site: https://tenders.procurement.gov.ge/public/?lang=ge
- The site URL never changes. All data is loaded via AJAX into a single page.
- Single backend endpoint: https://tenders.procurement.gov.ge/public/library/controller.php
- All responses are HTML fragments (NOT JSON).
- No authentication required. No session/cookie needed beyond what the browser sends.
- Site uses jQuery 1.8.3 (2012 era). Very old, very simple backend.

## Input
Excel file: AAA Trade Factor Report.xlsx
- Column: კომპანიის_საიდენტიფიკაციო_კოდი  → company 9-digit Georgian ID code
- Column: კომპანია                          → company name
- Column: ვადაგადაცილებული დღეების რაოდენობა → overdue days (filter: > 0 and not starting with "-")
- Read all rows, filter for overdue > 0, deduplicate by company ID

## Output
Excel file: ვალდებული კომპანიების ჩარიცხვები მიმდინარე ტენდერებზე.xlsm
- New sheet named with today's date (format: "d MMM", e.g. "1 Apr")
- Columns: A=amount(raw), B=payment_date(raw), C=company_name, D=amount(numeric cleaned), E=payment_date(as date)

## Reference Files
- docs/api_reference.md    → full API details, endpoints, parameters
- docs/html_structure.md   → exact HTML structure of responses to parse
- docs/flow_logic.md       → original Power Automate flow logic to replicate

## Language Note
The site and Excel files use Georgian (ქართული) text. Handle UTF-8 encoding carefully everywhere.
Georgian uses the backtick ` as a thousands separator in numbers (e.g. 7`500.00).

## Tech Decisions (to be made by Claude Code)
Language, libraries, structure — all open. Suggested: Python with requests + BeautifulSoup + openpyxl.
