#!/usr/bin/env python3
"""Export chat.message_feedback rows (with referenced message) to a CSV file."""

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
        description="Export message feedback reviews to CSV."
    )
    parser.add_argument(
        "--name",
        default="reviews.csv",
        help="Output CSV filename (default: reviews.csv)",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("ERROR: DATABASE_URL is not set in the environment or .env file.")

    output_path = Path(args.name)

    query = """
        SELECT
            f.id            AS feedback_id,
            f.student_id    AS reviewer_student_id,
            f.thumb,
            f.comment,
            f.created_at    AS feedback_created_at,
            m.id            AS message_id,
            m.session_id,
            m.student_id    AS message_student_id,
            m.role,
            m.message_text,
            m.feedback_class,
            m.response_id,
            m.created_at    AS message_created_at
        FROM chat.message_feedback f
        JOIN chat.messages m ON m.id = f.message_id
        ORDER BY f.created_at;
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
