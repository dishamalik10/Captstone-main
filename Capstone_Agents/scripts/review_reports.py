"""Review user reports by hand (ENGINEERING_PLAN 4.4).

    python -m scripts.review_reports                    # list open reports, oldest first
    python -m scripts.review_reports --resolve rpt_x    # mark one as reviewed, no action
    python -m scripts.review_reports --resolve rpt_x --remove
        # ...and take the content down: a listing is paused, a post is deleted,
        # a conversation's messages are deleted. A reported *user* is not deleted here;
        # block or delete the account yourself if that is warranted.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import connection, init_database, row, rows, utc_now  # noqa: E402


def list_open() -> None:
    open_reports = rows("SELECT * FROM reports WHERE status='open' ORDER BY created_at")
    if not open_reports:
        print("No open reports.")
        return
    for report in open_reports:
        print(f"{report['report_id']}  {report['created_at'][:16]}  {report['target_type']} {report['target_id']}")
        print(f"  reason: {report['reason']}  reporter: {report['reporter_id']}  owner: {report['target_owner_id']}")
        if report["details"]:
            print(f"  details: {report['details']}")
        print("  snapshot: " + json.dumps(json.loads(report["snapshot_json"]), ensure_ascii=False)[:600])
        print()


def resolve(report_id: str, remove: bool) -> None:
    report = row("SELECT * FROM reports WHERE report_id=?", (report_id,))
    if report is None:
        sys.exit(f"No report {report_id}")
    with connection() as db:
        if remove:
            kind, target = report["target_type"], report["target_id"]
            if kind == "listing":
                db.execute("UPDATE products SET status='paused', updated_at=? WHERE product_id=?", (utc_now(), target))
            elif kind == "post":
                db.execute("DELETE FROM social_posts WHERE post_id=?", (target,))
            elif kind == "conversation":
                db.execute("DELETE FROM conversation_messages WHERE conversation_id=?", (target,))
        status = "removed" if remove else "reviewed"
        # Every open report about the same thing is settled together.
        db.execute(
            "UPDATE reports SET status=?, resolved_at=? WHERE target_type=? AND target_id=? AND status='open'",
            (status, utc_now(), report["target_type"], report["target_id"]),
        )
    print(f"{report_id}: {status}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--resolve", metavar="REPORT_ID")
    parser.add_argument("--remove", action="store_true", help="also take the reported content down")
    args = parser.parse_args()
    init_database()
    if args.resolve:
        resolve(args.resolve, args.remove)
    else:
        list_open()


if __name__ == "__main__":
    main()
