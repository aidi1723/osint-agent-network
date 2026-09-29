import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.store import SQLiteStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Import OSINT Agent Hub JSON snapshots into SQLite.")
    parser.add_argument("--db", default="data/osint.sqlite")
    parser.add_argument("--agents")
    parser.add_argument("--investigation", action="append", default=[])
    args = parser.parse_args()

    store = SQLiteStore(args.db)
    if args.agents:
        agents_payload = _read_json(args.agents)
        for agent in agents_payload.get("agents", []):
            store.import_agent(agent)

    for path in args.investigation:
        payload = _read_json(path)
        if payload.get("id"):
            store.import_detail(payload)

    print(
        json.dumps(
            {
                "db": args.db,
                "agents": len(store.list_agents()),
                "investigations": len(store.list_investigations()),
            },
            ensure_ascii=False,
        )
    )


def _read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
