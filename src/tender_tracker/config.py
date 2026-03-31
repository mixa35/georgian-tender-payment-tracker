from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

import yaml


@dataclass(slots=True)
class OneDriveSettings:
    user_principal_name: str
    input_path: str
    output_path: str
    state_root: str
    logs_root: str
    debug_root: str


@dataclass(slots=True)
class StorageSettings:
    backend: str
    local_root: str
    onedrive: OneDriveSettings


@dataclass(slots=True)
class ScraperSettings:
    base_url: str
    app_particip_status_id: int
    contract_status_ids: list[int]
    request_timeout_seconds: int
    retry_count: int
    retry_backoff_seconds: float
    min_request_interval_seconds: float
    detail_fetch_concurrency: int
    max_pages_per_company: int
    cache_ttl_hours: int
    log_level: str
    debug_html_capture: bool
    page_param_name: str
    browser_user_agent: str


@dataclass(slots=True)
class ExcelSettings:
    input_sheet_name: str
    output_sheet_date_format: str
    timezone: str
    company_id_column: str
    company_name_column: str
    overdue_days_column: str


@dataclass(slots=True)
class WorkflowSettings:
    default_cron: str
    github_artifact_name: str


@dataclass(slots=True)
class AuthSettings:
    tenant_id: str
    client_id: str
    client_secret: str


@dataclass(slots=True)
class AppSettings:
    storage: StorageSettings
    scraper: ScraperSettings
    excel: ExcelSettings
    workflow: WorkflowSettings
    auth: AuthSettings


def load_settings(config_path: str | Path, *, debug_override: bool = False) -> AppSettings:
    path = Path(config_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))

    onedrive = OneDriveSettings(**payload["storage"]["onedrive"])
    storage = StorageSettings(
        backend=payload["storage"]["backend"],
        local_root=payload["storage"]["local_root"],
        onedrive=onedrive,
    )
    scraper = ScraperSettings(**payload["scraper"])
    if debug_override:
        scraper.debug_html_capture = True
    excel = ExcelSettings(**payload["excel"])
    workflow = WorkflowSettings(**payload["workflow"])
    auth = AuthSettings(
        tenant_id=os.getenv("MS_TENANT_ID", ""),
        client_id=os.getenv("MS_CLIENT_ID", ""),
        client_secret=os.getenv("MS_CLIENT_SECRET", ""),
    )
    return AppSettings(storage=storage, scraper=scraper, excel=excel, workflow=workflow, auth=auth)
