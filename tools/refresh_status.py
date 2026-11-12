#!/usr/bin/env python3
"""Turn the webapps-refresh snapshot into public/refresh-status.json.

Read-only on everything except the one output file. It does not start builds,
does not touch the catalogue, and does not need a workflow: the snapshot is
written by .github/workflows/webapps-refresh-twice-weekly.yml on
unclehowell/cedwyn (cedwyn#582) to resync/refresh/latest.json on the
evidence-resync branch.

Usage:
  python3 tools/refresh_status.py                      # fetch the live snapshot
  python3 tools/refresh_status.py --snapshot latest.json --out public/refresh-status.json

Rules for honest numbers:
  * A field the snapshot reports as null is written as "not measured", never 0.
  * Email-derived records are not counted as current: they only count once they
    have come through intake/review, and the snapshot does not say which have.
    Until the email-catalogue job fills that in, email is "not measured" and is
    left out of the counted total.
  * A dry-run snapshot is labelled as one.
"""
import argparse
import datetime
import json
import sys
import urllib.request

SNAPSHOT_URL = ("https://raw.githubusercontent.com/unclehowell/cedwyn/"
                "evidence-resync/resync/refresh/latest.json")
SNAPSHOT_SCHEMA = "cedwyn-webapps-refresh/1.0"
OUT_SCHEMA = "cedwyn-tweak-refresh-status/1.0"
NOT_MEASURED = "not measured"


class SnapshotError(ValueError):
    pass


def load_snapshot(source):
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=30) as r:  # noqa: S310
            return json.load(r)
    with open(source, encoding="utf-8") as f:
        return json.load(f)


def _measured(value):
    return NOT_MEASURED if value is None else value


def build_status(snap, now=None):
    if not isinstance(snap, dict) or snap.get("schema") != SNAPSHOT_SCHEMA:
        raise SnapshotError("unexpected snapshot schema: %r"
                            % (snap.get("schema") if isinstance(snap, dict) else None))
    cat = snap.get("central_catalogue")
    if not isinstance(cat, dict):
        raise SnapshotError("snapshot has no central_catalogue")
    kinds = cat.get("kinds") or {}
    total = cat.get("total")
    if not isinstance(kinds, dict) or not all(isinstance(v, int) for v in kinds.values()):
        raise SnapshotError("central_catalogue.kinds must map names to integers")

    counted_kinds = {k: v for k, v in sorted(kinds.items()) if k != "email"}
    counted_total = sum(counted_kinds.values())
    now = now or datetime.datetime.now(datetime.timezone.utc)

    return {
        "schema": OUT_SCHEMA,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "snapshot_schema": snap["schema"],
            "snapshot_at": snap.get("at"),
            "dry_run": snap.get("dry_run"),
            "build_action": snap.get("build_action"),
            "api_status": cat.get("api_status"),
        },
        "catalogue": {
            "counted_total": counted_total,
            "counted_kinds": counted_kinds,
            "snapshot_total_including_email": _measured(total),
            "kinds_sum_matches_total": (total == sum(kinds.values())
                                        if isinstance(total, int) else NOT_MEASURED),
        },
        "email": {
            "reviewed": NOT_MEASURED,
            "unreviewed": NOT_MEASURED,
            "counted": False,
            "note": ("Email-derived records are counted only once they have come "
                     "through intake/review. The snapshot does not say which have, "
                     "so none are counted here until the email-catalogue job reports it."),
        },
        "not_measured": sorted(
            ["email.reviewed", "email.unreviewed"]
            + [name for name, val in (
                ("candidates_awaiting_review", snap.get("candidates_awaiting_review")),
                ("core_record_files", cat.get("core_record_files")),
            ) if val is None]
        ),
        "builds_busy": snap.get("builds_busy") if snap.get("builds_busy") is not None else NOT_MEASURED,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=SNAPSHOT_URL, help="path or URL of latest.json")
    ap.add_argument("--out", default="public/refresh-status.json")
    args = ap.parse_args(argv)
    try:
        status = build_status(load_snapshot(args.snapshot))
    except (OSError, ValueError) as e:
        print("refresh_status: %s" % e, file=sys.stderr)
        return 1
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print("wrote %s (counted_total=%s, dry_run=%s)"
          % (args.out, status["catalogue"]["counted_total"], status["source"]["dry_run"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
