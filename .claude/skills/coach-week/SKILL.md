---
name: coach-week
description: Weekly review for career-coach that reads check-ins, refreshes market news, re-ranks weak areas, and writes next week's plan. Use for /coach-week, or on the weekly schedule.
---

# /coach-week

1. Run `python -I coach.py week --json` and `python -I coach.py status`.
2. Run the `/coach-news` steps (or read `data/market.md` if it is under 3 days old).
3. Judge the week honestly:
   - **Consistency**: counted days vs target. If under target, diagnose from the log which weekday broke and why it likely did (tasks too big, no fixed slot, energy after work). Fix the system, not the person: shrink the minimum, move the slot, attach it to an existing habit.
   - **Output**: proofs logged (solved sets, commits, posts). Minutes without proof is weak evidence.
   - **Neglect**: top-priority skills with zero minutes (`top_priority_untouched`).
4. Verdict table: **Excellent** (at or above target, keep warm), **Improve**, **Weak** (largest weight x gap), with the one-line reason for each.
5. If there is real evidence for a level change (proof in the log), apply it with `python -I coach.py rate`. Otherwise leave levels alone and say which `/coach-verify` quiz would settle it.
6. Next week's plan, 5 days: one skill per day from the priority order, each with the `minimum` task and an optional `deep` task, with 2 days on interview gates (dsa, system_design). Add one shippable proof target for the week (a repo, a write-up, a solved set).
6b. Refresh `data/resources.json` (the dashboard Learn tab) for next week's plan, so links arrive a topic at a time:
   - Topics in next week's plan get `"status": "now"` (at most 3); topics finished this week become `"done"`; likely topics for the week after stay `"next"` with titles only.
   - For each `now` topic with fewer than 3 links, WebSearch (standard mode, run searches in one turn) for free, beginner-to-medium reading on exactly that topic. Keep 2-4 links, each with `title`, `url` from a search result (never invented), `kind` (read/reference/video/course), `minutes`, a one-line `note`. Prefer official docs and well-known guides; mark vendor or paid pages as such.
   - Links teach the pattern only: never link a solution to a question in the user's current set.
   - Set `week_of` (next Monday) and `updated` (today).
6c. Weekly test: if a test was submitted this week, include its score and run `/coach-test grade` if written answers are ungraded. Build next week's test with `/coach-test build` (opens on the user's test day).
7. Write the report to `data/weekly/<today>.md` (create the folder): stats, verdicts, news that matters, next-week plan, and the single biggest risk to consistency.
8. Reply with a short summary (under 15 lines) and the path to the report. Tone: direct and warm, never shaming.
