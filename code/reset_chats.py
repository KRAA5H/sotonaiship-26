"""Forget every stored conversation, profile and task. Reports stay on the dashboard."""

import reports_db

TABLES = ("messages", "threads", "claims_sent", "delivery_outbox",
          "turn_operations", "profiles", "tasks")


def main():
    conn = reports_db.connect()
    try:
        for table in TABLES:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not exists:
                print(f"{table}: absent")
                continue
            before = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            conn.execute(f"DELETE FROM {table}")
            print(f"{table}: cleared {before}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
