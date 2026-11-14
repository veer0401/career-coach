#!/usr/bin/env python3
"""Goals, weekly/monthly plans with strict deadlines, and consequences.

Run through coach.py:
  python coach.py goal add|list|done|drop ...
  python coach.py plan new|add|show|done|excuse|drop|check ...
  python coach.py ledger [clear ID --note TEXT]
  python coach.py consequences [--confirm]

Progress is computed from data/log.jsonl and data/practice.jsonl, never typed in:
  solved       practice questions solved (first attempts; --skill/--topic/--min-difficulty filters)
  independent  same, but only solved without lookup
  minutes      minutes logged (optionally for one skill)
  days         counted days
  level        a skill's level reached (from skills.json history)
  manual       you finish it with `done --proof` (deploy, publish, ...)
Status is derived from the window start..due date, so a due date can't be moved to make an item pass.
"""
import argparse
import calendar
import sys
from datetime import date, timedelta

import coach

DATA = coach.DATA
GOALS_FILE = DATA / "goals.json"
PLANS_FILE = DATA / "plans.json"
LEDGER_FILE = DATA / "ledger.json"
CONSEQ_FILE = DATA / "consequences.json"
MEASURES = ["solved", "independent", "minutes", "days", "level", "manual"]
BAD = ("missed", "dropped", "done-late")


def _load(path, key):
    return coach.load(path)[key] if path.exists() else []


def _save(path, key, items):
    coach.save(path, {key: items})


DEFAULT_CONSEQ = {
    "_note": "PROPOSED defaults. Edit them to something you will really honour, then run: python coach.py consequences --confirm. "
             "Penalties (not debts) are only recorded after you confirm.",
    "debt": "It stays red on your dashboard and in `today` until done, and nothing new starts first.",
    "week_penalty": {"threshold": 0.6, "text": "One extra 60-minute catch-up block on the next weekday."},
    "month_penalty": {"threshold": 0.6, "text": "Pick a penalty you would genuinely avoid, agreed in advance."},
    "goal_penalty": {"text": "Write a short honest review of why it slipped and re-plan the goal with the coach."},
    "reward": {"threshold": 0.9, "text": "Take a guilt-free evening off."},
    "jokers_per_month": 2,
}


def consequences():
    """The user's agreed rules; a fresh install falls back to unconfirmed defaults (no penalties until confirmed)."""
    if CONSEQ_FILE.exists():
        return coach.load(CONSEQ_FILE)
    return {k: dict(v) if isinstance(v, dict) else v for k, v in DEFAULT_CONSEQ.items()}


def ctx():
    log, cfg = coach.read_log(), coach.load(coach.CONFIG_FILE)
    return {"log": log, "cfg": cfg, "first": coach.first_attempts(coach.read_attempts()),
            "skills": coach.load(coach.SKILLS_FILE)["skills"], "days": coach.counted_days(log, cfg)}


def value(m, since, until, c, done_on=None):
    s, u, t = since.isoformat(), until.isoformat(), m["type"]
    if t in ("solved", "independent"):
        ok = ("solved",) if t == "independent" else ("solved", "solved-with-lookup")
        return sum(1 for a in c["first"]
                   if s <= a["date"] <= u and a["result"] in ok
                   and (not m.get("skill") or a["skill"] == m["skill"])
                   and (not m.get("topic") or a.get("topic") == m["topic"])
                   and a["difficulty"] >= m.get("min_difficulty", 1))
    if t == "minutes":
        return sum(e.get("minutes", 0) for e in c["log"]
                   if s <= e["date"] <= u and (not m.get("skill") or e.get("skill") == m["skill"]))
    if t == "days":
        return sum(1 for d in c["days"] if s <= d <= u)
    if t == "level":
        sk = c["skills"][m["skill"]]
        lvl = sk["level"]
        for h in reversed(sk.get("history", [])):
            if h["date"] > u:
                lvl = h["from"]
        return lvl
    return 1 if done_on and s <= done_on <= u else 0  # manual


def evaluate(m, since, due, c, today, done_on=None):
    target = m.get("target", 1)
    on_time = value(m, since, due, c, done_on) >= target
    cur = value(m, since, max(due, today), c, done_on)
    if on_time:
        st = "done"
    elif due >= today:
        st = "open"
    elif cur >= target:
        st = "done-late"
    else:
        st = "missed"
    return {"current": round(cur, 1), "target": target, "status": st}


def d(s):
    return date.fromisoformat(s)


