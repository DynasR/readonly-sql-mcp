"""Run the server over stdio: python -m readonly_sql_mcp path/to/database.db"""
import argparse
import sys
from pathlib import Path

from .server import build_server


def main() -> None:
    parser = argparse.ArgumentParser(prog="readonly-sql-mcp", description=__doc__)
    parser.add_argument("database", type=Path, help="SQLite database file, opened read-only")
    database = parser.parse_args().database
    if not database.is_file():
        sys.exit(f"readonly-sql-mcp: no database file at {database}")
    build_server(database).run("stdio")


if __name__ == "__main__":
    main()
