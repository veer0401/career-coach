#!/usr/bin/env python3
"""Local dashboard for career-coach. Reads data/*.json, data/log.jsonl, data/market.md, data/weekly/*.md.

Run: python dashboard/server.py [--port 8765]   (or: python coach.py dashboard)
Binds to 127.0.0.1 only. Write endpoints: POST /api/checkin appends to log.jsonl; POST /api/chat runs the local
`claude` CLI in this folder (needs the per-start token from the served page, one request at a time).
"""
import argparse
import json
import re
import secrets
import shutil
import subprocess
import sys
import threading
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import coach  # noqa: E402
import planner  # noqa: E402
sys.path.insert(0, str(HERE))
import practice  # noqa: E402
import learn  # noqa: E402
import exam  # noqa: E402
from urllib.parse import parse_qs, urlsplit  # noqa: E402

WEEKS = 12

# --- chat: runs the local `claude` CLI in the career-coach folder (no API key) ---
CHAT_TOKEN = secrets.token_urlsafe(24)  # new on every server start; embedded in the served page
CHAT_LOCK = threading.Lock()            # one claude run at a time
CHAT_TIMEOUT_S = 300
MAX_MESSAGE = 6000
SESSION_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
# same tool scope as scripts/weekly.ps1: coach.py only (no arbitrary shell), web lookups, file edits in this folder
ALLOWED_TOOLS = ["Bash(python -I coach.py:*)", "WebSearch", "WebFetch", "Read", "Write", "Edit", "Glob", "Grep"]


def ask_claude(message, session_id=None):
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("`claude` CLI not found on PATH. Install Claude Code and log in, then restart the dashboard.")
    cmd = [exe, "-p", "--output-format", "json", "--allowedTools", ",".join(ALLOWED_TOOLS)]
    if session_id:
        cmd += ["--resume", session_id]
    # the message goes through stdin so text starting with "-" or "/" is never parsed as a flag
    r = subprocess.run(cmd, input=message, capture_output=True, text=True, encoding="utf-8",
                       cwd=str(ROOT), timeout=CHAT_TIMEOUT_S)
    out = (r.stdout or "").strip()
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        raise RuntimeError((r.stderr or out or "claude returned no output").strip()[:600])
    if data.get("is_error"):
        raise RuntimeError(str(data.get("result") or "claude reported an error")[:600])
    return {"reply": data.get("result", ""), "session_id": data.get("session_id", session_id or "")}


CHATS_FILE = ROOT / "data" / "chats.json"
CHAT_ID_RE = re.compile(r"^c[0-9a-z]{6,40}$")
CHATS_LOCK = threading.Lock()


def load_chats():
    return json.loads(CHATS_FILE.read_text(encoding="utf-8")) if CHATS_FILE.exists() else {}


def save_chats(c):
    CHATS_FILE.write_text(json.dumps(c, indent=1, ensure_ascii=False), encoding="utf-8")


def record_chat(chat_id, user_text, reply, session_id, error=None):
    now = datetime.now().isoformat(timespec="seconds")
    with CHATS_LOCK:
        chats = load_chats()
        c = chats.setdefault(chat_id, {"id": chat_id, "title": user_text.strip().splitlines()[0][:60] or "New chat",
                                       "created": now, "session_id": None, "msgs": []})
        c["msgs"].append({"role": "me", "text": user_text, "ts": now})
        if error:
            c["msgs"].append({"role": "sys", "text": "Error: " + error, "ts": now})
        else:
            c["msgs"].append({"role": "ai", "text": reply, "ts": now})
            c["session_id"] = session_id or c["session_id"]
        c["updated"] = now
        save_chats(chats)
        return c


