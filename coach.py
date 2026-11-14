#!/usr/bin/env python3
"""Career coach CLI: daily mission, check-ins, skill matrix, weekly summary.

Commands
  today            what to do now (tiny minimum + full version); adapts if you missed days
  done WHAT        log work: --skill KEY --min N [--proof URL_OR_NOTE]
  status           skill matrix: excellent / solid / improve / weak, plus consistency
  rate KEY LEVEL   change a skill level (needs --evidence)
  week [--json]    last-7-days summary (used by the /coach-week skill)
  skills           list skill keys
  run SET Q        run your solution (practice/SET/Q.java|py|js) against the question's tests
  attempt SET Q    record an attempt (re-runs tests itself): --minutes N [--lookup] [--approach X]
  estimate         practice-based level per skill and weak topics; --apply updates skills.json
  goal / plan / ledger / consequences   goals, weekly+monthly plans, strict deadlines, penalties (see planner.py)
  dashboard        open the local web dashboard (http://127.0.0.1:8765)
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))  # `python -I` does not add the script folder, and planner.py lives beside this file
DATA = ROOT / "data"
SKILLS_FILE = DATA / "skills.json"
CONFIG_FILE = DATA / "config.json"
LOG_FILE = DATA / "log.jsonl"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_log():
    if not LOG_FILE.exists():
        return []
    return [json.loads(line) for line in LOG_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_log(entry):
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def minutes_by_day(log):
    totals = defaultdict(int)
    for e in log:
        if e.get("minutes"):
            totals[e["date"]] += e["minutes"]
    return totals


def counted_days(log, cfg):
    return {d for d, m in minutes_by_day(log).items() if m >= cfg["min_minutes"]}


def run_length(days, today):
    """Consecutive counted days ending today, or yesterday if today is not done yet."""
    cursor = today if today.isoformat() in days else today - timedelta(days=1)
    n = 0
    while cursor.isoformat() in days:
        n += 1
        cursor -= timedelta(days=1)
    return n


def week_start(today):
    return today - timedelta(days=today.weekday())


def week_days(days, today):
    start = week_start(today)
    return sum(1 for i in range(7) if (start + timedelta(days=i)).isoformat() in days)


def days_since_last(days, today):
    if not days:
        return None
    return (today - max(date.fromisoformat(d) for d in days)).days


def recent_minutes(log, key, today, window=14):
    cutoff = (today - timedelta(days=window)).isoformat()
    return sum(e.get("minutes", 0) for e in log if e.get("skill") == key and e["date"] > cutoff)


def priority(key, s, log, today):
    gap = max(s["target"] - s["level"], 0)
    hours = recent_minutes(log, key, today) / 60
    return s["weight"] * gap / (1 + hours / 3)


def label(s):
    gap = s["target"] - s["level"]
    if gap <= 0:
        return "EXCELLENT"
    if gap <= 0.5:
        return "SOLID"
    if gap <= 1.5:
        return "IMPROVE"
    return "WEAK"


def ranked(skills, log, today):
    return sorted(skills, key=lambda k: priority(k, skills[k], log, today), reverse=True)


def cmd_today(args):
    cfg, skills, log = load(CONFIG_FILE), load(SKILLS_FILE)["skills"], read_log()
    today = date.today()
    days = counted_days(log, cfg)
    done_today = today.isoformat() in days
    since = days_since_last(days, today)
    top = ranked(skills, log, today)[0]
    s = skills[top]

    if args.short:
        print(f"Career coach: {s['name']} - {s['minimum']}")
        return

    print(f"== {today:%A %d %b} | week {week_days(days, today)}/{cfg['weekly_target_days']} days | run {run_length(days, today)} ==")
    if done_today:
        print("Today is already counted. Anything more is a bonus.\n")
    elif since is None:
        print("Fresh start. One small win today beats a perfect plan.\n")
    elif since >= 2:
        print(f"COMEBACK MODE: {since} days since your last counted day.")
        print(f"Do only {cfg['comeback_minutes']} minutes. Restarting matters more than catching up. Do not 'make up' missed days.\n")
    elif since == 1:
        print("You missed yesterday. Rule: never miss twice. Do the minimum today.\n")
    else:
        print("Run is alive. Protect it.\n")

    import planner
    planner.today_block()
    print(f"Focus skill : {s['name']} (level {s['level']} -> target {s['target']}, {label(s)})")
    mins = cfg["comeback_minutes"] if (since or 0) >= 2 else cfg["min_minutes"]
    print(f"MINIMUM ({mins} min, counts as a win): {s['minimum']}")
    print(f"If you have energy (60-90 min): {s['deep']}")
    print(f"\nWhen done: python coach.py done \"what you did\" --skill {top} --min {mins}")


def cmd_done(args):
    cfg, skills = load(CONFIG_FILE), load(SKILLS_FILE)["skills"]
    if args.skill not in skills:
        sys.exit(f"Unknown skill '{args.skill}'. Run: python coach.py skills")
    append_log({
        "date": date.today().isoformat(),
        "ts": datetime.now().isoformat(timespec="seconds"),
        "skill": args.skill,
        "minutes": args.min,
        "what": args.what,
        "proof": args.proof or "",
    })
    log = read_log()
    days = counted_days(log, cfg)
    today = date.today()
    total = minutes_by_day(log)[today.isoformat()]
    print(f"Logged {args.min} min on {skills[args.skill]['name']} (today: {total} min).")
    if total >= cfg["min_minutes"]:
        print(f"Day counted. Run: {run_length(days, today)} | This week: {week_days(days, today)}/{cfg['weekly_target_days']}")
    else:
        print(f"{cfg['min_minutes'] - total} more minutes to count today.")


def cmd_status(args):
    cfg, skills, log = load(CONFIG_FILE), load(SKILLS_FILE)["skills"], read_log()
    today = date.today()
    days = counted_days(log, cfg)
    print(f"Goal: {cfg['goal']} by {cfg['goal_date']}")
    print(f"Run {run_length(days, today)} days | this week {week_days(days, today)}/{cfg['weekly_target_days']} | "
          f"counted days total {len(days)}\n")
    print(f"{'SKILL':38}{'LVL':>5}{'TGT':>5}  {'STATUS':10}{'14d MIN':>8}  CONF")
    for k in ranked(skills, log, today):
        s = skills[k]
        print(f"{s['name'][:37]:38}{s['level']:>5}{s['target']:>5}  {label(s):10}{recent_minutes(log, k, today):>8}  {s['confidence']}")
    print("\nSorted by priority (weight x gap, discounted by recent effort). Low confidence = unverified, test it with /coach-verify.")


def cmd_rate(args):
    data = load(SKILLS_FILE)
    if args.key not in data["skills"]:
        sys.exit(f"Unknown skill '{args.key}'.")
    if not 0 <= args.level <= 5:
        sys.exit("Level must be between 0 and 5.")
    s = data["skills"][args.key]
    old = s["level"]
    s["level"] = args.level
    s["confidence"] = args.confidence or s["confidence"]
    s["evidence"] = args.evidence
    s.setdefault("history", []).append({"date": date.today().isoformat(), "from": old, "to": args.level, "evidence": args.evidence})
    save(SKILLS_FILE, data)
    print(f"{s['name']}: {old} -> {args.level} ({s['confidence']} confidence)")


def cmd_week(args):
    cfg, skills, log = load(CONFIG_FILE), load(SKILLS_FILE)["skills"], read_log()
    today = date.today()
    cutoff = (today - timedelta(days=7)).isoformat()
    recent = [e for e in log if e["date"] > cutoff]
    by_skill = defaultdict(int)
    for e in recent:
        by_skill[e.get("skill", "?")] += e.get("minutes", 0)
    days = counted_days(log, cfg)
    last7 = sum(1 for i in range(7) if (today - timedelta(days=i)).isoformat() in days)
    neglected = [k for k in ranked(skills, log, today)[:6] if by_skill.get(k, 0) == 0]
    out = {
        "date": today.isoformat(),
        "counted_days_last7": last7,
        "target_days": cfg["weekly_target_days"],
        "run": run_length(days, today),
        "total_minutes": sum(by_skill.values()),
        "minutes_by_skill": dict(by_skill),
        "proofs": [{"date": e["date"], "skill": e["skill"], "what": e["what"], "proof": e["proof"]} for e in recent if e.get("proof")],
        "entries": [{"date": e["date"], "skill": e["skill"], "min": e["minutes"], "what": e["what"]} for e in recent],
        "top_priority_untouched": neglected,
        "skills": {k: {"level": s["level"], "target": s["target"], "status": label(s), "confidence": s["confidence"]} for k, s in skills.items()},
    }
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    print(f"Last 7 days: {last7}/{cfg['weekly_target_days']} counted days, {out['total_minutes']} min, run {out['run']}")
    for k, m in sorted(by_skill.items(), key=lambda kv: -kv[1]):
        print(f"  {k:16}{m:>5} min")
    if neglected:
        print("High-priority skills with zero time this week: " + ", ".join(neglected))


# ---------- practice: run solutions, record attempts, estimate levels ----------

PRACTICE_FILE = DATA / "practice.jsonl"
SETS = ROOT / "practice"
RUNNERS = {".py": [sys.executable], ".java": ["java"], ".js": ["node"]}
SCORE = {"solved": 1.0, "solved-with-lookup": 0.5, "partial": 0.25, "unsolved": 0.0}
EXPECTED_MIN = {1: 10, 2: 20, 3: 30, 4: 45, 5: 60}
MIN_ATTEMPTS_TO_APPLY = 5


def read_attempts():
    if not PRACTICE_FILE.exists():
        return []
    return [json.loads(l) for l in PRACTICE_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]


def first_attempts(attempts):
    """Only the first try at each question counts toward the estimate; retries are practice."""
    seen, out = set(), []
    for a in attempts:
        k = (a["set"], a["q"])
        if k not in seen:
            seen.add(k)
            out.append(a)
    return out


def attempt_score(a):
    s = SCORE[a["result"]]
    if a["result"] == "solved" and a["minutes"] > 1.5 * EXPECTED_MIN[a["difficulty"]]:
        s = 0.75  # correct but slow
    return s


def estimate_skill(att):
    """Level from per-difficulty results: tier d solved at rate m counts as level d-1+m,
    but only with >=3 attempts in the tier and m >= 0.5."""
    tiers = defaultdict(list)
    for a in att[-40:]:
        tiers[a["difficulty"]].append(attempt_score(a))
    best, table = None, {}
    for d, sc in sorted(tiers.items()):
        m = sum(sc) / len(sc)
        table[d] = {"n": len(sc), "rate": round(m, 2)}
        if len(sc) >= 3 and m >= 0.5:
            best = max(best if best is not None else 0, d - 1 + m)
    return {"n": len(att), "level": round(best * 2) / 2 if best is not None else None, "tiers": table}


def topic_stats(first):
    groups = defaultdict(list)
    for a in first:
        groups[(a["skill"], a.get("topic", "general"))].append(a)
    rows = []
    for (skill, topic), items in groups.items():
        rate = sum(attempt_score(a) for a in items) / len(items)
        avg_min = sum(a["minutes"] for a in items) / len(items)
        status = "WEAK" if len(items) >= 2 and rate < 0.5 else "STRONG" if len(items) >= 2 and rate >= 0.8 else "OK"
        rows.append({"skill": skill, "topic": topic, "n": len(items), "rate": round(rate, 2), "avg_min": round(avg_min), "status": status})
    return sorted(rows, key=lambda r: (r["rate"], -r["n"]))


def practice_summary(skills):
    first = first_attempts(read_attempts())
    out = []
    for k, s in skills.items():
        att = [a for a in first if a["skill"] == k]
        if not att:
            continue
        est = estimate_skill(att)
        base = est["level"] if est["level"] is not None else s["level"]
        out.append({"key": k, "name": s["name"], "n": est["n"], "estimate": est["level"], "level": s["level"],
                    "tiers": est["tiers"], "recommended_difficulty": max(1, min(5, int(base + 0.5)))})
    return out


def load_question(set_id, qid):
    p = SETS / set_id / "set.json"
    if not p.exists():
        sys.exit(f"No such set: {p}")
    qid = qid if qid.startswith("q") else f"q{qid}"
    for q in load(p)["questions"]:
        if q["id"] == qid:
            return load(p), q
    sys.exit(f"No question '{qid}' in set {set_id}")


def find_solution(set_id, qid, explicit=None):
    if explicit:
        return Path(explicit).resolve()
    qid = qid if qid.startswith("q") else f"q{qid}"
    files = [f for f in sorted((SETS / set_id).glob(f"{qid}.*")) if f.suffix in RUNNERS]
    if not files:
        sys.exit(f"No solution file found: put your code in practice/{set_id}/{qid}.java (or .py/.js)")
    if len(files) > 1:
        sys.exit(f"Several solution files for {qid}: {[f.name for f in files]}. Pass --file to choose one.")
    return files[0]


def run_tests(q, path):
    import subprocess
    import time
    cmd = RUNNERS.get(path.suffix)
    if not cmd:
        sys.exit(f"Unsupported file type {path.suffix}; supported: {', '.join(RUNNERS)}")
    limit = q.get("time_limit_s", 5)
    failures, passed, max_ms = [], 0, 0
    for i, t in enumerate(q["tests"], 1):
        t0 = time.perf_counter()
        got, err, ok = "", "", False
        try:
            r = subprocess.run(cmd + [str(path)], input=t["input"], capture_output=True, text=True, timeout=limit)
            got, err = r.stdout, r.stderr
            ok = r.returncode == 0 and got.split() == t["expected"].split()
            if r.returncode != 0:
                err = err.strip()[-400:] or f"exit code {r.returncode}"
        except subprocess.TimeoutExpired:
            err = f"time limit exceeded ({limit}s)"
        except FileNotFoundError:
            sys.exit(f"Runtime '{cmd[0]}' not found on PATH.")
        max_ms = max(max_ms, int((time.perf_counter() - t0) * 1000))
        if ok:
            passed += 1
        else:
            failures.append({"index": i, "hidden": bool(t.get("hidden")), "input": t["input"][:300],
                             "expected": t["expected"][:200], "got": got[:200], "error": err})
    return {"passed": passed, "total": len(q["tests"]), "max_ms": max_ms, "failures": failures}


def cmd_run(args):
    _, q = load_question(args.set, args.q)
    if not q.get("tests"):
        sys.exit("This question has no runnable tests (rubric-graded). Ask the coach to review it.")
    path = find_solution(args.set, args.q, args.file)
    res = run_tests(q, path)
    print(f"{q['title']}: {res['passed']}/{res['total']} tests passed (slowest {res['max_ms']} ms)")
    for f in res["failures"][:3]:
        if f["hidden"]:
            print(f"  hidden test #{f['index']} failed" + (f": {f['error']}" if f["error"] else ""))
        else:
            print(f"  test #{f['index']} failed\n    input:    {f['input']!r}\n    expected: {f['expected']!r}\n    got:      {f['got']!r}" +
                  (f"\n    error:    {f['error']}" if f["error"] else ""))
    if args.json:
        print(json.dumps(res))


def cmd_attempt(args):
    import shutil
    sets_data, q = load_question(args.set, args.q)
    skills = load(SKILLS_FILE)["skills"]
    skill = sets_data.get("skill", q.get("skill"))
    if skill not in skills:
        sys.exit(f"Set has unknown skill '{skill}'.")
    tests_str, max_ms, path = "", 0, None
    if q.get("tests"):
        path = find_solution(args.set, args.q, args.file)
        res = run_tests(q, path)
        ratio, tests_str, max_ms = res["passed"] / res["total"], f"{res['passed']}/{res['total']}", res["max_ms"]
    else:
        if args.score is None:
            sys.exit("Rubric-graded question: pass --score 0..1 (the coach's grade against the rubric).")
        ratio = args.score
    if ratio >= (1.0 if q.get("tests") else 0.8):
        result = "solved-with-lookup" if args.lookup else "solved"
    elif ratio >= 0.5 or (not q.get("tests") and ratio >= 0.4):
        result = "partial"
    else:
        result = "unsolved"
    now = datetime.now()
    entry = {"date": now.date().isoformat(), "ts": now.isoformat(timespec="seconds"), "set": args.set, "q": q["id"],
             "title": q["title"], "skill": skill, "topic": q.get("topic", "general"), "difficulty": q["difficulty"],
             "minutes": args.minutes, "result": result, "lookup": args.lookup, "approach": args.approach,
             "tests": tests_str, "max_ms": max_ms, "notes": args.notes or ""}
    PRACTICE_FILE.parent.mkdir(exist_ok=True)
    with PRACTICE_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    if path:
        dest = SETS / args.set / "attempts"
        dest.mkdir(exist_ok=True)
        shutil.copy(path, dest / f"{q['id']}-{now:%Y%m%d-%H%M%S}{path.suffix}")
    append_log({"date": entry["date"], "ts": entry["ts"], "skill": skill, "minutes": args.minutes,
                "what": f"Practice: {q['title']} ({result})", "proof": f"practice/{args.set}"})
    first = [a for a in first_attempts(read_attempts()) if a["skill"] == skill]
    est = estimate_skill(first)
    print(f"{q['title']} [{q['topic'] if 'topic' in q else 'general'}, difficulty {q['difficulty']}]: {result.upper()}"
          + (f" (tests {tests_str}, slowest {max_ms} ms)" if tests_str else "") + f", {args.minutes} min")
    prior = len([a for a in read_attempts() if (a["set"], a["q"]) == (args.set, q["id"])])
    if prior > 1:
        print("Retry: recorded as practice, but it does not change your estimate (first attempt counts).")
    print(f"{skills[skill]['name']}: {est['n']} scored attempts, practice-based level "
          + (str(est["level"]) if est["level"] is not None else "not enough data yet (needs 3 attempts in one difficulty tier)"))


def cmd_estimate(args):
    data = load(SKILLS_FILE)
    skills = data["skills"]
    first = first_attempts(read_attempts())
    if not first:
        print("No practice attempts yet. Ask the coach for a set with /coach-set.")
        return
    changed = False
    for k, s in skills.items():
        att = [a for a in first if a["skill"] == k]
        if not att:
            continue
        est = estimate_skill(att)
        tiers = ", ".join(f"d{d}: {v['rate']:.0%} of {v['n']}" for d, v in est["tiers"].items())
        shown = est["level"] if est["level"] is not None else "n/a"
        print(f"{s['name']}: practice level {shown} (current {s['level']}) | {est['n']} attempts | {tiers}")
        if args.apply and est["level"] is not None and est["n"] >= MIN_ATTEMPTS_TO_APPLY:
            new = round((s["level"] + max(-0.5, min(1.0, est["level"] - s["level"]))) * 2) / 2
            if new != s["level"]:
                evidence = f"Auto-estimate from {est['n']} first-attempt practice results ({tiers})"
                s.setdefault("history", []).append({"date": date.today().isoformat(), "from": s["level"], "to": new, "evidence": evidence})
                print(f"  -> level {s['level']} to {new}")
                s["level"], s["evidence"], changed = new, evidence, True
            s["confidence"] = "high" if est["n"] >= 20 else "medium"
            changed = True
    topics = topic_stats(first)
    print("\nTopics (first attempts): weakest first")
    for t in topics[:10]:
        print(f"  {t['skill']:14}{t['topic']:20}{t['status']:7}{t['rate']:>5.0%} of {t['n']}, avg {t['avg_min']} min")
    if changed:
        save(SKILLS_FILE, data)
    elif args.apply:
        print("\nNo level changes (need >=5 attempts and >=3 in one tier).")


def cmd_dashboard(args):
    sys.path.insert(0, str(ROOT / "dashboard"))
    import server
    server.serve(args.port, not args.no_open)


def cmd_skills(_args):
    for k, s in load(SKILLS_FILE)["skills"].items():
        print(f"{k:16}{s['name']}")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if len(sys.argv) > 1 and sys.argv[1] in ("goal", "plan", "ledger", "consequences"):
        import planner
        planner.main(sys.argv[1], sys.argv[2:])
        return
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("today"); t.add_argument("--short", action="store_true"); t.set_defaults(fn=cmd_today)
    d = sub.add_parser("done")
    d.add_argument("what"); d.add_argument("--skill", required=True); d.add_argument("--min", type=int, required=True)
    d.add_argument("--proof"); d.set_defaults(fn=cmd_done)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    r = sub.add_parser("rate")
    r.add_argument("key"); r.add_argument("level", type=float); r.add_argument("--evidence", required=True)
    r.add_argument("--confidence", choices=["low", "medium", "high"]); r.set_defaults(fn=cmd_rate)
    w = sub.add_parser("week"); w.add_argument("--json", action="store_true"); w.set_defaults(fn=cmd_week)
    sub.add_parser("skills").set_defaults(fn=cmd_skills)
    ru = sub.add_parser("run"); ru.add_argument("set"); ru.add_argument("q"); ru.add_argument("--file")
    ru.add_argument("--json", action="store_true"); ru.set_defaults(fn=cmd_run)
    at = sub.add_parser("attempt"); at.add_argument("set"); at.add_argument("q")
    at.add_argument("--minutes", type=int, required=True); at.add_argument("--lookup", action="store_true")
    at.add_argument("--approach", choices=["none", "brute", "ideal", "optimal"], default="none")
    at.add_argument("--score", type=float); at.add_argument("--notes"); at.add_argument("--file")
    at.set_defaults(fn=cmd_attempt)
    es = sub.add_parser("estimate"); es.add_argument("--apply", action="store_true"); es.set_defaults(fn=cmd_estimate)
    b = sub.add_parser("dashboard"); b.add_argument("--port", type=int, default=8765)
    b.add_argument("--no-open", action="store_true"); b.set_defaults(fn=cmd_dashboard)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
