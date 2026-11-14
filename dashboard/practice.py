"""Practice engine for the dashboard: server-side timers, code files, test runs, submit + reflection.

State that must survive closed tabs lives on disk:
  data/sessions.json            open sessions keyed "SET/qN" (timer segments, pauses, runs, away time)
  data/practice_sessions.jsonl  one line per submitted session (the full timing + self-report record)
The attempt itself is recorded through coach.cmd_attempt, so practice.jsonl and log.jsonl update as usual.
"""
import contextlib
import io
import json
import math
import re
import threading
from argparse import Namespace
from datetime import datetime

import coach
import exam

SESSIONS_FILE = coach.DATA / "sessions.json"
HISTORY_FILE = coach.DATA / "practice_sessions.jsonl"
SET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")
Q_RE = re.compile(r"^q\d{1,3}$")
LANGS = {"java": ".java", "py": ".py", "js": ".js"}
STUCK = ["understanding", "approach", "syntax-io", "edge-cases", "complexity", "debugging", "nothing"]
PAUSE_REASONS = ["break", "distracted", "stuck-thinking", "work", "other"]
AWAY_REASONS = ["docs-lookup", "thinking-on-paper", "distracted", "break", "other"]
MAX_CODE = 200_000
LOCK = threading.Lock()


def now():
    return datetime.now().isoformat(timespec="seconds")


def _ts(s):
    return datetime.fromisoformat(s)


def check_ids(set_id, qid):
    if not SET_RE.match(set_id or "") or not Q_RE.match(qid or ""):
        raise ValueError("invalid set or question id")
    if not (coach.SETS / set_id / "set.json").exists():
        raise ValueError(f"no such set: {set_id}")


def _load_sessions():
    return coach.load(SESSIONS_FILE) if SESSIONS_FILE.exists() else {}


def _save_sessions(s):
    coach.save(SESSIONS_FILE, s)


def elapsed_s(sess, at=None):
    at = at or datetime.now()
    total = 0.0
    for seg in sess["segments"]:
        end = _ts(seg["end"]) if seg.get("end") else at
        total += max(0.0, (end - _ts(seg["start"])).total_seconds())
    return int(total)


def public_session(sess):
    if not sess:
        return None
    out = {k: sess[k] for k in ("set", "q", "state", "created", "expected_minutes", "pauses", "runs", "away_s", "lang")}
    out.update({k: sess.get(k, 0) for k in ("idle_s", "keys", "switches")})
    out["hints_used"] = sorted({h["level"] for h in sess.get("hints", [])})
    out["revealed"] = bool(sess.get("revealed"))
    out["elapsed_s"] = elapsed_s(sess)
    return out


# ---------- read ----------
def list_sets():
    done = {(a["set"], a["q"]) for a in coach.read_attempts()}
    sessions = _load_sessions()
    out = []
    for p in sorted(coach.SETS.glob("*/set.json"), reverse=True):
        data = coach.load(p)
        qs = []
        for q in data["questions"]:
            sess = sessions.get(f"{data['id']}/{q['id']}")
            qs.append({"id": q["id"], "title": q["title"], "topic": q.get("topic", ""), "difficulty": q["difficulty"],
                       "expected_minutes": q.get("expected_minutes"), "submitted": (data["id"], q["id"]) in done,
                       "session": sess["state"] if sess else None})
        out.append({"id": data["id"], "skill": data.get("skill"), "created": data.get("created"), "mode": data.get("mode"), "questions": qs})
    return out


def question(set_id, qid):
    check_ids(set_id, qid)
    _, q = coach.load_question(set_id, qid)
    visible = [{"input": t["input"], "expected": t["expected"]} for t in q.get("tests", []) if not t.get("hidden")]
    return {"set": set_id, "id": q["id"], "title": q["title"], "topic": q.get("topic", ""),
            "difficulty": q["difficulty"], "expected_minutes": q.get("expected_minutes"),
            "statement": q.get("statement", ""), "input_format": q.get("input_format", ""),
            "output_format": q.get("output_format", ""), "samples": visible,
            "rubric_question": not q.get("tests"),
            "study": None if exam.is_test_set(set_id) else coach.load(coach.SETS / set_id / "set.json").get("study"),
            "test_mode": exam.is_test_set(set_id),
            "hint_count": len(q.get("hints", [])), "solution_count": len(q.get("solutions", [])),
            "submitted": _submitted(set_id, qid),
            "session": public_session(_load_sessions().get(f"{set_id}/{qid}"))}


