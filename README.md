# career-coach

A local, private interview and career coach that runs on [Claude Code](https://claude.com/claude-code). It builds practice sets with hidden tests, makes you answer first, gives hints one rung at a time, times you on the server, and moves your skill levels only on evidence. A small local dashboard shows what to do today.

No API key and no cloud service of its own: Claude Code is the runtime, a Python standard-library server is the dashboard, and your progress is plain JSON files in `data/`.

Built for one specific failure mode: being great for 2-3 days and then stopping. Everything is designed around a tiny daily minimum (20 minutes counts as a win) and "never miss twice".

## What it does

**Today board.** One ordered list: continue a paused question, revisions due, an open weekly test, reading for this week's topic, the next unsolved practice question. Plus this week's counted days, the next deadline and days to your goal.

**Practice.** Question sets with runnable hidden tests (Java, Python, JavaScript; stdin to stdout).
- Every set is cross-checked: a brute force and an optimal reference agree on random inputs, and a max-size test makes the brute force time out, so only an efficient solution passes.
- In-browser editor with a server-side timer (survives closed tabs, pop-out always-on-top timer), pause reasons, idle time, tab switches.
- Hint ladder: hint 1, 2, 3, then solutions. Solutions unlock only after you submit or explicitly give up. Any hint counts as a lookup (half credit).
- Submitting records the attempt itself. Only your first attempt at a question counts toward your level.

**Learn.** A short reading list per topic, refreshed weekly by a web scan with sourced links. Mark links as read, close them, then write 3 lines from memory (active recall). Topics come back for a 5-minute revision after 3, 7 and 21 days. A "what tripped me up" note per topic feeds the next practice set.

**Weekly tests.** A 45-minute timed test from the week's topics: multiple choice (graded instantly, with explanations), short written answers (graded by the coach against a rubric), and coding questions with hints locked. Answers never reach the browser before you submit.

**Progress.** Counted-days heatmap, minutes per week, level per skill from test results, weakest topics first, practice-session patterns (where you get stuck, why you pause).

**Coach chat.** A chat page that runs Claude Code in this folder, with history.

**Plans with teeth.** Goals and weekly/monthly plans measured from logged work; missed items become debts; optional penalties you agree to in advance.

## Requirements
- [Claude Code](https://claude.com/claude-code) (logged in)
- Python 3.10+
- Java 17+ for Java practice (Python/Node optional for those languages)
- Windows, macOS or Linux (the optional reminder/backup scripts are PowerShell)

## Quick start
```bash
git clone https://github.com/veer0401/career-coach
cd career-coach
# 1. Tell it who you are: edit data/config.json (name, goal, goal_date, minutes)
# 2. Open the dashboard
python -I coach.py dashboard          # http://127.0.0.1:8765
# 3. In another terminal, start Claude Code in this folder
claude
/coach-verify dsa                     # honest starting level for one skill
/coach-set dsa arrays 5               # a practice set with hidden tests at your level
```
Solve in the Practice page, submit, then say `review q1` to the coach. An example set (`practice/example-dsa-basics`) and an example weekly test are included so you can try the pages straight away.

## Coach commands (Claude Code skills)
| Command | What it does |
|---|---|
| `/coach-set [skill] [topic] [n]` | Builds a question set with hidden tests, hints and verified solutions at your level |
| `/coach-review` | Analyses your attempt first, records it, then shows simplest / ideal / optimized solutions |
| `/coach-verify KEY` | Diagnostic quiz to set an honest level for one skill |
| `/coach-test build \| grade` | Builds the weekly test; grades written answers after you submit |
| `/coach-plan goals \| week \| month \| review` | Measurable goals and plans with fixed deadlines |
| `/coach-week` | Weekly review: stats, news, re-ranked weak areas, next week's plan and reading |
| `/coach-news` | Sourced market and tech news scan; adjusts skill weights |
| `/coach-notes` | Builds a notes library per topic from what you actually solved |

## How levels stay honest
| Signal | Source |
|---|---|
| Correct or not | Your code against hidden tests, including a large input where brute force times out |
| Lookup | Any hint or reveal; counts half credit |
| Pace | Time per question on the server timer (targets are recorded but not shown to you) |
| Level change | Only from >=5 first attempts, at most +1.0 / -0.5 per run |

## Layout
```
coach.py, planner.py      CLI: today, done, status, run, attempt, estimate, dashboard, plans
dashboard/                local web app (stdlib HTTP server + plain HTML/JS)
.claude/skills/           the coach's skills (Claude Code)
practice/<set>/set.json   question sets with tests, hints, solutions (your code: qN.java|py|js)
tests/<id>/test.json      weekly tests
data/                     your config, skills and progress (JSON / JSONL)
notes/                    notes library built from your attempts
scripts/                  optional: daily reminder, weekly review, nightly backup
```

## Privacy
Everything stays on your machine. The dashboard listens on 127.0.0.1 only and POSTs require a per-start token. The default `.gitignore` keeps your progress files and solutions out of git; if you back them up, use a private repository.

## Optional automation (Windows)
- `scripts/nudge.ps1`: a notification with today's minimum task, only if the day is not counted yet.
- `scripts/backup.ps1`: commit and push this folder to your own private remote.
- `scripts/weekly.ps1`: run `/coach-week` headless.

Schedule them with Task Scheduler, e.g. `schtasks /create /tn "CareerCoach Nudge" /tr "powershell -NoProfile -WindowStyle Hidden -File <path>\scripts\nudge.ps1" /sc daily /st 20:00`.

## License
MIT
