---
name: coach-review
description: Reviews a solved (or given-up) practice question, records the attempt automatically, shows 2-3 solution approaches (simplest, ideal, most optimized), and updates progress and level estimates. Use for /coach-review, or when the user says "done q1", "solved it", "I looked it up", or "review my answer".
---

# /coach-review SET QUESTION  (or: "done q2, 35 min")

The user never has to enter progress commands. You run them. Record first, teach second.

## 1. Gather facts
- Identify set and question (default: the most recent set in `practice/`, the question named).
- Minutes and whether they looked anything up: use what the user said. If missing, ask one short question ("how long, and did you look it up?"). Do not guess.
- Read their solution (`practice/<set>/qN.*`).

## 2. Record the attempt (objective)
- **Submitted from the web Practice page?** Check the last lines of `data/practice_sessions.jsonl` for this set/question. If present, the attempt is ALREADY recorded (do not run `attempt` again; that would count as a retry). Use that record instead of asking: active minutes, `over_expected`/`over_ratio`, pauses and reasons, `away_s`, `run_count`, `compile_errors`, `first_run_s`/`first_pass_s`, the user's `stuck` areas, `confidence`, `felt_difficulty`, `note`, `lookup`, plus focus data: `idle_pct`/`idle_spans` (60s+ with no input, usually thinking), `switches` (tab switches), `aways` (time away with the reason the user gave). Mention the 1-2 most telling numbers in the analysis (for example "6 runs, 3 compile errors: Java syntax is costing you time, not the logic"). Then continue at step 3.
- Coding: `python -I coach.py attempt SET QN --minutes M [--lookup] --approach none|brute|ideal|optimal --notes "<one-line mistake pattern, if any>"`. The command re-runs the tests itself, so the result comes from the code, not from the user's word. `--approach` is which tier their solution actually is (judge from the code and which hidden tests it passes).
- Rubric question: grade the written answer against `rubric` (fraction of points hit, strictly), then `... attempt SET QN --minutes M --score S [--lookup] --notes "..."`.
- If tests fail: first show `python -I coach.py run SET QN` output, point at the bug class (not the fixed code) and let them retry. If they say they gave up, record it as unsolved/partial honestly and continue to step 3.

## 3. Analyse first, then hints, never the answer first
The user's own answer always comes before anything from you. Walk this ladder one rung at a time and stop as soon as they solve it:
1. **Analysis of their answer**: what is right, what is wrong or missing, which tier it reached. No fix, no corrected code.
2. **Hint 1, direction**: a question that points at the pattern family or the failing case ("what happens when the array has duplicates?").
3. **Hint 2, key insight**: the central idea phrased as a question, still no code.
4. **Hint 3, skeleton**: outline or pseudocode with the core step left blank.
5. **Reveal**: only when the user explicitly says "reveal" (or gives up) after being offered the ladder. Then go to step 3b.
After each hint, wait for the user's next attempt. Count hints used. If the user needed a hint or reveal, pass `--lookup` to `coach.py attempt` (half credit).
For system design and OOPS (rubric questions) the ladder is: gaps against the rubric as questions ("what happens when this cache node dies?"), then the missing rubric area named without its answer, then a partial outline, then the model answer on reveal.

## 3b. Show 2-3 ways (only after the user finished their own solution, or revealed)
Verify **every** solution you show: save it in the scratchpad and run `python -I coach.py run SET QN --file <path>` (it must pass all tests; the simplest one may legitimately time out on the big test, and say so). Never show code you have not run.

1. **Simplest**: the most direct, easiest-to-write solution. Code, time/space complexity, and where it breaks (the input size at which it fails).
2. **Ideal**: what a strong interview answer looks like: clean, correct, the expected pattern/data structure, well-named, edge cases handled. Code, complexity, the one key insight, the pattern name to remember.
3. **Most optimized**: the best known asymptotic or practical approach (less memory, better constants, streaming, bit tricks, specialised structure). Code, complexity, trade-offs, and whether it is worth writing in an interview. If the ideal solution already is the optimum, say so plainly and give the best genuine variant instead (for example a space-optimized form), or skip it. Do not invent a third way.

For rubric questions the three ways are: **basic** (works on one machine), **ideal** (production-grade, what interviewers expect), **at scale** (what changes at 100x load or in failure scenarios), each with the concrete trade-offs.

## 4. Compare with their answer
- Which tier they reached, with the single most important thing they missed or did well.
- The mistake pattern to avoid next time, one line (this also goes in `--notes`).
- One follow-up question to cement it (a variation one step harder) and offer to add it to the next set.

## 4b. Save to the notes library
Run `/coach-notes log DOMAIN TOPIC PROBLEM` so the attempt, analysis, hints used and mistake pattern are stored in `notes/`. The reference solution stays LOCKED unless step 3 reached a reveal or the user finished their own.

## 5. Update progress
After the last question of a set (or any time asked), run `python -I coach.py estimate --apply` and report in at most 5 lines: the skill's practice-based level and any change, weakest topic now, solved-independent rate, and the recommended difficulty for the next set. State plainly when there is not yet enough data (needs >=5 attempts and >=3 in one difficulty tier) instead of implying a level.
