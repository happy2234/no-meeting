# No Meeting 🗳️

**A Switch room that makes team decisions without a meeting.**

Post `Decide: Postgres or MongoDB?` in Discord. Three AI agents collect every stakeholder's
position, argue the losing side once, and write a signed Decision Record. A plain Python
script, not an AI, decides when the decision is final.

Built for the **Flip the Switch** hackathon (WeMakeDevs × DevTools Academy × Switch AI).
Track 01: Best Business Workflow.

---

## The problem

Teams book a 30-minute meeting for every decision that needs more than one person: which
database, which vendor, which date. Half the attendees are there "just in case", the quiet
ones never speak, and a week later nobody remembers *why* the team chose what it chose.

No Meeting turns that meeting into a short, written, asynchronous process in the chat the
team already uses:

| In a meeting | In No Meeting |
|---|---|
| Everyone blocks 30 minutes at the same time | Each person spends 1 minute, when it suits them |
| The loudest voice wins | Every stakeholder is asked by name, silence is visible |
| Groupthink | A Devil's Advocate makes the best case against the leader, once |
| "Who decided this?" | A Decision Record with votes, dissent and a fingerprint |
| Notes on one laptop | A room document every person and agent can read later |

## How it works

```
 person in #decide            Switch room "decide" (Discord channel)
 ─────────────────            ─────────────────────────────────────
 "Decide: A or B?" ─────────▶ @facilitator  writes decisions/D-1.md (the ballot)
                                   │        @-mentions EACH stakeholder by name
 stakeholders reply ─────────▶     │        appends their vote, runs tally.py
                                   ▼
                              @devil        best case against the leading option (once)
                                   │
                                   ▼
                              tools/tally.py   ◀── deterministic, no AI:
                                   │               quorum, deadline, majority, tie,
                                   │               ignores outsiders, last vote counts,
                                   │               sha256 fingerprint
                                   ▼
                              @recorder     Decision Record as a ROOM DOCUMENT
 owner: "approve D-1" ───────▶              status FINAL only after the owner approves
 next week: "why did we           │
 pick Postgres?" ────────────▶ @recorder answers from the record, with its name
```

**The model proposes, the code decides.** Agents never declare a winner; they run
`tools/tally.py` and report what it says.

## Why Switch is central

Take Switch away and No Meeting stops working:

| Switch feature | What No Meeting uses it for |
|---|---|
| **Room = Discord channel** | `#decide` is where people and agents work together, nothing to install |
| **Addressing** | Facilitator answers anyone (any teammate can open a decision); Devil and Recorder only take work from the owner and other agents, so nobody can make the Recorder approve a decision |
| **Agent-to-agent handoff** | Facilitator → Devil → Recorder hand work over by @-mentioning each other in the room. No agent calls another directly |
| **@-routing to humans** | Agents mention each stakeholder and the owner by name |
| **Room instructions** | One briefing every agent reads: only tally.py decides, only the owner approves, dissent is always recorded |
| **Room documents** | Decision Records live in the room, so any person or a brand-new agent can answer "why did we pick X?" months later |
| **Template** | `templates/no-meeting.template.yaml` creates the three agents, the room and the kickoff in one step |
| **Approval prompts** | Agent tool calls that need permission (e.g. writing a ballot) show up for the owner to allow |

## Repository

| Path | What it is |
|---|---|
| `templates/no-meeting.template.yaml` | Switch template: 3 agents, the room, its instructions, the kickoff |
| `tools/tally.py` | The deterministic referee (standard library only) |
| `tests/test_tally.py` | 10 tests for the referee |
| `decisions/` | Ballots (`D-n.md`) and records (`D-n.record.md`) written by the agents |
| `examples/D-1.md` | A sample ballot from the demo |

## Run it yourself

**You need:** Switch Console 0.40.x with a local server running, Docker, Claude Code
installed and signed in, Python 3.10+, git, and a Discord server connected to Switch.
Tested on Fedora Linux with Switch Console 0.40.1 and Switch server 0.31.0.