def resolve_item(plan, it, c, today):
    if it.get("excused"):
        return {**it, "status": "excused", "current": 0, "target": it["measure"].get("target", 1), "plan": plan["id"]}
    ev = evaluate(it["measure"], d(it.get("start") or plan["start"]), d(it["due"]), c, today, it.get("done_on"))
    if it.get("dropped"):
        ev["status"] = "dropped"
    return {**it, **ev, "plan": plan["id"], "days_left": (d(it["due"]) - today).days}


def resolve_goal(g, c, today):
    ev = evaluate(g["measure"], d(g["start"]), d(g["deadline"]), c, today, g.get("done_on"))
    if g.get("dropped"):
        ev["status"] = "dropped"
    return {**g, **ev, "days_left": (d(g["deadline"]) - today).days}


def rate(items):
    scored = [i for i in items if i["status"] in ("done", "done-late", "missed", "dropped")]
    if not scored:
        return None, 0
    return sum(1 for i in scored if i["status"] == "done") / len(scored), len(scored)


def check(today=None):
    """Idempotently create ledger entries. Returns the entries created in this call."""
    today = today or date.today()
    c, plans, goals = ctx(), _load(PLANS_FILE, "plans"), _load(GOALS_FILE, "goals")
    ledger = _load(LEDGER_FILE, "ledger")
    have = {e["id"]: e for e in ledger}
    cq = consequences()
    agreed = bool(cq.get("confirmed_on"))
    new = []

    def add(eid, kind, text):
        if eid not in have:
            e = {"id": eid, "kind": kind, "created": today.isoformat(), "text": text,
                 "status": "unclaimed" if kind == "reward" else "owed"}
            ledger.append(e)
            have[eid] = e
            new.append(e)

    for plan in plans:
        items = [resolve_item(plan, it, c, today) for it in plan["items"]]
        for it in items:
            eid = f"debt:{it['id']}"
            if it["status"] == "missed":
                add(eid, "debt", f"Missed '{it['title']}' (due {it['due']}). Finish it before starting anything new. {cq['debt']}")
            elif it["status"] == "done-late" and eid in have and have[eid]["status"] == "owed":
                have[eid].update(status="cleared", cleared_on=today.isoformat(), note="completed late")
        if d(plan["end"]) < today:
            r, n = rate(items)
            if r is None or n < 3:
                continue
            kind = "week" if plan["type"] == "week" else "month"
            pen = cq[f"{kind}_penalty"]
            if r < pen["threshold"] and agreed:
                add(f"{kind}pen:{plan['id']}", f"{kind}-penalty", f"{kind.capitalize()} {plan['id']} finished at {r:.0%} on time. {pen['text']}")
            elif kind == "week" and r >= cq["reward"]["threshold"]:
                add(f"reward:{plan['id']}", "reward", f"Week {plan['id']} finished at {r:.0%} on time. {cq['reward']['text']}")
    for g in goals:
        rg = resolve_goal(g, c, today)
        if rg["priority"] == 1 and rg["status"] == "missed" and agreed:
            add(f"goalpen:{g['id']}", "goal-penalty", f"P1 goal '{g['title']}' missed its deadline {g['deadline']}. {cq['goal_penalty']['text']}")
    if new or any(e.get("cleared_on") == today.isoformat() for e in ledger):
        _save(LEDGER_FILE, "ledger", ledger)
    return new


def commitment_score(today=None):
    today = today or date.today()
    c = ctx()
    items = []
    for plan in _load(PLANS_FILE, "plans"):
        items += [resolve_item(plan, it, c, today) for it in plan["items"]]
    recent = [i for i in items if today - timedelta(days=27) <= d(i["due"]) <= today]
    r, n = rate(recent)
    return None if r is None else {"rate": round(r, 2), "n": n}


def snapshot(today=None):
    """Everything the dashboard needs. Also applies pending ledger entries."""
    today = today or date.today()
    check(today)
    c = ctx()
    plans = []
    for plan in _load(PLANS_FILE, "plans"):
        items = [resolve_item(plan, it, c, today) for it in plan["items"]]
        r, n = rate(items)
        plans.append({"id": plan["id"], "type": plan["type"], "start": plan["start"], "end": plan["end"],
                      "items": sorted(items, key=lambda i: (i["due"], i["priority"])),
                      "rate": None if r is None else round(r, 2), "scored": n,
                      "current": d(plan["start"]) <= today <= d(plan["end"])})
    goals = sorted((resolve_goal(g, c, today) for g in _load(GOALS_FILE, "goals") if not g.get("dropped")),
                   key=lambda g: (g["priority"], g["deadline"]))
    ledger = _load(LEDGER_FILE, "ledger")
    return {"goals": goals, "plans": sorted(plans, key=lambda p: p["start"], reverse=True)[:6],
            "owed": [e for e in ledger if e["status"] == "owed"], "rewards": [e for e in ledger if e["kind"] == "reward"][-3:],
            "score": commitment_score(today), "confirmed": bool(consequences().get("confirmed_on"))}


