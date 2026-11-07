#!/usr/bin/env python3
"""tally.py - the deterministic referee of a No Meeting decision.

No AI here. Agents propose, this script decides whether a decision is final.

Usage:
    python3 tally.py <ballot.md>            # human-readable verdict
    python3 tally.py <ballot.md> --json     # machine-readable verdict
    python3 tally.py <ballot.md> --now 2026-11-07T19:00+05:30

Ballot format (one file per decision, written by @facilitator):

    DECISION: Postgres or MongoDB for v2
    OPTIONS: Postgres | MongoDB
    STAKEHOLDERS: @priya @sam @alex
    QUORUM: 2/3
    DEADLINE: 2026-11-07T18:00+05:30
    OWNER: @gaurav
    ---
    @priya: Postgres | our data is relational
    @sam: MongoDB | schema keeps changing
    @priya: MongoDB | changed my mind after the devil's case

Rules (all enforced here, none by the model):
  * Only listed stakeholders count. Other voters are reported, not counted.
  * A vote must name one of the OPTIONS exactly (case-insensitive).
  * A stakeholder's LAST valid vote counts, so people can change their mind.
  * Quorum = fraction of stakeholders who must have voted.
  * Status:
      decided    - quorum met and one option has a strict majority of votes cast
      tie        - quorum met but no strict majority -> owner breaks the tie
      no_quorum  - deadline passed without quorum
      open       - deadline not reached and not everyone has voted
  * Every verdict carries a SHA-256 fingerprint of the ballot, so the
    Decision Record can prove which ballot it was computed from.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from fractions import Fraction

HEADER_KEYS = {"DECISION", "OPTIONS", "STAKEHOLDERS", "QUORUM", "DEADLINE", "OWNER"}
VOTE_RE = re.compile(r"^(@[\w.\-]+)\s*:\s*([^|]+?)\s*(?:\|\s*(.*))?$")


class BallotError(ValueError):
    """The ballot file itself is malformed."""


@dataclass
class Vote:
    voter: str
    option: str
    reason: str
    line: int


@dataclass
class Verdict:
    decision: str
    status: str
    winner: str | None
    counts: dict
    voted: list
    missing: list
    dissent: list
    ignored: list
    quorum_needed: int
    quorum_met: bool
    deadline: str
    deadline_passed: bool
    owner: str
    fingerprint: str
    notes: list = field(default_factory=list)


def _norm(handle: str) -> str:
    return handle.strip().lower()


def parse_ballot(text: str) -> tuple[dict, list[Vote], list[str]]:
    if "\n---" not in "\n" + text:
        raise BallotError("ballot needs a '---' line between the header and the votes")
    head, _, body = text.partition("\n---")
    if text.startswith("---"):
        head, body = "", text[3:]

    header: dict[str, str] = {}
    for raw in head.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition(":")
        key = key.strip().upper()
        if not sep or key not in HEADER_KEYS:
            raise BallotError(f"unknown header line: {raw!r}")
        header[key] = value.strip()

    missing = HEADER_KEYS - header.keys()
    if missing:
        raise BallotError(f"missing header fields: {', '.join(sorted(missing))}")

    votes: list[Vote] = []
    problems: list[str] = []
    # body starts right after '---'; first line is the remainder of the '---' line
    for offset, raw in enumerate(body.splitlines()[1:], start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = VOTE_RE.match(line)
        if not m:
            problems.append(f"unreadable vote line: {raw!r}")
            continue
        votes.append(Vote(m.group(1), m.group(2).strip(), (m.group(3) or "").strip(), offset))
    return header, votes, problems


def _parse_quorum(value: str, n: int) -> int:
    value = value.strip()
    try:
        if "/" in value or "." in value:
            frac = Fraction(value)
            if not 0 < frac <= 1:
                raise ValueError
            needed = -(-frac.numerator * n // frac.denominator)  # ceil
        else:
            needed = int(value)
    except (ValueError, ZeroDivisionError):
        raise BallotError(f"QUORUM must be a fraction like 2/3 or a count, got {value!r}")
    if not 1 <= needed <= n:
        raise BallotError(f"QUORUM resolves to {needed}, must be between 1 and {n}")
    return needed


def _parse_time(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.strip())
    except ValueError:
        raise BallotError(f"DEADLINE must be ISO 8601 like 2026-11-07T18:00+05:30, got {value!r}")
    if dt.tzinfo is None:
        raise BallotError("DEADLINE must include a timezone offset, e.g. +05:30")
    return dt


def tally(text: str, now: datetime | None = None) -> Verdict:
    header, votes, notes = parse_ballot(text)

    options = [o.strip() for o in header["OPTIONS"].split("|") if o.strip()]
    if len(options) < 2:
        raise BallotError("OPTIONS needs at least two choices separated by '|'")
    by_key = {o.lower(): o for o in options}
    if len(by_key) != len(options):
        raise BallotError("OPTIONS contains duplicates")

    stakeholders = []
    for h in header["STAKEHOLDERS"].split():
        if not h.startswith("@"):
            raise BallotError(f"stakeholder {h!r} must start with @")
        if _norm(h) not in [_norm(s) for s in stakeholders]:
            stakeholders.append(h)
    if not stakeholders:
        raise BallotError("STAKEHOLDERS is empty")

    needed = _parse_quorum(header["QUORUM"], len(stakeholders))
    deadline = _parse_time(header["DEADLINE"])
    now = now or datetime.now(timezone.utc)
    deadline_passed = now >= deadline

    canon = {_norm(s): s for s in stakeholders}
    final: dict[str, Vote] = {}
    ignored: list[str] = []
    for v in votes:
        who = _norm(v.voter)
        if who not in canon:
            ignored.append(f"{v.voter} is not a stakeholder (line {v.line})")
            continue
        opt = by_key.get(v.option.lower())
        if opt is None:
            ignored.append(f"{v.voter} voted for unknown option {v.option!r} (line {v.line})")
            continue
        final[who] = Vote(canon[who], opt, v.reason, v.line)

    counts = {o: 0 for o in options}
    for v in final.values():
        counts[v.option] += 1

    cast = len(final)
    quorum_met = cast >= needed
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    top, top_n = ranked[0]
    majority = top_n * 2 > cast

    everyone_voted = cast == len(stakeholders)
    if quorum_met and (deadline_passed or everyone_voted):
        status, winner = ("decided", top) if majority else ("tie", None)
    elif deadline_passed:
        status, winner = "no_quorum", None
    else:
        status, winner = "open", None

    dissent = [
        {"who": v.voter, "option": v.option, "reason": v.reason}
        for v in final.values()
        if winner is not None and v.option != winner
    ]

    fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return Verdict(
        decision=header["DECISION"],
        status=status,
        winner=winner,
        counts=counts,
        voted=[v.voter for v in final.values()],
        missing=[s for s in stakeholders if _norm(s) not in final],
        dissent=dissent,
        ignored=ignored,
        quorum_needed=needed,
        quorum_met=quorum_met,
        deadline=deadline.isoformat(),
        deadline_passed=deadline_passed,
        owner=header["OWNER"],
        fingerprint=fingerprint,
        notes=notes,
    )


def render(v: Verdict) -> str:
    icon = {"decided": "✅", "tie": "⚖️", "no_quorum": "⛔", "open": "⏳"}[v.status]
    lines = [f"{icon} {v.decision}", f"status: {v.status}"]
    if v.winner:
        lines.append(f"winner: {v.winner}")
    lines.append("counts: " + ", ".join(f"{k} {n}" for k, n in v.counts.items()))
    lines.append(f"quorum: {len(v.voted)} voted, {v.quorum_needed} needed ({'met' if v.quorum_met else 'not met'})")
    if v.missing:
        lines.append("waiting on: " + " ".join(v.missing))
    for d in v.dissent:
        lines.append(f"dissent: {d['who']} -> {d['option']}" + (f" ({d['reason']})" if d["reason"] else ""))
    for i in v.ignored + v.notes:
        lines.append(f"ignored: {i}")
    if v.status == "tie":
        lines.append(f"next: owner {v.owner} must break the tie")
    lines.append(f"fingerprint: sha256:{v.fingerprint[:16]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ballot")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--now", help="override current time (ISO 8601 with offset), for testing")
    args = ap.parse_args(argv)
    try:
        with open(args.ballot, encoding="utf-8") as fh:
            text = fh.read()
        now = _parse_time(args.now) if args.now else None
        verdict = tally(text, now)
    except (OSError, BallotError) as exc:
        print(f"tally: error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(asdict(verdict), indent=2, ensure_ascii=False) if args.json else render(verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