def _submitted(set_id, qid):
    return any(a["set"] == set_id and a["q"] == qid for a in coach.read_attempts())


def hint(set_id, qid, level, give_up=False):
    """Hint ladder (rule 7): hint n needs hint n-1; solutions need a submit, or all hints + an explicit give-up.
    Every hint or reveal before submitting is recorded and turns the attempt into 'with lookup'."""
    check_ids(set_id, qid)
    _, q = coach.load_question(set_id, qid)
    hints, sols = q.get("hints", []), q.get("solutions", [])
    done = _submitted(set_id, qid)
    if exam.is_test_set(set_id) and not done:
        raise ValueError("hints and solutions are locked during a test; they open after you submit")
    key = f"{set_id}/{qid}"
    with LOCK:
        sessions = _load_sessions()
        sess = sessions.get(key)
        used = sess.get("hints", []) if sess else []
        levels = {h["level"] for h in used}
        if level == "solution":
            if not sols:
                raise ValueError("no reference solutions for this question yet")
            if not done:
                if not sess:
                    raise ValueError("start the timer and try it first")
                if len(levels) < len(hints) or not give_up:
                    raise ValueError("solutions unlock after you submit, or after all hints and choosing to give up")
                if not sess.get("revealed"):
                    sess["revealed"] = {"at": now(), "elapsed_s": elapsed_s(sess)}
                    _save_sessions(sessions)
            return {"solutions": sols}
        try:
            level = int(level)
        except (TypeError, ValueError):
            raise ValueError("level must be 1-3 or solution")
        if not 1 <= level <= len(hints):
            raise ValueError("no such hint")
        if not done:
            if not sess:
                raise ValueError("start the timer and try it first; hints are recorded against the session")
            if level > 1 and (level - 1) not in levels:
                raise ValueError(f"open hint {level - 1} first")
            if level not in levels:
                sess.setdefault("hints", []).append({"level": level, "at": now(), "elapsed_s": elapsed_s(sess)})
                _save_sessions(sessions)
        return {"level": level, "text": hints[level - 1]}


def _code_path(set_id, qid, lang):
    if lang not in LANGS:
        raise ValueError("lang must be java, py or js")
    return coach.SETS / set_id / f"{qid}{LANGS[lang]}"


def get_code(set_id, qid, lang="java"):
    check_ids(set_id, qid)
    p = _code_path(set_id, qid, lang)
    return {"code": p.read_text(encoding="utf-8") if p.exists() else "", "lang": lang}


def save_code(set_id, qid, code, lang="java"):
    check_ids(set_id, qid)
    if not isinstance(code, str) or len(code) > MAX_CODE:
        raise ValueError("code missing or too large")
    p = _code_path(set_id, qid, lang)
    # one solution file per question: coach.find_solution refuses several
    for other, ext in LANGS.items():
        f = coach.SETS / set_id / f"{qid}{ext}"
        if other != lang and f.exists() and f.read_text(encoding="utf-8").strip():
            raise ValueError(f"{f.name} already exists; delete it or keep using {other}")
    p.write_text(code, encoding="utf-8")
    return {"saved": now()}


# ---------- timer ----------
def _mark_over(sess):
    exp = sess.get("expected_minutes")
    if exp and not sess.get("over_expected_at") and elapsed_s(sess) > exp * 60:
        sess["over_expected_at"] = now()


def _pause(sess, t, reason):
    sess["segments"][-1]["end"] = t
    sess["state"] = "paused"
    sess["pauses"].append({"at": t, "reason": reason, "elapsed_s": elapsed_s(sess)})