def today_block():
    snap = snapshot()
    lines = []
    for e in snap["owed"]:
        tag = "DEBT" if e["kind"] == "debt" else "OWED"
        lines.append(f"  [{tag}] {e['text']}")
    today = date.today()
    for p in snap["plans"]:
        if not p["current"]:
            continue
        for it in p["items"]:
            if it["status"] == "open" and it["days_left"] <= 2:
                when = "TODAY" if it["days_left"] == 0 else f"in {it['days_left']}d"
                lines.append(f"  [DUE {when}] {it['title']}: {it['current']}/{it['target']}")
    if lines:
        print("Commitments:\n" + "\n".join(lines) + "\n")


# ---------------- CLI ----------------

def measure_from(a, skills):
    m = {"type": a.measure}
    if a.measure != "manual":
        if a.target is None:
            sys.exit("--target is required for measured items")
        m["target"] = a.target
    for k in ("skill", "topic"):
        if getattr(a, k):
            m[k] = getattr(a, k)
    if a.min_difficulty:
        m["min_difficulty"] = a.min_difficulty
    if a.measure == "level" and m.get("skill") not in skills:
        sys.exit("level measures need a valid --skill")
    if m.get("skill") and m["skill"] not in skills:
        sys.exit(f"Unknown skill '{m['skill']}'.")
    return m


def add_measure_args(p):
    p.add_argument("--measure", choices=MEASURES, required=True)
    p.add_argument("--target", type=float)
    p.add_argument("--skill")
    p.add_argument("--topic")
    p.add_argument("--min-difficulty", type=int, choices=range(1, 6), metavar="1-5")


def find_item(item_id):
    plans = _load(PLANS_FILE, "plans")
    for plan in plans:
        for it in plan["items"]:
            if it["id"] == item_id:
                return plans, plan, it
    sys.exit(f"No such item: {item_id}")


def fmt_status(i):
    mark = {"done": "OK  ", "done-late": "LATE", "open": "....", "missed": "MISS", "dropped": "DROP", "excused": "JOKR"}[i["status"]]
    left = f"{i['days_left']}d left" if i["status"] == "open" else ""
    return f"  [{mark}] P{i['priority']} {i['title']}  {i['current']:g}/{i['target']:g}  due {i['due']} {left}".rstrip()


def cmd_goal(a):
    skills = coach.load(coach.SKILLS_FILE)["skills"]
    goals, today = _load(GOALS_FILE, "goals"), date.today()
    if a.sub == "add":
        active = [g for g in goals if not g.get("dropped")]
        if a.priority == 1 and sum(1 for g in active if g["priority"] == 1) >= 3:
            sys.exit("Max 3 active P1 goals. Everything cannot be top priority; drop or demote one first.")
        if d(a.deadline) <= today:
            sys.exit("Deadline must be in the future.")
        g = {"id": f"g{len(goals) + 1}", "title": a.title, "why": a.why or "", "priority": a.priority,
             "created": today.isoformat(), "start": today.isoformat(), "deadline": a.deadline, "measure": measure_from(a, skills)}
        goals.append(g)
        _save(GOALS_FILE, "goals", goals)
        print(f"Added {g['id']} (P{g['priority']}) '{g['title']}' due {g['deadline']}")
    elif a.sub == "list":
        c = ctx()
        for g in sorted((resolve_goal(g, c, today) for g in goals if not g.get("dropped")), key=lambda g: (g["priority"], g["deadline"])):
            print(f"{g['id']:4}P{g['priority']} {g['status'].upper():9}{g['current']:g}/{g['target']:g}  due {g['deadline']} ({g['days_left']}d)  {g['title']}")
        if not goals:
            print("No goals yet. Use /coach-plan to set them.")
    else:
        g = next((g for g in goals if g["id"] == a.id), None)
        if not g:
            sys.exit(f"No such goal: {a.id}")
        if a.sub == "done":
            if g["measure"]["type"] != "manual":
                sys.exit("This goal is measured automatically; it completes when the numbers reach the target.")
            g["done_on"], g["proof"] = today.isoformat(), a.proof
            print(f"Goal {g['id']} marked done with proof: {a.proof}")
        else:
            g["dropped"], g["drop_reason"] = True, a.reason
            print(f"Goal {g['id']} dropped: {a.reason}")
        _save(GOALS_FILE, "goals", goals)


