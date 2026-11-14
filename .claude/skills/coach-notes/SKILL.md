---
name: coach-notes
description: Builds and maintains the topic knowledge base in career-coach/notes (DSA, system-design, OOPS, DB, AI, ...) with a concept note, reference links, a problem index and one file per attempted problem. Use for /coach-notes, "create notes for two pointers", "add this problem to my notes", or automatically at the end of /coach-review.
---

# /coach-notes new|log|index|revise  DOMAIN [TOPIC]

A personal study library the user builds by doing, not by reading. It is the user's memory aid, so it records the user's own thinking first and the reference answer last.

## Folder layout (under `career-coach/notes/`)
```
notes/
  README.md                      index of domains, topics, status counts (regenerate with `index`)
  DSA/
    two-pointers/
      README.md                  concept note (see template)
      problems.md                table of problems: link, difficulty, status, dates
      solutions/<slug>.md        one file per problem (see template)
  system-design/
    caching/
      README.md                  building-block note: when to use, when NOT to, trade-offs
      problems.md                design prompts and decision drills
      solutions/<slug>.md
  OOPS/   DB/   AI/   java/   cloud/    same shape; add a domain by creating its folder
```
Names are lowercase-kebab-case. Domain folders map to skill keys in `data/skills.json` (DSA=dsa, system-design=system_design, OOPS=lld, DB=sql_db, AI=ai_agents, java=java, cloud=cloud).

## `new DOMAIN TOPIC`
Create the topic folder with the three parts, never overwrite existing files.

**README.md template**
1. *What it is* (3-5 lines, plain words)
2. *Recognise it* (signals in a problem or requirement that point here)
3. *Template* (Java skeleton for DSA, decision checklist for system design, interface sketch for OOPS)
4. *Complexity / trade-offs* (cost, and when it is the WRONG choice)
5. *Common mistakes* (starts empty, filled from the user's own mistakes via `log`)
6. *References* (links; see rule below)

**problems.md template**: table `| # | Problem | Link | Difficulty | Status | First attempt | Revisit |`. Status is one of `todo`, `attempted`, `solved-alone`, `solved-with-hints`, `revealed`. Seed it with 8-12 well-known problems for the topic, ordered easy to hard, all `todo`.

**References rule (no invented facts)**: only put a URL in the file after it is verified with WebSearch/WebFetch; otherwise write the title plus `(link unverified)`. Prefer official docs, the original paper/RFC, or a recognised problem site. Never paste a solution into README.md.

## `log DOMAIN TOPIC PROBLEM`
Run after the user has attempted a problem (also called by `/coach-review`). Create `solutions/<slug>.md`:
```
# <Problem title>
Link: <url or "unverified"> | Difficulty: | Date: | Time spent: | Hints used: 0-3 | Revealed: no/yes

## My attempt (verbatim, untouched)
<the user's code or written answer exactly as submitted>

## Analysis of my attempt
<what was right, what was missing or wrong, which tier it reached; no fix shown>

## Hints I got (in order)
<the hints given, one line each, so I can see what unlocked it>

## Final solution (mine)
<the user's accepted solution, written in only after they reach it themselves>

## Reference solution
LOCKED until I finish my own solution or explicitly ask to reveal it.

## Mistake pattern and rule of thumb
<one line each>

## Variations to try later
<1-2 harder variants>
```
Then update that topic's `problems.md` row (status, dates, revisit date: +3 days, then +14, then +45 for spaced revision) and add any new mistake pattern to the topic README "Common mistakes".

## Reference-solution lock
- Write `Reference solution` content only when (a) the user's own solution passes, or (b) the user types "reveal" after the hint ladder has been offered. In case (b) set `Revealed: yes` and the attempt counts as a lookup (half credit) in `coach.py attempt --lookup`.
- Every reference solution shown or stored must have been run against the tests first (same rule as `/coach-review`).
- For system design and OOPS, the reference is a rubric-based model answer; the same lock applies.

## `index`
Regenerate `notes/README.md`: per domain, a topic list with counts of solved-alone / solved-with-hints / revealed / todo, and the list of problems whose revisit date is today or earlier (the user's revision queue).

## `revise`
Show today's revision queue from the problems tables. For each, give only the problem statement and ask the user to solve it again alone; on completion run `log` again (append a new dated attempt block, never replace the old one).

## Rules
- Notes record the user's thinking verbatim; never rewrite their attempt to look better.
- Never add a topic's reference solution during `new`.
- Keep each file short; the value is the user's own mistakes and rules of thumb, not copied theory.
