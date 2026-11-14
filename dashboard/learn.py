"""Learn tab engine: per-link "read" marks, written recall, spaced revisions, topic notes, practice stats.

  data/resources.json        topics + links, written by the coach (/coach-week weekly scan). Read only here.
  data/learn_progress.json   the user's side: {"topics": {key: {"read": {url: ts}, "recalls": [...], "notes": str}}}

A first recall logs the read links' minutes to data/log.jsonl (so reading counts toward the 20-minute day);
a revision recall logs 5 minutes. Revisions fall due 3, 7 and 21 days after the first recall.
"""
import threading
from datetime import date, datetime, timedelta

import coach

RES_FILE = coach.DATA / "resources.json"
PROG_FILE = coach.DATA / "learn_progress.json"
REVISE_DAYS = [3, 7, 21]
REVISE_MIN = 5
MIN_RECALL = 40          # characters; roughly three short lines
MAX_TEXT = 4000
LOCK = threading.Lock()


def _now():
    return datetime.now().isoformat(timespec="seconds")


def resources():
    try:
        r = coach.load(RES_FILE) if RES_FILE.exists() else {}
    except ValueError:
        r = {}
    return r if isinstance(r, dict) else {}


def _progress():
    try:
        p = coach.load(PROG_FILE) if PROG_FILE.exists() else {}
    except ValueError:
        p = {}
    p.setdefault("topics", {})
    return p


def _topic(key):
    for t in resources().get("topics", []):
        if t.get("key") == key:
            return t
    raise ValueError("unknown topic")


def _revision(prog_t, today):
    """Next revision step for a topic, or None when not started."""
    recalls = prog_t.get("recalls", [])
    first = next((r for r in recalls if r["kind"] == "first"), None)
    if not first:
        return None
    done = sum(1 for r in recalls if r["kind"] == "revise")
    if done >= len(REVISE_DAYS):
        return {"step": done, "of": len(REVISE_DAYS), "finished": True}
    due = date.fromisoformat(first["at"][:10]) + timedelta(days=REVISE_DAYS[done])
    return {"step": done + 1, "of": len(REVISE_DAYS), "due": due.isoformat(), "is_due": due <= today, "finished": False}


def _practice(t, first_attempts):
    names = {n.lower() for n in t.get("practice_topics") or [t.get("key", "").replace("_", "-")]}
    items = [a for a in first_attempts if (a.get("topic") or "").lower() in names]
    if not items:
        return None
    solved = sum(1 for a in items if a["result"] == "solved")
    lookup = sum(1 for a in items if a["result"] == "solved-with-lookup")
    return {"n": len(items), "solved": solved, "with_lookup": lookup, "unsolved": len(items) - solved - lookup,
            "sets": sorted({a["set"] for a in items})}


def snapshot(today=None):
    today = today or date.today()
    res, prog = resources(), _progress()
    first = coach.first_attempts(coach.read_attempts())
    topics = []
    for t in res.get("topics", []):
        if not isinstance(t, dict) or not t.get("key"):
            continue
        p = prog["topics"].get(t["key"], {})
        topics.append(dict(t, progress={
            "read": sorted(p.get("read", {})),
            "recalls": p.get("recalls", []),
            "notes": p.get("notes", ""),
            "revision": _revision(p, today),
        }, practice=_practice(t, first)))
    return {k: res.get(k) for k in ("updated", "week_of", "note")} | {"topics": topics, "revise_days": REVISE_DAYS}


def act(body):
    action, key = body.get("action"), str(body.get("topic") or "")
    t = _topic(key)
    with LOCK:
        prog = _progress()
        p = prog["topics"].setdefault(key, {"read": {}, "recalls": [], "notes": ""})
        logged = None
        if action == "read":
            url = str(body.get("url") or "")
            if url not in {l.get("url") for l in t.get("links", [])}:
                raise ValueError("unknown link")
            if body.get("value", True):
                p["read"].setdefault(url, _now())
            else:
                p["read"].pop(url, None)
        elif action == "notes":
            p["notes"] = str(body.get("text") or "")[:MAX_TEXT]
            p["notes_at"] = _now()
        elif action == "recall":
            text = str(body.get("text") or "").strip()[:MAX_TEXT]
            if len(text) < MIN_RECALL:
                raise ValueError("write at least three short lines in your own words")
            if not any(r["kind"] == "first" for r in p["recalls"]):
                if not p["read"]:
                    raise ValueError("mark at least one link as read first")
                minutes = sum(l.get("minutes") or 0 for l in t.get("links", []) if l.get("url") in p["read"])
                minutes = max(5, min(60, minutes))
                kind, what = "first", f"read + recall: {t.get('title', key)}"
            else:
                rev = _revision(p, date.today())
                if rev.get("finished"):
                    raise ValueError("all revisions for this topic are done")
                if not rev["is_due"]:
                    raise ValueError(f"next revision is due on {rev['due']}")
                minutes, kind, what = REVISE_MIN, "revise", f"revision {rev['step']}/{rev['of']}: {t.get('title', key)}"
            p["recalls"].append({"kind": kind, "at": _now(), "text": text, "minutes": minutes})
            skill = t.get("skill") if t.get("skill") in coach.load(coach.SKILLS_FILE)["skills"] else "dsa"
            coach.append_log({"date": date.today().isoformat(), "ts": _now(), "skill": skill, "minutes": minutes,
                              "what": what, "proof": "learn recall"})
            logged = minutes
        else:
            raise ValueError("unknown action")
        coach.save(PROG_FILE, prog)
    return {"ok": True, "logged_minutes": logged, "learn": snapshot()}