def period(kind, nxt):
    t = date.today()
    if kind == "week":
        s = t - timedelta(days=t.weekday()) + (timedelta(days=7) if nxt else timedelta())
        return s, s + timedelta(days=6)
    y, m = t.year, t.month + (1 if nxt else 0)
    if m == 13:
        y, m = y + 1, 1
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def cmd_plan(a):
    skills = coach.load(coach.SKILLS_FILE)["skills"]
    plans, today = _load(PLANS_FILE, "plans"), date.today()
    if a.sub == "new":
        s, e = period(a.kind, a.next)
        pid = f"{'w' if a.kind == 'week' else 'm'}-{s.isoformat() if a.kind == 'week' else s.strftime('%Y-%m')}"
        if any(p["id"] == pid for p in plans):
            sys.exit(f"Plan {pid} already exists.")
        plans.append({"id": pid, "type": a.kind, "start": s.isoformat(), "end": e.isoformat(), "created": today.isoformat(), "items": []})
        _save(PLANS_FILE, "plans", plans)
        print(f"Created {pid} ({s} to {e}). Items can be added until {today + timedelta(days=1)}; after that it is locked.")
    elif a.sub == "add":
        plan = next((p for p in plans if p["id"] == a.plan), None)
        if not plan:
            sys.exit(f"No such plan: {a.plan}")
        if today > d(plan["created"]) + timedelta(days=1):
            sys.exit("This plan is locked (items can only be added within 1 day of creating it). Due dates are strict.")
        if not d(plan["start"]) <= d(a.due) <= d(plan["end"]):
            sys.exit(f"Due date must be within the plan ({plan['start']} to {plan['end']}).")
        goal = None
        if a.goal:
            goal = next((g for g in _load(GOALS_FILE, "goals") if g["id"] == a.goal), None)
            if not goal:
                sys.exit(f"No such goal: {a.goal}")
        prio = a.priority or (goal["priority"] if goal else 2)
        it = {"id": f"{plan['id']}-{len(plan['items']) + 1}", "title": a.title, "goal": a.goal or "", "priority": prio,
              "due": a.due, "measure": measure_from(a, skills)}
        plan["items"].append(it)
        _save(PLANS_FILE, "plans", plans)
        print(f"Added {it['id']} (P{prio}) due {it['due']}: {it['title']}")
    elif a.sub == "show":
        snap = snapshot()
        shown = [p for p in snap["plans"] if (a.plan and p["id"] == a.plan) or (not a.plan and p["current"])]
        for p in shown:
            r = "n/a" if p["rate"] is None else f"{p['rate']:.0%} on time"
            print(f"{p['id']} ({p['start']} to {p['end']}), {r}")
            print("\n".join(fmt_status(i) for i in p["items"]) or "  (no items)")
        if not shown:
            print("No current plan. Use /coach-plan to create one.")
        sc = snap["score"]
        if sc:
            print(f"\nCommitment score (last 28 days): {sc['rate']:.0%} of {sc['n']} items on time")
    elif a.sub == "check":
        new = check()
        for e in new:
            print(f"[{e['kind'].upper()}] {e['text']}")
        print("Nothing new." if not new else f"\n{len(new)} new ledger entr{'y' if len(new) == 1 else 'ies'}. See: python coach.py ledger")
    else:
        plans, plan, it = find_item(a.item)
        if a.sub == "done":
            if it["measure"]["type"] != "manual":
                sys.exit("This item is measured automatically from your logged work; it completes when the numbers reach the target.")
            it["done_on"], it["proof"] = today.isoformat(), a.proof
            print(f"{it['id']} marked done with proof: {a.proof}")
        elif a.sub == "excuse":
            cq = consequences()
            used = sum(1 for p in plans for i in p["items"] if i.get("excused") and i["excused"][:7] == today.isoformat()[:7])
            if used >= cq["jokers_per_month"]:
                sys.exit(f"No jokers left this month ({cq['jokers_per_month']} allowed). The deadline stands.")
            it["excused"], it["excuse_reason"] = today.isoformat(), a.reason
            print(f"{it['id']} excused with a joker ({used + 1}/{cq['jokers_per_month']} this month): {a.reason}")
        else:  # drop
            it["dropped"], it["drop_reason"] = True, a.reason
            print(f"{it['id']} dropped; it counts as missed (no debt). Reason: {a.reason}")
        _save(PLANS_FILE, "plans", plans)


