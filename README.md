# Georgian Tender Payment Tracker

[![Tender Tracker](https://github.com/mixa35/georgian-tender-payment-tracker/actions/workflows/tender_tracker.yml/badge.svg)](https://github.com/mixa35/georgian-tender-payment-tracker/actions/workflows/tender_tracker.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Replaces a fragile Power Automate Desktop browser flow with a scheduled cloud job that runs
unattended every morning.** Every night at 00:37 UTC (04:37 Tbilisi) GitHub Actions pulls a
receivables workbook out of OneDrive, looks up every overdue debtor company on the Georgian
government tenders portal, finds the most recent state payment each one received, and writes a
new dated sheet back into the canonical workbook — before anyone gets to the office.

No browser, no desktop agent, no VM to keep awake. Direct HTTP against the portal, Microsoft
Graph for the file I/O, and the whole thing gated by its own test suite on every run.

| | |
|---|---|
| **Runs on** | GitHub Actions (`schedule` + `workflow_dispatch`) — no server to maintain |
| **In production since** | March 2026, daily |
| **Replaced** | A Power Automate Desktop UI-automation flow that broke whenever the page moved |
| **Storage** | Microsoft Graph → OneDrive for Business (`.xlsx` in, `.xlsm` out) |
| **Tests** | 6 test modules, run by CI *before* the production job is allowed to execute |

## How it works

```
  00:37 UTC (cron)                 GitHub Actions runner
        │                     ┌──────────────────────────────┐
        └────────────────────►│ 1. pytest  (gate — must pass)│
                              │ 2. python -m tender_tracker  │
                              └───────────┬──────────────────┘
                                          │
             ┌────────────────────────────┼────────────────────────────┐
             ▼                            ▼                            ▼
    ┌─────────────────┐        ┌────────────────────┐       ┌──────────────────┐
    │ Microsoft Graph │        │  tenders.procure-  │       │ Microsoft Graph  │
    │  OneDrive (in)  │        │   ment.gov.ge      │       │  OneDrive (out)  │
    │  input workbook │        │  controller.php    │       │  dated sheet +   │
    │  debtor rows    │        │  HTML fragments    │       │  state + logs    │
    └─────────────────┘        └────────────────────┘       └──────────────────┘
             │                            │                            ▲
             │  overdue companies         │  latest payment per        │
             └────────────────────────────┴─── relevant tender ────────┘
```

1. Download the input workbook from OneDrive and read the debtor companies with positive overdue days.
2. Resolve each company to a supplier ID, then search its tenders via `library/controller.php`.
3. Parse the returned HTML fragments (the portal has no JSON API) for the latest payment row.
4. Write a new dated sheet into the output `.xlsm` workbook, as a real Excel table with values — not formulas.
5. Persist run state, logs and optional debug HTML back to OneDrive so a failed run can be resumed.

## Engineering notes

Things that turned out to matter, and what the code does about them:

- **The portal serves HTML fragments, not JSON.** Parsers live in [`parsers.py`](src/tender_tracker/parsers.py) and are covered by fixture-backed tests, so markup drift fails loudly in CI instead of silently producing empty sheets.
- **Its TLS chain is missing an intermediate certificate.** [`certs.py`](src/tender_tracker/certs.py) bundles the missing cert rather than disabling verification.
- **SharePoint stalls under load.** Storage calls retry transient network failures and every run logs a `run_id` so an interrupted batch can be resumed with `resume --run-id`.
- **Company search was the bottleneck.** It runs in a bounded thread pool (`company_search_concurrency`), with a floor on request interval so the portal is never hammered.
- **Reruns on the same day must not clobber.** Same-day reruns are written as numbered sheets, and a run is skipped entirely when today's sheet already exists.
- **Georgian number formatting uses a backtick thousands separator** (`7`500.00`). Handled at parse time, tested.

## Commands

```bash
python -m tender_tracker run                                    # the full nightly batch
python -m tender_tracker company --company-id 123456789 --company-name "Example LLC"
python -m tender_tracker tender  --app-id 678938                # one tender by internal id
python -m tender_tracker regid   --reg-id B2B260000023           # one tender by registration no.
python -m tender_tracker resume  --run-id 20260331T120000Z       # resume an interrupted run
python -m tender_tracker smoke-test --company-id 123456789       # live check, no workbook writes
```

Every command above is also available as a `workflow_dispatch` input on the Actions tab, so a
one-off rerun needs no local checkout.

## Install

```bash
pip install .[dev]      # dev extra pulls in pytest
python -m pytest        # 6 test modules, green on a fresh clone
```

Requires Python 3.12+.

## Configuration

Defaults live in [config/settings.yaml](config/settings.yaml). Deployment-specific values are
**not** committed — every OneDrive setting can be overridden by an environment variable, and an
environment variable wins whenever it is set and non-empty:

| Setting | Environment variable |
| --- | --- |
| `user_principal_name` | `ONEDRIVE_UPN` |
| `input_path` | `ONEDRIVE_INPUT_PATH` |
| `output_path` | `ONEDRIVE_OUTPUT_PATH` |
| `state_root` | `ONEDRIVE_STATE_ROOT` |
| `logs_root` | `ONEDRIVE_LOGS_ROOT` |
| `debug_root` | `ONEDRIVE_DEBUG_ROOT` |

The values committed in `settings.yaml` are placeholders, so a real tenant and its file paths
never need to reach the repository.

### Required GitHub Secrets

`MS_TENANT_ID` · `MS_CLIENT_ID` · `MS_CLIENT_SECRET` · `ONEDRIVE_UPN` · `ONEDRIVE_INPUT_PATH` · `ONEDRIVE_OUTPUT_PATH`

The Azure / Entra app registration needs Microsoft Graph **application** permissions to read and
write the target user's OneDrive for Business files.

## Layout

| Path | What it is |
|---|---|
| [`src/tender_tracker/runner.py`](src/tender_tracker/runner.py) | Orchestration — the batch, resume, and per-company flow |
| [`src/tender_tracker/tender_client.py`](src/tender_tracker/tender_client.py) | HTTP client for the portal (throttling, retries, search) |
| [`src/tender_tracker/parsers.py`](src/tender_tracker/parsers.py) | HTML fragment → dataclass |
| [`src/tender_tracker/storage.py`](src/tender_tracker/storage.py) | Microsoft Graph / OneDrive read + write |
| [`src/tender_tracker/excel.py`](src/tender_tracker/excel.py) | Workbook rendering (dated sheets, Excel tables) |
| [`src/tender_tracker/state.py`](src/tender_tracker/state.py) | Run state for resumability |
| [`src/tender_tracker/certs.py`](src/tender_tracker/certs.py) | TLS chain fix-up |
| [`docs/`](docs/) | Portal API reference, HTML structure, original flow logic |
| [`tests/`](tests/) | Fixture-backed tests — the CI gate |

## Local wrapper

For local development or emergency fallback:
[`scripts/run_tender_tracker.ps1`](scripts/run_tender_tracker.ps1).

## License

[MIT](LICENSE).
