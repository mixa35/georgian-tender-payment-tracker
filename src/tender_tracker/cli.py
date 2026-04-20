from __future__ import annotations

import argparse
import json
from pathlib import Path

from tender_tracker.config import load_settings
from tender_tracker.logging_utils import build_logger
from tender_tracker.models import json_default
from tender_tracker.runner import create_app, write_github_summary
from tender_tracker.state import RunStateStore
from tender_tracker.storage import build_storage
from tender_tracker.tender_client import TenderPortalClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tender_tracker")
    parser.add_argument("--config", default="config/settings.yaml", help="Path to YAML settings file")
    parser.add_argument("--debug", action="store_true", help="Enable debug HTML capture")

    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--clear-cache", action="store_true", help="Invalidate cache before running")

    company_parser = subparsers.add_parser("company")
    company_parser.add_argument("--company-id", required=True)
    company_parser.add_argument("--company-name", default="")

    tender_parser = subparsers.add_parser("tender")
    tender_parser.add_argument("--app-id", required=True)

    regid_parser = subparsers.add_parser("regid")
    regid_parser.add_argument("--reg-id", required=True)

    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("--run-id", required=True)

    smoke_parser = subparsers.add_parser("smoke-test")
    smoke_parser.add_argument("--company-id", default="")
    smoke_parser.add_argument("--app-id", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config, debug_override=args.debug)

    work_dir = Path("work")
    log_path = work_dir / "logs" / "tender_tracker.log"
    debug_dir = work_dir / "debug"
    logger = build_logger(log_path, settings.scraper.log_level)
    storage = build_storage(settings)
    state_store = RunStateStore(settings, storage)
    client = TenderPortalClient(settings, logger=logger, debug_dir=debug_dir)
    app = create_app(settings, storage, state_store, client, logger)

    if args.command == "run":
        result = app.run(clear_cache=getattr(args, "clear_cache", False))
    elif args.command == "company":
        result = app.run_company(args.company_id, args.company_name or None)
    elif args.command == "tender":
        result = app.run_tender(args.app_id)
    elif args.command == "regid":
        result = app.run_regid(args.reg_id)
    elif args.command == "resume":
        result = app.resume(args.run_id)
    elif args.command == "smoke-test":
        result = app.smoke_test(company_id=args.company_id or None, app_id=args.app_id or None)
    else:
        parser.error(f"Unsupported command {args.command}")

    write_github_summary(result)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=json_default))
    return 0
