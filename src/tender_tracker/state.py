from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
from typing import Any

from tender_tracker.config import AppSettings
from tender_tracker.models import CompanyRecord, PaymentRecord, RunState, RunSummary, json_default
from tender_tracker.storage import BaseStorage


class RunStateStore:
    def __init__(self, settings: AppSettings, storage: BaseStorage) -> None:
        self.settings = settings
        self.storage = storage

    def _run_root(self, run_id: str) -> str:
        return f"{self.settings.storage.onedrive.state_root.rstrip('/')}/runs/{run_id}"

    def _run_state_path(self, run_id: str) -> str:
        return f"{self._run_root(run_id)}/run_state.json"

    def _latest_state_path(self) -> str:
        return f"{self.settings.storage.onedrive.state_root.rstrip('/')}/latest_run.json"

    def _cache_path(self, app_id: str) -> str:
        return f"{self.settings.storage.onedrive.state_root.rstrip('/')}/cache/{app_id}.json"

    def create(self, command: str, args: dict[str, Any], companies: list[CompanyRecord]) -> RunState:
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        state = RunState(
            run_id=run_id,
            started_at=datetime.now(UTC).isoformat(),
            command=command,
            args=args,
            queued_companies=[asdict(company) for company in companies],
            summary=asdict(RunSummary()),
        )
        self.save(state)
        return state

    def load(self, run_id: str) -> RunState:
        payload = self.storage.read_json(self._run_state_path(run_id))
        if payload is None:
            raise FileNotFoundError(f"Run state {run_id} was not found")
        return RunState.from_dict(payload)

    def save(self, state: RunState) -> None:
        payload = state.to_dict()
        self.storage.write_json(self._run_state_path(state.run_id), payload)
        self.storage.write_json(self._latest_state_path(), payload)

    def store_cache(self, record: PaymentRecord) -> None:
        payload = json.loads(json.dumps(asdict(record), ensure_ascii=False, default=json_default))
        payload["cached_at"] = datetime.now(UTC).isoformat()
        self.storage.write_json(self._cache_path(record.app_id), payload)

    def read_cache(self, app_id: str) -> dict[str, Any] | None:
        return self.storage.read_json(self._cache_path(app_id))