def cmd_ledger(a):
    ledger = _load(LEDGER_FILE, "ledger")
    if a.sub == "clear":
        e = next((e for e in ledger if e["id"] == a.id), None)
        if not e:
            sys.exit(f"No such entry: {a.id}")
        if e["kind"] == "debt":
            sys.exit("Debts clear themselves when you complete the item.")
        e.update(status="cleared", cleared_on=date.today().isoformat(), note=a.note)
        _save(LEDGER_FILE, "ledger", ledger)
        print(f"Cleared {a.id}: {a.note}")
        return
    check()
    ledger = _load(LEDGER_FILE, "ledger")
    owed = [e for e in ledger if e["status"] == "owed"]
    print(f"{len(owed)} owed" if owed else "Nothing owed.")
    for e in owed:
        print(f"  {e['id']}  [{e['kind']}] {e['text']}")
    for e in ledger:
        if e["status"] == "unclaimed":
            print(f"  {e['id']}  [reward, unclaimed] {e['text']}  (claim: ledger clear {e['id']} --note ...)")
    done = [e for e in ledger if e["status"] == "cleared"][-5:]
    if done:
        print("Recently cleared: " + "; ".join(f"{e['id']} ({e.get('note', '')})" for e in done))


def cmd_consequences(a):
    cq = consequences()
    if a.confirm:
        cq["confirmed_on"] = date.today().isoformat()
        coach.save(CONSEQ_FILE, cq)
    status = f"CONFIRMED on {cq['confirmed_on']}" if cq.get("confirmed_on") else "NOT CONFIRMED: penalties are not applied until you confirm"
    print(f"Consequences: {status}\n")
    print(f"  Missed item   : {cq['debt']}")
    print(f"  Week < {cq['week_penalty']['threshold']:.0%}    : {cq['week_penalty']['text']}")
    print(f"  Month < {cq['month_penalty']['threshold']:.0%}   : {cq['month_penalty']['text']}")
    print(f"  P1 goal missed: {cq['goal_penalty']['text']}")
    print(f"  Week >= {cq['reward']['threshold']:.0%}   : {cq['reward']['text']} (reward)")
    print(f"  Jokers        : {cq['jokers_per_month']} excused items per month")
    print("\nEdit data/consequences.json to change these before confirming.")


def main(cmd, argv):
    p = argparse.ArgumentParser(prog=f"coach.py {cmd}")
    sub = p.add_subparsers(dest="sub", required=True)
    if cmd == "goal":
        s = sub.add_parser("add"); s.add_argument("title"); s.add_argument("--priority", type=int, choices=[1, 2, 3], required=True)
        s.add_argument("--deadline", required=True); s.add_argument("--why"); add_measure_args(s)
        sub.add_parser("list")
        s = sub.add_parser("done"); s.add_argument("id"); s.add_argument("--proof", required=True)
        s = sub.add_parser("drop"); s.add_argument("id"); s.add_argument("--reason", required=True)
        fn = cmd_goal
    elif cmd == "plan":
        s = sub.add_parser("new"); s.add_argument("kind", choices=["week", "month"]); s.add_argument("--next", action="store_true")
        s = sub.add_parser("add"); s.add_argument("plan"); s.add_argument("title"); s.add_argument("--due", required=True)
        s.add_argument("--goal"); s.add_argument("--priority", type=int, choices=[1, 2, 3]); add_measure_args(s)
        s = sub.add_parser("show"); s.add_argument("plan", nargs="?")
        sub.add_parser("check")
        s = sub.add_parser("done"); s.add_argument("item"); s.add_argument("--proof", required=True)
        s = sub.add_parser("excuse"); s.add_argument("item"); s.add_argument("--reason", required=True)
        s = sub.add_parser("drop"); s.add_argument("item"); s.add_argument("--reason", required=True)
        fn = cmd_plan
    elif cmd == "ledger":
        sub.add_parser("list")
        s = sub.add_parser("clear"); s.add_argument("id"); s.add_argument("--note", required=True)
        fn = cmd_ledger
    else:
        p = argparse.ArgumentParser(prog="coach.py consequences"); p.add_argument("--confirm", action="store_true")
        cmd_consequences(p.parse_args(argv))
        return
    if cmd == "ledger" and not argv:
        argv = ["list"]
    fn(p.parse_args(argv))
