import argparse
import sys

from sqlmodel import Session

from mastohuman.config.settings import settings
from mastohuman.db.engine import (engine,  # engine needed for Session(engine)
                                  init_db)
from mastohuman.etl.pipeline import IngestionManager
from mastohuman.llm.provider import Summarizer
from mastohuman.render.builder import SiteBuilder
from mastohuman.util.logging import setup_logging


# --- 1. Define Argument Helpers ---
def add_common_args(parser):
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of accounts processed (for partial runs)",
    )


def add_ingest_args(parser):
    parser.add_argument("--since-hours", type=int, default=settings.since_hours)
    parser.add_argument(
        "--force-fetch", action="store_true", help="Ignore overlap stop"
    )


def add_summarize_args(parser):
    parser.add_argument("--force-llm", action="store_true", help="Ignore LLM cache")


def add_render_args(parser):
    parser.add_argument("--no-llm", action="store_true", help="Use placeholders")


def cmd_ingest(args):
    print(f"Ingesting timeline (since {args.since_hours}h)...")
    if args.limit:
        print(f"Batch mode: limiting to {args.limit} accounts.")

    with Session(engine) as session:
        manager = IngestionManager(session)
        manager.run_pipeline(
            since_hours=args.since_hours, force_fetch=args.force_fetch, limit=args.limit
        )


def cmd_summarize(args):
    print("Summarizing content...")
    if args.limit:
        print(f"Batch mode: limiting to {args.limit} accounts.")

    with Session(engine) as session:
        summarizer = Summarizer(session)
        summarizer.process_all(force=args.force_llm, limit=args.limit)


def cmd_render(args):
    print(f"Rendering site to {settings.output_dir}...")
    with Session(engine) as session:
        builder = SiteBuilder(session)
        builder.build(no_llm=args.no_llm)


def cmd_run(args):
    print("=== MastoHuman Pipeline Start ===")

    # Pass 'args' directly. Since we updated p_run in the fix above,
    # args now contains all the necessary flags (since_hours, force_llm, etc).
    cmd_ingest(args)

    print("--- Summarizing ---")
    cmd_summarize(args)

    print("--- Rendering ---")
    cmd_render(args)

    # Handle archiving here if it's unique to the 'run' command,
    # or move it into cmd_render logic
    if settings.archive_dir:
        # You might need to instantiate builder again or refactor cmd_render
        # to return the builder
        pass

    print("=== Pipeline Complete ===")


def cmd_status(args):
    print("Checking status...")
    # TODO: Add logic to show how many accounts have fresh data vs stale


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="Mastodon Human-Centric Reader")
    # Global flags
    parser.add_argument("--config", help="Path to config file")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- 2. Configure 'run' (The Aggregate Command) ---
    p_run = subparsers.add_parser("run", help="Run full pipeline")
    # 'run' needs ALL arguments because it calls all functions
    add_common_args(p_run)
    add_ingest_args(p_run)
    add_summarize_args(p_run)
    add_render_args(p_run)

    # --- 3. Configure Individual Commands ---
    p_ingest = subparsers.add_parser("ingest", help="Fetch data")
    add_common_args(p_ingest)
    add_ingest_args(p_ingest)

    p_summarize = subparsers.add_parser("summarize", help="Generate LLM summaries")
    add_common_args(p_summarize)
    add_summarize_args(p_summarize)

    p_render = subparsers.add_parser("render", help="Build static site")
    add_render_args(p_render)

    p_status = subparsers.add_parser("status", help="Show cache stats")

    args = parser.parse_args()

    init_db()

    # Dispatcher
    try:
        if args.command == "run":
            cmd_run(args)
        elif args.command == "ingest":
            cmd_ingest(args)
        elif args.command == "summarize":
            cmd_summarize(args)
        elif args.command == "render":
            cmd_render(args)
        elif args.command == "status":
            cmd_status(args)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user. (Database is safe)")
        sys.exit(1)


if __name__ == "__main__":
    main()