def timer(set_id, qid, action, reason=None, away_s=0, lang="java", extra=None):
    extra = extra or {}
    check_ids(set_id, qid)
    key = f"{set_id}/{qid}"
    with LOCK:
        sessions = _load_sessions()
        sess = sessions.get(key)
        t = now()
        if action == "start":
            for k, s in sessions.items():  # only one clock runs at a time
                if k != key and s["state"] == "running":
                    _mark_over(s)
                    _pause(s, t, "switched-question")
            if not sess:
                _, q = coach.load_question(set_id, qid)
                sess = {"set": set_id, "q": qid, "created": t, "state": "paused", "segments": [], "pauses": [],
                        "runs": [], "away_s": 0, "lang": lang if lang in LANGS else "java",
                        "expected_minutes": q.get("expected_minutes"), "over_expected_at": None}
                sessions[key] = sess
            if sess["state"] != "running":
                sess["segments"].append({"start": t, "end": None})
                sess["state"] = "running"
        elif not sess:
            raise ValueError("no session for this question; press Start first")
        elif action == "pause":
            if sess["state"] == "running":
                _mark_over(sess)
                _pause(sess, t, reason if reason in PAUSE_REASONS else "other")
        elif action == "away":
            secs = max(0, min(int(away_s or 0), 24 * 3600))
            sess["away_s"] += secs
            sess.setdefault("aways", []).append({"at": t, "s": secs, "elapsed_s": elapsed_s(sess),
                                                 "reason": reason if reason in AWAY_REASONS else None})
        elif action == "away-reason":
            aw = sess.setdefault("aways", [])
            if aw and reason in AWAY_REASONS:
                aw[-1]["reason"] = reason
        elif action == "activity":
            def num(k, cap):
                try:
                    return max(0, min(int(extra.get(k) or 0), cap))
                except (TypeError, ValueError):
                    return 0
            sess["idle_s"] = sess.get("idle_s", 0) + num("idle_s", 3600)
            sess["keys"] = sess.get("keys", 0) + num("keys", 100000)
            sess["switches"] = sess.get("switches", 0) + num("switches", 1000)
            if num("idle_span", 24 * 3600) >= 60:
                sess.setdefault("idle_spans", []).append({"at": t, "s": num("idle_span", 24 * 3600), "elapsed_s": elapsed_s(sess)})
        else:
            raise ValueError("action must be start, pause, away, away-reason or activity")
        _mark_over(sess)
        _save_sessions(sessions)
        return public_session(sess)


def active():
    """The running session (any question), so every page and the pop-out timer can show it."""
    sessions = _load_sessions()
    running = [s for s in sessions.values() if s["state"] == "running"]
    if running:
        return public_session(running[0])
    paused = sorted(sessions.values(), key=lambda s: (s["pauses"][-1]["at"] if s["pauses"] else s["created"]), reverse=True)
    return public_session(paused[0]) if paused else None


# ---------- run ----------
def run(set_id, qid, code=None, lang="java"):
    check_ids(set_id, qid)
    if code is not None:
        save_code(set_id, qid, code, lang)
    _, q = coach.load_question(set_id, qid)
    if not q.get("tests"):
        raise ValueError("rubric question: no runnable tests")
    path = _code_path(set_id, qid, lang)
    if not path.exists():
        raise ValueError("no code saved yet")
    res = coach.run_tests(q, path)
    failures = []
    for f in res["failures"][:3]:
        if f["hidden"]:  # never leak hidden inputs or expected outputs
            failures.append({"index": f["index"], "hidden": True, "error": (f["error"] or "")[-300:]})
        else:
            failures.append(f)
    key = f"{set_id}/{qid}"
    with LOCK:
        sessions = _load_sessions()
        sess = sessions.get(key)
        if sess:
            sess["runs"].append({"at": now(), "elapsed_s": elapsed_s(sess), "passed": res["passed"], "total": res["total"],
                                 "compile_error": any("compilation failed" in (f.get("error") or "") for f in res["failures"])})
            _mark_over(sess)
            _save_sessions(sessions)
    return {"passed": res["passed"], "total": res["total"], "max_ms": res["max_ms"], "failures": failures,
            "session": public_session(sess)}


