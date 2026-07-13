"""Developer commands for exporting and serving the local V application."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(prog="uc-visualisation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve", help="serve the read-only API and built web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8000, type=int)
    export = subparsers.add_parser("export-fixture", help="regenerate the V1 synthetic fixture")
    export.add_argument(
        "--output",
        type=Path,
        default=Path("fixtures/visualisation/v1/synthetic_strict_fifo_diverge_v1.json"),
    )
    args = parser.parse_args()
    if args.command == "export-fixture":
        from .fixtures import write_synthetic_fixture

        bundle = write_synthetic_fixture(args.output)
        print(f"wrote {bundle.run.run_id} to {args.output}")
        return

    import uvicorn

    uvicorn.run(
        "urban_cybernetics.visualisation.server:create_app",
        factory=True,
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
