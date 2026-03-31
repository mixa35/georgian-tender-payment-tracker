# Original Flow Logic to Replicate

## Step 1: Read Input Excel
File: AAA Trade Factor Report.xlsx
- Read all rows (columns 1-24, first row is header)
- Filter rows where:
  - "ვადაგადაცილებული დღეების რაოდენობა" does NOT start with "-"
  - AND "ვადაგადაცილებული დღეების რაოდენობა" > 0
- Sort by "კომპანია" ascending
- Extract unique company IDs from "კომპანიის_საიდენტიფიკაციო_კოდი" (deduplicated)
- Extract unique company names from "კომპანია" (deduplicated, case-insensitive)

## Step 2: For Each Company ID

### 2a. Search for tenders
POST to controller.php with:
- org_b = company ID
- app_particip_status_id = 200 (contract awarded)
- app_agr_status = 10 (active contract)
- all other params as specified in api_reference.md

Parse response to get:
- Total page count from pagination text: extract number after "/" in "(გვერდი: N/TOTAL)"
- List of tender numeric IDs (strip "A" prefix from tr id attributes)

### 2b. Skip conditions
- If total pages = 0 → skip this company (no tenders found)
- If total pages >= 100 → skip this company (too many, likely a large conglomerate/noise)

### 2c. Deduplication across companies
Original flow tracked already-processed tender NAT numbers in a list (NAT_LIST)
to avoid processing the same tender twice across different company searches.
The tender number (e.g. "NAT260006620") is extracted from the row text via regex.

### 2d. Paginate and collect all tender IDs
For each page (up to total pages):
- Extract tender IDs from that page
- Filter: keep only tenders from year 2022 onward
  (year extracted from tender number prefix: e.g. "NAT260006620" → year is encoded in number,
   OR from the announcement date field in the row text: "შესყიდვის გამოცხადების თარიღი: DD.MM.YYYY")
- The original flow used regex (?<=^...)\d+ to extract the numeric part after first 3 chars of tender number
  and filtered where that number > 2021 (comparing the full number not just year — this was filtering
  by the raw numeric ID being greater than 2021, which excludes very old low-numbered tenders)

## Step 3: For Each Tender ID

### 3a. Fetch contract/payment data
GET controller.php?action=agr_docs&app_id=<NUMERIC_ID>

### 3b. Parse payment table
Target: #agency_docs > div:last-of-type > table
Get the LAST row of the table body.

### 3c. Extract fields
- Amount (raw): last row, col 0 text — extract up to and including "ლარი"
  e.g. "7`500.00 ლარი"
- Payment date (raw): last row, col 3 — format DD.MM.YYYY
  e.g. "12.03.2026"
- If last row contains "ჩანაწერები არ არის" → amount = "ჩანაწერები არ არის", date = ""

### 3d. Write to output Excel
- Column A (1): raw amount string
- Column B (2): raw date string
- Column C (3): company name
- Column D (4): Excel formula =IF(A{row}="ჩანაწერები არ არის","ჩანაწერები არ არის",VALUE(SUBSTITUTE(A{row},"`","")))
- Column E (5): Excel formula =IF(B{row}="","",DATE(MID(B{row},7,4),MID(B{row},4,2),LEFT(B{row},2)))

## Step 4: Output Setup
- Open/create output Excel file
- Add new sheet named with today's date: format "d MMM" in Georgian locale (e.g. "31 მარტი" or "1 Apr")
- Write header row 1: A="თანხა", B="თარიღი", C="კომპანია", G="ყველა კომპანია"
- Write unique company names list starting at G2
- Data rows start at row 2, increment row counter per tender written

## Step 5: Post-processing
- Original flow ran a macro "TransformData_NoNamedTables" on the output file
- This macro's logic is unknown but it likely formats/transforms the data
- The flow had disabled code to copy columns D:E back over A:B and delete D:E

## Key Numbers
- 4 results per page from search
- Max pages to process: 100 (skip companies with >= 100 pages of results)
- Year filter threshold: tender numeric ID > 2021 (original flow logic)
- Row counter starts at 2 (row 1 = headers)
