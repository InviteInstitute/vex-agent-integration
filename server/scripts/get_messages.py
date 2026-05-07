#!/usr/bin/env python3
"""Export all chat.messages rows with the latest feedback (if any) to a CSV file."""

import argparse
import csv
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# Load .env from the project root (one level above this script's directory)
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export all messages with latest feedback to CSV."
    )
    parser.add_argument(
        "--name",
        default="messages.csv",
        help="Output CSV filename (default: messages.csv)",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("ERROR: DATABASE_URL is not set in the environment or .env file.")

    output_path = Path(args.name)

    query = """
        SELECT
            m.id            AS message_id,
            m.session_id,
            m.student_id,
            m.role,
            m.message_text,
            m.feedback_class,
            m.response_id,
            m.created_at    AS message_created_at,
            f.id            AS feedback_id,
            f.thumb,
            f.comment,
            f.created_at    AS feedback_created_at
        FROM chat.messages m
        LEFT JOIN LATERAL (
            SELECT id, thumb, comment, created_at
            FROM chat.message_feedback
            WHERE message_id = m.id
            ORDER BY created_at DESC
            LIMIT 1
        ) f ON TRUE
        ORDER BY m.created_at;
    """

    conn = psycopg.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
    finally:
        conn.close()

    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        writer.writerows(rows)

    print(f"Wrote {len(rows)} row(s) to {output_path}")


if __name__ == "__main__":
    main()
