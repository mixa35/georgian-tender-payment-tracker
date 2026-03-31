# Georgian Tender Payment Tracker

Cloud-first scraper for the Georgian government tenders portal. The project is designed to run in GitHub Actions, use Microsoft Graph to read/write Excel files in OneDrive for Business, and replace a fragile Power Automate Desktop browser flow with direct HTTP requests.

## What It Does

- Downloads `AAA Trade Factor Report.xlsx` from OneDrive
- Reads debtor companies with positive overdue days
- Searches the tenders portal via `library/controller.php`
- Fetches the latest payment row for each relevant tender
- Updates the canonical `.xlsm` output workbook in OneDrive with a new dated sheet
- Persists run state, logs, and optional debug HTML back to OneDrive

## Commands

Run the full batch:

```bash
python -m tender_tracker run
```

Run one company:

```bash
python -m tender_tracker company --company-id 123456789 --company-name "Example LLC"
```

Fetch one tender directly:

```bash
python -m tender_tracker tender --app-id 678938
```

Fetch by tender registration number:

```bash
python -m tender_tracker regid --reg-id B2B260000023
```

Resume a run:

```bash
python -m tender_tracker resume --run-id 20260331T120000Z
```

Live smoke test without workbook writes:

```bash
python -m tender_tracker smoke-test --company-id 123456789
```

## Configuration

Default settings live in [config/settings.yaml](/c:/Users/MISHO/Desktop/web%20scraper%20codex/config/settings.yaml).

Important OneDrive settings:

- `storage.onedrive.user_principal_name`
- `storage.onedrive.input_path`
- `storage.onedrive.output_path`
- `storage.onedrive.state_root`
- `storage.onedrive.logs_root`
- `storage.onedrive.debug_root`

## Required GitHub Secrets

- `MS_TENANT_ID`
- `MS_CLIENT_ID`
- `MS_CLIENT_SECRET`

The Azure / Entra app registration needs Microsoft Graph application permissions that allow reading and writing the target user's OneDrive for Business files.

## GitHub Actions

The scheduled/manual workflow lives at [.github/workflows/tender_tracker.yml](/c:/Users/MISHO/Desktop/web%20scraper%20codex/.github/workflows/tender_tracker.yml).

It:

- sets up Python 3.12
- installs the package
- runs tests
- executes the selected command
- uploads debug artifacts on failure

## Local Wrapper

For local development or emergency fallback, use [scripts/run_tender_tracker.ps1](/c:/Users/MISHO/Desktop/web%20scraper%20codex/scripts/run_tender_tracker.ps1).