def build_payload():
    cfg, skills, log = coach.load(coach.CONFIG_FILE), coach.load(coach.SKILLS_FILE)["skills"], coach.read_log()
    today = date.today()
    days = coach.counted_days(log, cfg)
    mins = coach.minutes_by_day(log)
    since = coach.days_since_last(days, today)
    ordered = coach.ranked(skills, log, today)
    top = skills[ordered[0]]

    if today.isoformat() in days:
        mode = "counted"
    elif since is None:
        mode = "fresh"
    elif since >= 2:
        mode = "comeback"
    elif since == 1:
        mode = "missed-yesterday"
    else:
        mode = "alive"

    # calendar: WEEKS full Mon-Sun columns ending with the current week
    start = coach.week_start(today) - timedelta(weeks=WEEKS - 1)
    calendar = []
    for i in range(WEEKS * 7):
        d = start + timedelta(days=i)
        calendar.append({"date": d.isoformat(), "minutes": mins.get(d.isoformat(), 0), "future": d > today})
    weekly = []
    for w in range(WEEKS):
        ws = start + timedelta(weeks=w)
        weekly.append({
            "week": ws.isoformat(),
            "days": sum(1 for i in range(7) if (ws + timedelta(days=i)).isoformat() in days),
            "minutes": sum(mins.get((ws + timedelta(days=i)).isoformat(), 0) for i in range(7)),
        })

    skill_rows = []
    for k in ordered:
        s = skills[k]
        skill_rows.append({
            "key": k, "name": s["name"], "category": s["category"], "level": s["level"], "target": s["target"],
            "weight": s["weight"], "confidence": s["confidence"], "status": coach.label(s),
            "minutes_14d": coach.recent_minutes(log, k, today), "evidence": s["evidence"],
            "target_bar": s["target_bar"], "priority": round(coach.priority(k, s, log, today), 2),
        })

    attempts = coach.read_attempts()
    practice = {
        "total": len(attempts),
        "solved_independent": sum(1 for a in attempts if a["result"] == "solved"),
        "by_skill": coach.practice_summary(skills),
        "topics": coach.topic_stats(coach.first_attempts(attempts))[:12],
        "recent": [{k: a[k] for k in ("date", "title", "skill", "topic", "difficulty", "minutes", "result", "tests", "notes")}
                   for a in sorted(attempts, key=lambda a: a["ts"], reverse=True)[:10]],
    }

    market = ROOT / "data" / "market.md"
    weekly_dir = ROOT / "data" / "weekly"
    reports = sorted(weekly_dir.glob("20*.md"), reverse=True) if weekly_dir.exists() else []
    return {
        "today": today.isoformat(),
        "config": cfg,
        "run": coach.run_length(days, today),
        "week_days": coach.week_days(days, today),
        "counted_total": len(days),
        "today_minutes": mins.get(today.isoformat(), 0),
        "mode": mode,
        "mission": {
            "key": ordered[0], "name": top["name"], "level": top["level"], "target": top["target"],
            "minimum": top["minimum"], "deep": top["deep"],
            "minutes": cfg["comeback_minutes"] if mode == "comeback" else cfg["min_minutes"],
        },
        "calendar": calendar,
        "weekly": weekly,
        "skills": skill_rows,
        "practice": practice,
        "planner": planner.snapshot(today),
        "log": sorted(log, key=lambda e: e.get("ts", e["date"]), reverse=True)[:30],
        "resources": learn.snapshot(today),
        "market": market.read_text(encoding="utf-8") if market.exists() else "",
        "report": reports[0].read_text(encoding="utf-8") if reports else "",
        "report_name": reports[0].name if reports else "",
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "CoachDashboard"

    def log_message(self, fmt, *a):  # quiet
        pass

    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, "forbidden", "text/plain")
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            html = (HERE / "index.html").read_text(encoding="utf-8").replace("__CHAT_TOKEN__", CHAT_TOKEN)
            return self._send(200, html, "text/html; charset=utf-8")
        if path == "/api/data":
            return self._send(200, json.dumps(build_payload()), "application/json")
        if path == "/api/chats":
            chats = load_chats()
            items = sorted(({k: c[k] for k in ("id", "title", "created", "updated")} | {"n": len(c["msgs"])}
                            for c in chats.values()), key=lambda c: c["updated"], reverse=True)
            return self._send(200, json.dumps(items), "application/json")
        if path == "/api/chat/history":
            cid = (parse_qs(urlsplit(self.path).query).get("id") or [""])[0]
            c = load_chats().get(cid)
            return self._send(200 if c else 404, json.dumps(c or {"error": "no such chat"}), "application/json")
        if path == "/theme.js":
            return self._send(200, (HERE / "theme.js").read_text(encoding="utf-8"), "application/javascript; charset=utf-8")
        if path == "/theme.css":
            return self._send(200, (HERE / "theme.css").read_text(encoding="utf-8"), "text/css; charset=utf-8")
        if path == "/test":
            html = (HERE / "test.html").read_text(encoding="utf-8").replace("__CHAT_TOKEN__", CHAT_TOKEN)
            return self._send(200, html, "text/html; charset=utf-8")
        if path in ("/api/tests", "/api/test"):
            try:
                tid = (parse_qs(urlsplit(self.path).query).get("id") or [""])[0]
                out = exam.list_tests() if path == "/api/tests" else exam.view(tid)
            except ValueError as e:
                return self._send(400, json.dumps({"error": str(e)}), "application/json")
            return self._send(200, json.dumps(out), "application/json")
        if path == "/practice":
            html = (HERE / "practice.html").read_text(encoding="utf-8").replace("__CHAT_TOKEN__", CHAT_TOKEN)
            return self._send(200, html, "text/html; charset=utf-8")
        if path.startswith("/api/practice/"):
            qs = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
            name = path.rsplit("/", 1)[-1]
            try:
                if name == "sets":
                    out = practice.list_sets()
                elif name == "question":
                    out = practice.question(qs.get("set"), qs.get("q"))
                elif name == "code":
                    out = practice.get_code(qs.get("set"), qs.get("q"), qs.get("lang", "java"))
                elif name == "active":
                    out = {"session": practice.active()}
                elif name == "insights":
                    out = practice.insights()
                else:
                    return self._send(404, "not found", "text/plain")
            except ValueError as e:
                return self._send(400, json.dumps({"error": str(e)}), "application/json")
            return self._send(200, json.dumps(out), "application/json")
        self._send(404, "not found", "text/plain")

    def _handle_practice(self):
        if not secrets.compare_digest(self.headers.get("X-Chat-Token") or "", CHAT_TOKEN):
            return self._send(403, json.dumps({"error": "bad or missing token, reload the page"}), "application/json")
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(length, practice.MAX_CODE * 2)))
            s, q, lang = body.get("set"), body.get("q"), body.get("lang", "java")
            name = self.path.rsplit("/", 1)[-1]
            if name == "save":
                out = practice.save_code(s, q, body.get("code"), lang)
            elif name == "timer":
                out = {"session": practice.timer(s, q, body.get("action"), body.get("reason"), body.get("away_s", 0), lang, body)}
            elif name == "run":
                out = practice.run(s, q, body.get("code"), lang)
            elif name == "hint":
                out = practice.hint(s, q, body.get("level"), bool(body.get("give_up")))
            elif name == "submit":
                out = practice.submit(s, q, body)
            else:
                return self._send(404, "not found", "text/plain")
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            return self._send(400, json.dumps({"error": str(e)}), "application/json")
        self._send(200, json.dumps(out), "application/json")

    def _handle_small(self, fn):
        """Token-checked JSON POST for the Learn and Test pages."""
        if not secrets.compare_digest(self.headers.get("X-Chat-Token") or "", CHAT_TOKEN):
            return self._send(403, json.dumps({"error": "bad or missing token, reload the page"}), "application/json")
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 200_000:
                raise ValueError("request too large")
            out = fn(json.loads(self.rfile.read(length)))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
            return self._send(400, json.dumps({"error": str(e)}), "application/json")
        self._send(200, json.dumps(out), "application/json")

    def _handle_chat(self):
        if not secrets.compare_digest(self.headers.get("X-Chat-Token") or "", CHAT_TOKEN):
            return self._send(403, json.dumps({"error": "bad or missing chat token, reload the page"}), "application/json")
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(length, MAX_MESSAGE * 4)))
            if body.get("delete"):
                cid = str(body["delete"])
                with CHATS_LOCK:
                    chats = load_chats(); chats.pop(cid, None); save_chats(chats)
                return self._send(200, json.dumps({"deleted": cid}), "application/json")
            message = str(body["message"]).strip()
            chat_id = str(body.get("chat_id") or "")
            if not CHAT_ID_RE.match(chat_id):
                raise ValueError("invalid chat id")
            session_id = (load_chats().get(chat_id) or {}).get("session_id")
            if not message or len(message) > MAX_MESSAGE:
                raise ValueError(f"message must be 1-{MAX_MESSAGE} characters")
            if session_id and not SESSION_RE.match(str(session_id)):
                session_id = None
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
            return self._send(400, json.dumps({"error": str(e)}), "application/json")
        if not CHAT_LOCK.acquire(blocking=False):
            return self._send(429, json.dumps({"error": "Claude is still answering the previous message"}), "application/json")
        try:
            result = ask_claude(message, session_id)
        except subprocess.TimeoutExpired:
            err = f"Claude took longer than {CHAT_TIMEOUT_S}s; try a smaller question"
            record_chat(chat_id, message, None, None, err)
            return self._send(504, json.dumps({"error": err}), "application/json")
        except (RuntimeError, OSError) as e:
            record_chat(chat_id, message, None, None, str(e))
            return self._send(502, json.dumps({"error": str(e)}), "application/json")
        finally:
            CHAT_LOCK.release()
        c = record_chat(chat_id, message, result["reply"], result["session_id"])
        self._send(200, json.dumps({"reply": result["reply"], "chat": {k: c[k] for k in ("id", "title", "updated")}}), "application/json")

    def do_POST(self):
        is_practice = self.path.startswith("/api/practice/")
        if not self._host_ok() or (self.path not in ("/api/checkin", "/api/chat", "/api/learn", "/api/test") and not is_practice):
            return self._send(403, "forbidden", "text/plain")
        origin = self.headers.get("Origin")
        if origin and origin.split("://", 1)[-1].split(":")[0] not in ("127.0.0.1", "localhost"):
            return self._send(403, "forbidden", "text/plain")
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._send(415, "json only", "text/plain")
        if self.path == "/api/chat":
            return self._handle_chat()
        if is_practice:
            return self._handle_practice()
        if self.path == "/api/learn":
            return self._handle_small(learn.act)
        if self.path == "/api/test":
            return self._handle_small(exam.act)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(length, 10_000)))
            skills = coach.load(coach.SKILLS_FILE)["skills"]
            skill, minutes = body["skill"], int(body["minutes"])
            what = str(body["what"]).strip()[:300]
            proof = str(body.get("proof", "")).strip()[:300]
            if skill not in skills or not 1 <= minutes <= 600 or not what:
                raise ValueError("invalid skill, minutes or description")
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
            return self._send(400, json.dumps({"error": str(e)}), "application/json")
        coach.append_log({
            "date": date.today().isoformat(), "ts": datetime.now().isoformat(timespec="seconds"),
            "skill": skill, "minutes": minutes, "what": what, "proof": proof,
        })
        self._send(200, json.dumps(build_payload()), "application/json")


def serve(port=8765, open_browser=True):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Dashboard running at {url}  (Ctrl+C to stop)")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    serve(a.port, not a.no_open)
