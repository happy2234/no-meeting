import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from tally import BallotError, tally  # noqa: E402

HEAD = """DECISION: Postgres or MongoDB for v2
OPTIONS: Postgres | MongoDB
STAKEHOLDERS: @priya @sam @alex
QUORUM: 2/3
DEADLINE: 2026-11-07T18:00+05:30
OWNER: @gaurav
---
"""
BEFORE = datetime.fromisoformat("2026-11-07T17:00+05:30")
AFTER = datetime.fromisoformat("2026-11-07T18:30+05:30")


class TallyTests(unittest.TestCase):
    def test_decided_when_everyone_voted(self):
        v = tally(HEAD + "@priya: Postgres | relational\n@sam: Postgres\n@alex: MongoDB | flexible\n", BEFORE)
        self.assertEqual(v.status, "decided")
        self.assertEqual(v.winner, "Postgres")
        self.assertEqual(v.dissent, [{"who": "@alex", "option": "MongoDB", "reason": "flexible"}])

    def test_open_before_deadline_if_someone_missing(self):
        v = tally(HEAD + "@priya: Postgres\n@sam: Postgres\n", BEFORE)
        self.assertEqual(v.status, "open")
        self.assertEqual(v.missing, ["@alex"])

    def test_decided_after_deadline_with_quorum(self):
        v = tally(HEAD + "@priya: Postgres\n@sam: Postgres\n", AFTER)
        self.assertEqual(v.status, "decided")

    def test_no_quorum_after_deadline(self):
        v = tally(HEAD + "@priya: Postgres\n", AFTER)
        self.assertEqual(v.status, "no_quorum")
        self.assertIsNone(v.winner)

    def test_tie_goes_to_owner(self):
        v = tally(HEAD + "@priya: Postgres\n@sam: MongoDB\n", AFTER)
        self.assertEqual(v.status, "tie")

    def test_last_vote_wins(self):
        v = tally(HEAD + "@priya: Postgres\n@priya: mongodb | changed mind\n@sam: MongoDB\n@alex: MongoDB\n", BEFORE)
        self.assertEqual(v.counts, {"Postgres": 0, "MongoDB": 3})

    def test_outsiders_and_unknown_options_ignored(self):
        v = tally(HEAD + "@mallory: Postgres\n@priya: SQLite\n@sam: MongoDB\n@alex: MongoDB\n", AFTER)
        self.assertEqual(len(v.ignored), 2)
        self.assertEqual(v.counts["Postgres"], 0)
        self.assertEqual(v.status, "decided")

    def test_handles_are_case_insensitive(self):
        v = tally(HEAD + "@Priya: Postgres\n@SAM: Postgres\n", AFTER)
        self.assertEqual(v.voted, ["@priya", "@sam"])

    def test_fingerprint_changes_when_ballot_changes(self):
        a = tally(HEAD + "@priya: Postgres\n", BEFORE).fingerprint
        b = tally(HEAD + "@priya: MongoDB\n", BEFORE).fingerprint
        self.assertNotEqual(a, b)

    def test_malformed_ballots_rejected(self):
        with self.assertRaises(BallotError):
            tally("DECISION: x\n---\n", BEFORE)
        with self.assertRaises(BallotError):
            tally(HEAD.replace("+05:30", ""), BEFORE)
        with self.assertRaises(BallotError):
            tally(HEAD.replace("Postgres | MongoDB", "Postgres"), BEFORE)


if __name__ == "__main__":
    unittest.main()
