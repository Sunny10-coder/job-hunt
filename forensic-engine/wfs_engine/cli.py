"""Command line entry point (used by the Tauri sidecar and by developers)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import (cases as cases_mod, config, db, importer, reporting, samples)
from .api import server as api_server
from .config import ENGINE_VERSION


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wfs-engine",
                                     description="WhatsApp Forensic Studio AI engine")
    parser.add_argument("--version", action="version", version=f"wfs-engine {ENGINE_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the local HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--token", default=None, help="bearer token (or WFS_TOKEN env)")

    sub.add_parser("migrate", help="apply database migrations")
    sub.add_parser("info", help="print paths and versions")

    mk = sub.add_parser("case-create", help="create a case")
    mk.add_argument("name")
    mk.add_argument("--description", default="")

    imp = sub.add_parser("import", help="import evidence into a case")
    imp.add_argument("case_id")
    imp.add_argument("paths", nargs="+")
    imp.add_argument("--timezone", default="UTC")
    imp.add_argument("--date-order", default="auto", choices=["auto", "mdy", "dmy"])

    rep = sub.add_parser("report", help="generate a report")
    rep.add_argument("case_id")
    rep.add_argument("--type", default="case")
    rep.add_argument("--format", default="pdf",
                     choices=["pdf", "html", "xlsx", "csv", "json"])
    rep.add_argument("--out", default=None)

    demo = sub.add_parser("demo", help="create a case from the synthetic dataset")
    demo.add_argument("--dir", default=None)

    args = parser.parse_args(argv)
    config.ensure_dirs()
    db.migrate()

    if args.command == "serve":
        api_server.serve(args.host, args.port,
                         args.token or api_server.api_key_from_env())
        return 0
    if args.command == "migrate":
        applied = db.migrate()
        print(json.dumps({"applied": applied, "db": str(config.db_path())}))
        return 0
    if args.command == "info":
        print(json.dumps({"engine": ENGINE_VERSION, "data_dir": str(config.data_dir()),
                          "db": str(config.db_path())}, indent=2))
        return 0
    if args.command == "case-create":
        with db.session() as conn:
            case = cases_mod.create_case(conn, args.name, args.description)
        print(json.dumps({"case_id": case["id"], "case_number": case["case_number"]}))
        return 0
    if args.command == "import":
        with db.session() as conn:
            job = importer.create_job(
                conn, args.case_id, args.paths,
                importer.ImportOptions(source_timezone=args.timezone,
                                       date_order=args.date_order))
            job_id = job["job_id"]
            importer.run_job(job_id)  # CLI runs synchronously
            print(json.dumps(importer.get_job(conn, job_id), indent=2)[:8000])
        return 0
    if args.command == "report":
        with db.session() as conn:
            result = reporting.generate(conn, args.case_id, args.type, args.format)
        if args.out:
            Path(args.out).write_bytes(Path(result["path"]).read_bytes())
            result["path"] = args.out
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "demo":
        target = Path(args.dir) if args.dir else config.data_dir() / "sample-data"
        info = samples.write_sample_files(target)
        with db.session() as conn:
            case = cases_mod.create_case(conn, "Synthetic sample case",
                                         "Generated demo dataset (no real conversations)")
            job = importer.create_job(conn, case["id"], info["files"],
                                      importer.ImportOptions())
            importer.run_job(job["job_id"])
        print(json.dumps({"case_id": case["id"], "files": info["files"]}, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
