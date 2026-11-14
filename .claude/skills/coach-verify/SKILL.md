---
name: coach-verify
description: Diagnostic quiz that sets an honest level for one skill in the career-coach matrix. Use when the user runs /coach-verify <skill key> or wants their skills cross-checked.
---

# /coach-verify KEY

1. Run `python -I coach.py skills` if no key was given and ask which to test (default: the highest-priority `low` confidence skill from `python -I coach.py status`).
2. Read that skill's entry in `data/skills.json` (`target_bar`, `evidence`).
3. Ask **6 questions, one at a time**, rising from level-2 to level-4 difficulty and tied to the `target_bar` and to the user's own projects (ask for them if unknown). Do not reveal answers until they respond. For coding skills (dsa, lld), give one timed problem instead of some questions.
4. After each answer, grade in one line: correct / partial / wrong, plus the missing point.
5. Score: 0-1 right = level 1.5-2, 2-3 = 2.5-3, 4 = 3.5, 5-6 with depth and trade-offs = 4. Be strict.
6. Record: `python -I coach.py rate KEY LEVEL --confidence medium --evidence "<quiz date, score, main gaps>"`. A quiz gives at most `medium` confidence; `high` needs real shipped work.
7. End with the 2 topics to study next and one `python -I coach.py done` command to log the quiz (use `--min` for the actual time).
