#!/usr/bin/env python3
"""CLI för den lokala Kunskapstratten.

Användning:
    python run.py                      Inget kommando = starta GUI:t (samma som "gui")
    python run.py process              Bearbeta allt nytt i inboxen en gång
    python run.py process --force      Bearbeta om, även redan processade filer
    python run.py status               Visa status för inbox/register
    python run.py watch                Bevaka inboxen kontinuerligt
    python run.py watch --interval 5   ...med annat skanningsintervall (sek)
    python run.py skills               Lista skapade bearbetningsskills
    python run.py gui                  Starta det lokala webb-GUI:t (bläddra, skills, chatt)
    python run.py gui --port 8080      ...på annan port

Config läses från config.yaml i samma mapp om inget annat anges med --config.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config  # noqa: E402
from src.pipeline import Pipeline  # noqa: E402
from src.skillbuilder import list_custom_skills  # noqa: E402
from src.watcher import watch  # noqa: E402


def setup_logging(config: Config) -> None:
    config.paths.logs.mkdir(parents=True, exist_ok=True)
    log_file = config.paths.logs / "pipeline.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_file, encoding="utf-8")],
    )


def cmd_process(config: Config, args: argparse.Namespace) -> None:
    pipeline = Pipeline(config)
    try:
        stats = pipeline.process_all(force=args.force)
        print(
            f"Bearbetade: {stats['processed']}  "
            f"Överhoppade: {stats['skipped']}  "
            f"Fel: {stats['errors']}"
        )
    finally:
        pipeline.close()


def cmd_status(config: Config, args: argparse.Namespace) -> None:
    pipeline = Pipeline(config)
    try:
        counts = pipeline.registry.counts()
        pending_in_inbox = len(pipeline.discover_files())
        print("== Kunskapstratten - status ==")
        print(f"Inbox:            {config.paths.inbox.resolve()}")
        print(f"Output:           {config.paths.output.resolve()}")
        print(f"Skills:           {config.paths.skills.resolve()}")
        print(f"Arkiv (klara):    {config.paths.processed_archive.resolve()}")
        print(f"Register (db):    {config.paths.registry_db.resolve()}")
        print(f"Filer i inbox nu: {pending_in_inbox}")
        print("Registerstatus (historik):")
        if not counts:
            print("  (inga filer processade ännu)")
        for status, count in counts.items():
            print(f"  {status:10s}: {count}")

        errors = pipeline.registry.list_by_status("error")
        if errors:
            print("\nFiler med fel:")
            for row in errors:
                print(f"  - {row['source_path']}: {row['error_message']}")
    finally:
        pipeline.close()


def cmd_watch(config: Config, args: argparse.Namespace) -> None:
    watch(config, interval_seconds=args.interval)


def cmd_skills(config: Config, args: argparse.Namespace) -> None:
    skills = list_custom_skills(config)
    print(f"{len(skills)} bearbetningsskills tillgängliga.")
    for skill in skills:
        print(f"  - {skill['name']}: {skill['description']}")
    print(f"Skills-katalog: {config.paths.skills.resolve()}")


def cmd_gui(config: Config, args: argparse.Namespace) -> None:
    from src.webapp import run_gui

    if args.port:
        config.gui.port = args.port
    if args.host:
        config.gui.host = args.host
    run_gui(config)


def main() -> None:
    parser = argparse.ArgumentParser(description="Kunskapstratten - lokal dokument- och AI-pipeline")
    parser.add_argument("--config", default="config.yaml", help="Sökväg till config.yaml")
    parser.set_defaults(func=cmd_gui, port=None, host=None)
    sub = parser.add_subparsers(dest="command", required=False)

    p_process = sub.add_parser("process", help="Bearbeta filer i inboxen en gång")
    p_process.add_argument("--force", action="store_true", help="Bearbeta om redan processade filer")
    p_process.set_defaults(func=cmd_process)

    p_status = sub.add_parser("status", help="Visa status för inbox/register")
    p_status.set_defaults(func=cmd_status)

    p_watch = sub.add_parser("watch", help="Bevaka inboxen kontinuerligt")
    p_watch.add_argument("--interval", type=int, default=10, help="Sekunder mellan skanningar")
    p_watch.set_defaults(func=cmd_watch)

    p_skills = sub.add_parser("skills", help="Lista skapade bearbetningsskills")
    p_skills.set_defaults(func=cmd_skills)

    p_gui = sub.add_parser("gui", help="Starta det lokala webb-GUI:t")
    p_gui.add_argument("--port", type=int, default=None, help="Port (standard: från config.yaml)")
    p_gui.add_argument("--host", default=None, help="Host (standard: från config.yaml)")
    p_gui.set_defaults(func=cmd_gui)

    args = parser.parse_args()
    config = Config.load(args.config)
    setup_logging(config)
    args.func(config, args)


if __name__ == "__main__":
    main()