# ---------- submit ----------
def submit(set_id, qid, body):
    check_ids(set_id, qid)
    key = f"{set_id}/{qid}"
    stuck = [s for s in body.get("stuck", []) if s in STUCK]
    lookup = bool(body.get("lookup"))
    gave_up = bool(body.get("gave_up"))
    try:
        confidence, felt = int(body.get("confidence", 0)), int(body.get("felt_difficulty", 0))
    except (TypeError, ValueError):
        confidence = felt = 0
    if not 1 <= confidence <= 5 or not 1 <= felt <= 5:
        raise ValueError("pick confidence and felt difficulty (1-5)")
    note = str(body.get("note", "")).strip()[:500]
    with LOCK:
        sessions = _load_sessions()
        sess = sessions.get(key)
        if not sess:
            raise ValueError("no timer session for this question; press Start first")
        if sess["state"] == "running":
            _mark_over(sess)
            sess["segments"][-1]["end"] = now()
            sess["state"] = "paused"
        secs = elapsed_s(sess)
        minutes = max(1, math.ceil(secs / 60))
        hints_used = sorted({h["level"] for h in sess.get("hints", [])})
        if hints_used or sess.get("revealed"):
            lookup = True  # rule 7: a hint or reveal counts as a lookup (half credit)
        notes = (f"web: stuck={','.join(stuck) or 'none'}; conf={confidence}/5; felt={felt}/5"
                 + ("; gave up" if gave_up else "") + (f"; {note}" if note else ""))
        args = Namespace(set=set_id, q=qid, minutes=minutes, lookup=lookup, approach="none", score=None,
                         notes=notes[:300], file=str(_code_path(set_id, qid, sess.get("lang", "java"))))
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                coach.cmd_attempt(args)
        except SystemExit as e:
            raise ValueError(str(e))
        last = coach.read_attempts()[-1]
        exp, runs = sess.get("expected_minutes"), sess["runs"]
        record = {
            "ts": now(), "date": datetime.now().date().isoformat(), "set": set_id, "q": qid,
            "result": last["result"], "tests": last["tests"], "active_s": secs, "minutes": minutes,
            "expected_minutes": exp, "over_expected": bool(exp and secs > exp * 60),
            "over_ratio": round(secs / (exp * 60), 2) if exp else None, "over_expected_at": sess.get("over_expected_at"),
            "started": sess["created"], "segments": sess["segments"], "pauses": sess["pauses"], "away_s": sess["away_s"],
            "aways": sess.get("aways", []), "switches": sess.get("switches", 0), "idle_s": sess.get("idle_s", 0),
            "idle_spans": sess.get("idle_spans", []), "keys": sess.get("keys", 0),
            "idle_pct": min(100, round(sess.get("idle_s", 0) / secs * 100)) if secs else 0,
            "runs": runs, "run_count": len(runs),
            "first_run_s": runs[0]["elapsed_s"] if runs else None,
            "first_pass_s": next((r["elapsed_s"] for r in runs if r["passed"] == r["total"]), None),
            "compile_errors": sum(1 for r in runs if r.get("compile_error")),
            "lookup": lookup, "gave_up": gave_up, "hints_used": hints_used, "hint_log": sess.get("hints", []),
            "revealed": sess.get("revealed"), "stuck": stuck, "confidence": confidence,
            "felt_difficulty": felt, "note": note,
        }
        with HISTORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        del sessions[key]
        _save_sessions(sessions)
    return {"record": record, "message": buf.getvalue().strip()}


def insights():
    """Patterns across submitted sessions: where the time and the struggle go."""
    if not HISTORY_FILE.exists():
        return {"n": 0}
    recs = [json.loads(l) for l in HISTORY_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    n = len(recs)
    stuck = {}
    for r in recs:
        for s in r["stuck"]:
            stuck[s] = stuck.get(s, 0) + 1
    pauses = {}
    for r in recs:
        for p in r["pauses"]:
            pauses[p["reason"]] = pauses.get(p["reason"], 0) + 1
    return {"n": n,
            "over_expected": sum(1 for r in recs if r["over_expected"]),
            "avg_over_ratio": round(sum(r["over_ratio"] or 0 for r in recs) / n, 2),
            "stuck": sorted(stuck.items(), key=lambda kv: -kv[1]),
            "pause_reasons": sorted(pauses.items(), key=lambda kv: -kv[1]),
            "avg_runs": round(sum(r["run_count"] for r in recs) / n, 1),
            "compile_errors": sum(r["compile_errors"] for r in recs),
            "lookups": sum(1 for r in recs if r["lookup"]),
            "avg_confidence": round(sum(r["confidence"] for r in recs) / n, 1),
            "avg_idle_pct": round(sum(r.get("idle_pct", 0) for r in recs) / n),
            "avg_switches": round(sum(r.get("switches", 0) for r in recs) / n, 1),
            "away_min": round(sum(r.get("away_s", 0) for r in recs) / 60),
            "away_reasons": sorted(_count(a.get("reason") or "unanswered" for r in recs for a in r.get("aways", [])).items(), key=lambda kv: -kv[1])}


def _count(it):
    c = {}
    for x in it:
        c[x] = c.get(x, 0) + 1
    return c
