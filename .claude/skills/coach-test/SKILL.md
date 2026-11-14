---
name: coach-test
description: Builds the weekly timed test (theory MCQ + short answers + coding questions with hidden tests) from what the user practised that week, and grades the written answers after they submit. Use for /coach-test build|grade, "make this week's test", "grade my test".
---

# /coach-test build | grade

Weekly test = spaced retrieval: what the user can still do days after practising, with no hints. It runs on the dashboard Tests page (`/test`).

## build (Saturday, for Sunday)
1. Read the week: `data/practice.jsonl` (topics, results, lookups), `data/learn_progress.json` (recalls and the "what tripped me up" notes), `data/resources.json` (this week's topics), previous `data/tests.jsonl` (repeat what was missed last time).
2. Write `tests/<YYYY-MM-DD>-week-<n>/test.json` (date = the day it opens). If a test for that day already exists (e.g. theory-only), add to it instead of replacing it.
   ```json
   {"id": "...", "title": "Week n test", "skill": "dsa", "created": "<today>", "available_from": "<test day>",
    "duration_min": 45, "topics": ["..."], "rules": ["..."],
    "theory": [{"id": "t1", "type": "mcq", "topic": "...", "prompt": "...", "options": ["..."], "answer": 1, "explain": "..."},
               {"id": "t7", "type": "short", "topic": "...", "prompt": "...", "rubric": ["..."], "model": "..."}],
    "coding": [{"set": "<test set id>", "q": "q1", "title": "..."}]}
   ```
   - About 6 MCQ + 2 short + 2 coding for 45 minutes. Weight toward topics that were WEAK, solved with lookup, or named in the user's notes.
   - MCQ: one clearly correct option, plausible wrong options taken from real mistakes; `explain` says why the right one is right and why the tempting wrong one is wrong. If a claim is checkable by code (complexity, overflow, Java API behaviour), run it.
   - Short answers: 4-6 rubric points and a model answer of 3-6 lines.
   - Never reuse a question the user already solved; write new ones on the same pattern.
3. Coding questions: build a normal set with `/coach-set` rules (brute vs optimal cross-check, hidden tests, a max-size test that the brute force times out on, verified with `python -I coach.py run`) in `practice/<date>-test-<n>/set.json`, with `"mode": "test"` at the top level. In test mode the Practice page hides Study and Hints and the server refuses hints until submit. No `study` block.
4. Answers, explanations, rubrics and models never reach the browser before submit (the server strips them). Do not mention them in chat either.
5. Hand over: the date it opens, duration, topics, question counts. Do not reveal questions. Do not show target minutes.

## grade (after the user submits)
1. Read `data/test_runs.json[<id>]` (answers, result) and the test file.
2. For each `short` question: score 0, 0.5 or 1 against the rubric, with a one-line comment naming the missing rubric point. Write `data/test_runs.json[<id>]["review"] = {"t7": {"score": 0.5, "comment": "..."}}`, then recompute `result` with `exam._grade(test, answers, review)` (import from `dashboard/`) so the page shows the written score.
3. Coding results come from the practice attempts (first attempt counts toward the estimate, as usual).
4. Reply: score per section, the 2-3 concepts that did not stick, and put those topics back into next week's set and `data/resources.json` (status `now`). Never shame a low score; a test that shows gaps is doing its job.
