import datetime
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import refresh_status as rs  # noqa: E402

# Copy of resync/refresh/latest.json on cedwyn evidence-resync, commit 24f0ce2 (11 Nov 2026 18:21Z).
SNAPSHOT = {
    "schema": "cedwyn-webapps-refresh/1.0",
    "date": "2026-11-11",
    "at": "2026-11-11T18:21:09Z",
    "central_catalogue": {
        "api_status": 200,
        "total": 2202,
        "kinds": {"artifact": 25, "catalogue_candidate": 7, "email": 1138, "evidence": 806,
                  "media": 128, "missing_record": 86, "person": 12},
        "core_record_files": None,
    },
    "candidates_awaiting_review": None,
    "builds_busy": [],
    "build_action": "dry run: would dispatch build-cedwyn on main",
    "dry_run": True,
}
NOW = datetime.datetime(2026, 11, 12, 12, 0, 0, tzinfo=datetime.timezone.utc)


class RefreshStatusTest(unittest.TestCase):
    def test_email_is_not_counted(self):
        s = rs.build_status(SNAPSHOT, NOW)
        self.assertNotIn("email", s["catalogue"]["counted_kinds"])
        self.assertEqual(s["catalogue"]["counted_total"], 2202 - 1138)
        self.assertEqual(s["catalogue"]["snapshot_total_including_email"], 2202)
        self.assertEqual(s["email"]["reviewed"], "not measured")
        self.assertEqual(s["email"]["unreviewed"], "not measured")
        self.assertIs(s["email"]["counted"], False)

    def test_nulls_are_not_measured_never_zero(self):
        s = rs.build_status(SNAPSHOT, NOW)
        self.assertIn("candidates_awaiting_review", s["not_measured"])
        self.assertIn("core_record_files", s["not_measured"])
        snap = json.loads(json.dumps(SNAPSHOT))
        snap["candidates_awaiting_review"] = 0
        snap["central_catalogue"]["core_record_files"] = 12
        s2 = rs.build_status(snap, NOW)
        self.assertNotIn("candidates_awaiting_review", s2["not_measured"])
        self.assertNotIn("core_record_files", s2["not_measured"])

    def test_dry_run_is_labelled_and_time_is_utc(self):
        s = rs.build_status(SNAPSHOT, NOW)
        self.assertIs(s["source"]["dry_run"], True)
        self.assertEqual(s["generated_at"], "2026-11-12T12:00:00Z")
        self.assertEqual(s["source"]["snapshot_at"], "2026-11-11T18:21:09Z")

    def test_kinds_sum_check(self):
        self.assertIs(rs.build_status(SNAPSHOT, NOW)["catalogue"]["kinds_sum_matches_total"], True)
        snap = json.loads(json.dumps(SNAPSHOT))
        snap["central_catalogue"]["total"] = 9999
        self.assertIs(rs.build_status(snap, NOW)["catalogue"]["kinds_sum_matches_total"], False)

    def test_missing_total_is_not_measured(self):
        snap = json.loads(json.dumps(SNAPSHOT))
        snap["central_catalogue"]["total"] = None
        c = rs.build_status(snap, NOW)["catalogue"]
        self.assertEqual(c["snapshot_total_including_email"], "not measured")
        self.assertEqual(c["kinds_sum_matches_total"], "not measured")

    def test_rejects_wrong_schema_and_bad_kinds(self):
        with self.assertRaises(rs.SnapshotError):
            rs.build_status({"schema": "other/1"}, NOW)
        with self.assertRaises(rs.SnapshotError):
            rs.build_status(None, NOW)
        bad = json.loads(json.dumps(SNAPSHOT))
        bad["central_catalogue"]["kinds"]["media"] = "128"
        with self.assertRaises(rs.SnapshotError):
            rs.build_status(bad, NOW)

    def test_cli_writes_file_and_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            snap = os.path.join(d, "latest.json")
            out = os.path.join(d, "out.json")
            with open(snap, "w") as f:
                json.dump(SNAPSHOT, f)
            self.assertEqual(rs.main(["--snapshot", snap, "--out", out]), 0)
            with open(out) as f:
                self.assertEqual(json.load(f)["schema"], "cedwyn-tweak-refresh-status/1.0")
            self.assertEqual(rs.main(["--snapshot", os.path.join(d, "missing.json"), "--out", out]), 1)


if __name__ == "__main__":
    unittest.main()
