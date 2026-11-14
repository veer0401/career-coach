---
name: coach-set
description: Creates a practice question set for the user to solve on their own, with runnable hidden tests, sized to their current level and weak topics. Use for /coach-set, "give me questions on X", or when the user pastes their own questions to be turned into a tracked set.
---

# /coach-set [skill] [topic] [count] [difficulty]

The user solves alone first. Never include solutions, hints or approach names in anything the user can see.

## 1. Choose what to ask
- Run `python -I coach.py estimate` and `python -I coach.py status`. Read `data/practice.jsonl` titles so you never repeat a question.
- Skill: the user's choice, else the highest-priority skill from `status`. Count: 5 unless told otherwise.
- Difficulty (1 easy ... 5 hard; level 4 = interview-ready medium/hard): centre on the skill's practice-based level, `int(level + 0.5)`, clipped to 1-5. Mix: 1 warm-up (one below), 3 at level, 1 stretch (one above). Keep >=3 questions in the same tier so the estimate can use them.
- Read `data/learn_progress.json`: the user's "what tripped me up" notes and recalls per topic. Turn named mistakes into edge cases or questions.
- Topics: put at least 2 questions on topics marked WEAK in the estimate output, then fill with untested topics.
- If the user pasted their own questions, use those verbatim and assign skill/topic/difficulty.

## 2. Build a runnable set (coding questions)
Questions are stdin to stdout so any language works (Java by default, also Python/JS). For each question:
1. Write the statement, constraints, input/output format and 1-2 sample cases.
2. In the scratchpad (not in `practice/`), write a **brute-force** and an **optimal reference** solution. Check they agree on all samples, edge cases and 200+ random small inputs. Generate every `expected` output by running the reference, never by hand.
3. Tests: >=2 visible (the samples), >=5 hidden covering edge cases (empty/minimal, duplicates, negatives, overflow with `long`, max size). Add one **max-size test that the brute force cannot pass within `time_limit_s`**, so the runner separates simple from optimized solutions. Check the brute force really does time out and the optimal passes in well under the limit (also in Java).
4. Set `expected_minutes` from the difficulty (1:10, 2:20, 3:30, 4:45, 5:60).

## 3. Rubric questions (system_design, lld, java concepts, communication)
No tests. `"tests": []` plus `"rubric"`: 4-8 specific points a strong answer must hit (requirements, estimates, data model, trade-offs, failure modes...). Ask for a written answer in `practice/<set>/qN.md`.

## 4. Write the files
`practice/<YYYY-MM-DD>-<skill>-<n>/set.json`:
```json
{"id": "<set id>", "skill": "<skill key>", "created": "<date>", "questions": [
  {"id": "q1", "title": "...", "topic": "graphs", "difficulty": 3, "expected_minutes": 30, "time_limit_s": 5,
   "statement": "...", "input_format": "...", "output_format": "...",
   "tests": [{"input": "4 9\n2 7 11 15\n", "expected": "YES\n", "hidden": false}], "rubric": []}]}
```
**Hints and solutions (for the Practice page Hints tab):** every coding question also gets `"hints"`: exactly 3 strings (1 direction, 2 key insight, 3 skeleton/pseudocode with the core step left as `____`; none may contain the full answer), and `"solutions"`: 2-3 objects `{name, complexity, note, lang, code, verified}` in the order simplest, ideal, most optimized (skip the third if it would not be genuinely different). Run every solution with `python -I coach.py run SET qN --file <path>` first; `verified` records the pass count, and only a simplest solution may fail, and only by timing out on the large test (say so in `note`). The server keeps these locked: hints one at a time, solutions only after submit or after all hints plus an explicit give-up.

Create a starter file per question, `practice/<set>/q1.java` (class named `q1`, reads stdin) so the user only fills in logic. Rubric questions: an empty `qN.md` with the prompt.

## 5. Hand over
Show the questions (statement, formats, samples), the folder, and this routine, briefly:
- Solve alone first. If stuck, look it up, then solve it yourself in the file. That is fine, but say so when you report (it is scored as "with lookup", half credit).
- Check your own work any time: `python coach.py run <set> q1`
- When done with a question, tell me "done q1, 35 min" (and "looked up" if you did). I record it myself and review it.
Do not reveal tests, the reference, or how many hidden tests exist beyond "hidden tests include large inputs".
