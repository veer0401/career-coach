"""Weekly tests: a fixed time box with theory questions (MCQ auto-graded, short answers graded by the coach)
plus coding questions that live in a normal practice set marked "mode": "test" (hints and Study are locked there).

  tests/<id>/test.json   written by the coach (/coach-test). Answers, explanations, rubrics never leave the
                         server before the user submits.
  data/test_runs.json    {id: {started, deadline, answers, submitted, result, review}}; the coach adds
                         "review": {qid: {"score": 0-1, "comment": str}} after grading short answers.
  data/tests.jsonl       one line per submitted test.
"""
import json
import re
import threading
from datetime import date, datetime, timedelta

import coach

TESTS = coach.ROOT / "tests"
RUNS_FILE = coach.DATA / "test_runs.json"
HISTORY = coach.DATA / "tests.jsonl"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")
GRACE_S = 120
MAX_ANSWER = 6000
LOCK = threading.Lock()


def _now():
    return datetime.now()


def _iso(d):
    return d.isoformat(timespec="seconds")


def _runs():
    try:
        return coach.load(RUNS_FILE) if RUNS_FILE.exists() else {}
    except ValueError:
        return {}


def _load(test_id):
    if not ID_RE.match(test_id or ""):
        raise ValueError("invalid test id")
    p = TESTS / test_id / "test.json"
    if not p.exists():
        raise ValueError("no such test")
    return coach.load(p)


def _coding_status(t, run):
    out = []
    started = run.get("started") if run else None
    for c in t.get("coding", []):
        att = [a for a in coach.read_attempts() if a["set"] == c["set"] and a["q"] == c["q"]]
        a = att[0] if att else None
        out.append({"set": c["set"], "q": c["q"], "title": c.get("title", c["q"]),
                    "submitted": bool(a), "result": a and a["result"], "tests": a and a.get("tests"),
                    "minutes": a and a.get("minutes"),
                    "in_window": bool(a and started and a["ts"] >= started[:19])})
    return out


def _status(t, run, today):
    if run and run.get("submitted"):
        return "done"
    if run and run.get("started"):
        return "running"
    return "open" if t.get("available_from", "") <= today.isoformat() else "locked"


def list_tests():
    runs, today, out = _runs(), date.today(), []
    if not TESTS.exists():
        return out
    for p in sorted(TESTS.glob("*/test.json"), reverse=True):
        t = coach.load(p)
        run = runs.get(t["id"])
        out.append({"id": t["id"], "title": t.get("title", t["id"]), "available_from": t.get("available_from"),
                    "duration_min": t.get("duration_min"), "topics": t.get("topics", []),
                    "n_theory": len(t.get("theory", [])), "n_coding": len(t.get("coding", [])),
                    "status": _status(t, run, today), "score": (run or {}).get("result", {}).get("summary")})
    return out


def view(test_id):
    t, run = _load(test_id), _runs().get(test_id) or {}
    status = _status(t, run, date.today())
    base = {k: t.get(k) for k in ("id", "title", "available_from", "duration_min", "topics", "rules")}
    base.update(status=status, n_theory=len(t.get("theory", [])), n_coding=len(t.get("coding", [])))
    if status == "locked":
        return base
    if status == "open":
        return base
    remaining = max(0, int((datetime.fromisoformat(run["deadline"]) - _now()).total_seconds()))
    base.update(started=run["started"], deadline=run["deadline"], remaining_s=remaining,
                answers=run.get("answers", {}), coding=_coding_status(t, run))
    if status == "running":
        base["theory"] = [{k: q.get(k) for k in ("id", "type", "topic", "prompt", "options")} for q in t.get("theory", [])]
        return base
    # done: full reveal, with grading
    base.update(submitted=run["submitted"], late=run.get("late", False), result=run.get("result"),
                review=run.get("review", {}), theory=t.get("theory", []))
    return base


def _grade(t, answers, review):
    mcq, short = [q for q in t.get("theory", []) if q["type"] == "mcq"], [q for q in t.get("theory", []) if q["type"] != "mcq"]
    right = sum(1 for q in mcq if str(answers.get(q["id"], "")) == str(q["answer"]))
    graded = [review[q["id"]]["score"] for q in short if q["id"] in review]
    return {"mcq_right": right, "mcq_total": len(mcq), "short_total": len(short), "short_graded": len(graded),
            "short_score": round(sum(graded), 2) if graded else None,
            "summary": f"MCQ {right}/{len(mcq)}" + (f" · written {round(sum(graded), 1)}/{len(short)}" if graded else
                                                     f" · {len(short)} written awaiting review" if short else "")}


def act(body):
    action, test_id = body.get("action"), body.get("id")
    t = _load(test_id)
    with LOCK:
        runs = _runs()
        run = runs.get(test_id) or {}
        status = _status(t, run, date.today())
        if action == "start":
            if status == "locked":
                raise ValueError(f"this test opens on {t.get('available_from')}")
            if status == "open":
                now = _now()
                run = runs[test_id] = {"started": _iso(now), "deadline": _iso(now + timedelta(minutes=t.get("duration_min", 45))),
                                       "answers": {}}
        elif action in ("save", "submit"):
            if status != "running":
                raise ValueError("start the test first" if status != "done" else "this test is already submitted")
            ids = {q["id"] for q in t.get("theory", [])}
            for k, v in (body.get("answers") or {}).items():
                if k in ids:
                    run["answers"][k] = str(v)[:MAX_ANSWER]
            if action == "submit":
                now = _now()
                deadline = datetime.fromisoformat(run["deadline"])
                run["submitted"] = _iso(now)
                run["late"] = (now - deadline).total_seconds() > GRACE_S
                run["result"] = _grade(t, run["answers"], run.get("review", {}))
                end = min(now, deadline)
                spent = max(0, round((end - datetime.fromisoformat(run["started"])).total_seconds() / 60))
                coding_min = sum(c["minutes"] or 0 for c in _coding_status(t, run) if c["in_window"])
                theory_min = max(0, spent - coding_min)
                if theory_min:
                    skill = t.get("skill") if t.get("skill") in coach.load(coach.SKILLS_FILE)["skills"] else "dsa"
                    coach.append_log({"date": date.today().isoformat(), "ts": _iso(now), "skill": skill,
                                      "minutes": theory_min, "what": f"test: {t.get('title', test_id)} (theory)",
                                      "proof": f"tests/{test_id}"})
                with HISTORY.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"date": date.today().isoformat(), "ts": _iso(now), "test": test_id,
                                        "minutes": spent, "late": run["late"], "result": run["result"],
                                        "answers": run["answers"], "coding": _coding_status(t, run)},
                                       ensure_ascii=False) + "\n")
        else:
            raise ValueError("unknown action")
        coach.save(RUNS_FILE, runs)
    return view(test_id)


def is_test_set(set_id):
    try:
        return coach.load(coach.SETS / set_id / "set.json").get("mode") == "test"
    except (OSError, ValueError):
        return False
