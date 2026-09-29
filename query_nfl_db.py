"""Compatibility wrapper for the project-local SQL query tool."""

from tools.query_nfl_db import query_nfl_db

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Run a read-only query against nfl.db")
    parser.add_argument("query", help="One read-only SQL query")
    args = parser.parse_args()
    print(json.dumps(query_nfl_db(args.query), indent=2))
