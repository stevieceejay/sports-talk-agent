"""Read-only JSON query tool for nfl.db."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "nfl.db"
ALLOWED_OBJECTS = frozenset({"v_season_team", "v_team_game", "v_explosive_season"})
_OBJECT_REFERENCE = re.compile(r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_READ_ONLY_START = re.compile(r"^\s*(?:select|with|explain\s+query\s+plan)\b", re.IGNORECASE)


def query_nfl_db(query: str) -> dict[str, Any]:
    """Run one read-only query against the three approved NFL views."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty SQL string")
    if not _READ_ONLY_START.match(query):
        raise ValueError("only SELECT, WITH, or EXPLAIN QUERY PLAN statements are allowed")
    if len([part for part in query.split(";") if part.strip()]) != 1:
        raise ValueError("exactly one SQL statement is allowed")

    referenced = {name.lower() for name in _OBJECT_REFERENCE.findall(query)}
    disallowed = sorted(referenced - ALLOWED_OBJECTS)
    if disallowed:
        raise ValueError(f"disallowed table/view reference(s): {', '.join(disallowed)}")
    if not referenced:
        raise ValueError("query must reference at least one approved NFL view")

    uri = f"{DB_PATH.resolve().as_uri()}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        cursor = connection.execute(query)
        columns = [item[0] for item in cursor.description or ()]
        rows = [dict(row) for row in cursor.fetchall()]
    return {"columns": columns, "rows": rows, "row_count": len(rows)}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="One read-only SQL query")
    args = parser.parse_args()
    print(json.dumps(query_nfl_db(args.query), indent=2))