### 1. Install Switch and connect Discord
1. Install Switch Console and choose **On this computer → Start**
   ([quickstart](https://docs.switchagents.ai/switch-rooms/getting-started)).
2. Create a Discord application and bot, turn on **Server Members Intent** and
   **Message Content Intent**, invite the bot to your server.
3. In Console: **Connectors → Connect → Discord**, paste the bot token, link your Discord account.

### 2. Get the code and check the referee
```bash
git clone https://github.com/<you>/no-meeting.git
cd no-meeting
python3 -m unittest discover -s tests -v      # 10 tests pass
python3 tools/tally.py examples/D-1.md --now 2026-11-07T17:00+05:30
```

### 3. Create the room from the template
In Switch Console open **Templates**, import `templates/no-meeting.template.yaml`, then fill in:

| Field | Example |
|---|---|
| `team` | `nm` |
| `provider` | Claude Code |
| `bridge` | your Discord server |
| `repo_dir` | `/home/you/no-meeting` (absolute path of this clone) |

Console creates `nm-facilitator`, `nm-devil`, `nm-recorder` and the `#decide` room with
you in it, then posts the kickoff.

**If the template import fails on your version**, set it up by hand (5 minutes):
create three agents under **Your Agents** with the names above and provider Claude Code,
paste each agent's `instructions` block from the template (replace `{team}` and
`{repo_dir}`), set addressing as in the template, create a Discord channel `#decide`,
post a message in it, then `!invite-agent @nm-facilitator` (and the other two) and paste
the room `instructions` block into the room's Instructions.

### 4. Let your teammates talk to the facilitator
New agents only answer their owner. Allow your teammates to address `nm-facilitator`
(agent settings → addressing **anyone**, as the template sets).

### 5. Make a decision
In `#decide`:
```
Decide: Postgres or MongoDB for the v2 backend? Options: Postgres | MongoDB.
Stakeholders: @priya @sam @alex. Deadline: 6 PM today.
```
Stakeholders answer `D-1: Postgres because ...`. When the tally closes, the Recorder posts the
Decision Record and asks the owner to reply `approve D-1`.

## The referee: `tools/tally.py`

```
$ python3 tools/tally.py decisions/D-1.md
✅ Postgres or MongoDB for the v2 backend
status: decided
winner: Postgres
counts: Postgres 3, MongoDB 0
quorum: 3 voted, 2 needed (met)
fingerprint: sha256:6aeabcefe1701c69
```

| Status | When |
|---|---|
| `open` | before the deadline and not everyone has voted |
| `decided` | quorum met, and either everyone voted or the deadline passed, and one option has a strict majority |
| `tie` | quorum met but no strict majority, the owner breaks it |
| `no_quorum` | deadline passed without enough votes, the owner extends or decides |

Votes from non-stakeholders and votes for options that are not on the ballot are listed
under `ignored`, never counted. A stakeholder's last vote counts. `--json` gives the full
verdict for the Recorder.

## Limits, honestly

- The server runs on the owner's computer: Switch Console must be open for the agents to answer.
- The agents follow their instructions; the hard guarantees (who counts, when it's final)
  are only the ones `tally.py` enforces. Owner approval is a chat reply checked by the
  Recorder against the owner handle in the ballot.
- Deadlines are checked whenever someone votes or asks for status; there is no background timer yet.

## What's next
- A scheduled job that closes decisions exactly at their deadline.
- Weighted votes (e.g. the on-call engineer counts double for ops decisions).
- Linked rooms: a decision in `#decide` posts its record to the project room it affects.

## Built during the hackathon
Everything in this repository (template, agents, referee, tests, README) was written on
7 November 2026, inside the hackathon window. Switch, Switch Console and Claude Code are used
as provided. Built with AI assistance (Claude), as the rules allow.

## License
MIT
