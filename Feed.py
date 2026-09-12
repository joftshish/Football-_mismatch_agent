import Core as C
import traceback
from datetime import datetime, timezone

GENERIC = {"sports", "soccer", "all sports", "teams", "games", "polymarket", "crypto", "bitcoin", "ethereum", "spanish", "english"}

def fuzzy_find(name, tbl):
    n = C.norm(name)
    for key, d in tbl.items():
        k = C.norm(key)
        if n and (n in k or k in n):
            return d
    return None

def team_info(name, cur, last):
    cr = lr = None
    slug = None
    for s, t in cur.items():
        if s.startswith("uefa."):
            continue
        d = fuzzy_find(name, t)
        if d:
            cr = d.get("rank")
            slug = s
            break
    for s, t in last.items():
        if s.startswith("uefa."):
            continue
        d = fuzzy_find(name, t)
        if d:
            lr = d.get("rank")
            if not slug:
                slug = s
            break
    return cr, lr, slug

def league_label(ev, slug):
    if slug and slug in C.SOCCER:
        return C.SOCCER[slug]
    for t in (ev.get("tags") or []):
        lb = (t.get("label") or "").strip()
        if lb and lb.lower() not in GENERIC:
            return lb
    return "رقابت نامشخص"

def main():
    st = C.load_state()
    prefs = st.get("prefs", {})
    if prefs.get("feed_off"):
        print("feed off")
        return
    seen = st.setdefault("feed_seen", [])
    seen_set = set(seen)
    now = datetime.now(timezone.utc)
    ls = (now.year if now.month >= 7 else now.year - 1) - 1
    cache = C.standings_cache_load(st)
    if cache and cache.get("ls") == ls:
        cur, last = cache["cur"], cache["last"]
    else:
        cur = C.soccer_standings()
        last = C.soccer_standings(ls)
        C.standings_cache_save(st, cur, last, ls)
    evs = C.poly_events()
    new = []
    for e in evs:
        eid = str(e.get("id"))
        if eid in seen_set or C.is_closed(e):
            continue
        sd = e.get("startDate") or ""
        try:
            sdt = datetime.fromisoformat(sd.replace("Z", "+00:00"))
        except Exception:
            sdt = None
        if sdt and sdt < now:
            seen_set.add(eid)
            continue
        new.append(e)
    if not st.get("feed_init"):
        for e in evs:
            seen_set.add(str(e.get("id")))
        st["feed_init"] = True
        st["feed_seen"] = list(seen_set)[-2000:]
        C.save_state(st)
        C.send(f"📡 فید بازار Polymarket فعال شد\n{C.fa(len(seen_set))} بازار موجود بارگذاری شد؛ از این به بعد هر بازار جدید اعلام می‌شه (بدون تحلیل مدل)", html=False)
        print("feed init", len(seen_set))
        return
    sent = 0
    for e in new[:20]:
        eid = str(e.get("id"))
        seen_set.add(eid)
        title = (e.get("title") or "").strip()
        sep = " vs " if " vs " in title else (" v " if " v " in title else None)
        if not sep:
            continue
        parts = [x.strip() for x in title.split(sep, 1)]
        if len(parts) != 2 or not parts[0] or not parts[1]:
            continue
        home, away = parts
        crh, lrh, slh = team_info(home, cur, last)
        cra, lra, sla = team_info(away, cur, last)
        slug = slh or sla
        lab = league_label(e, slug)
        try:
            dt = datetime.fromisoformat((e.get("startDate") or "").replace("Z", "+00:00"))
            jd, tm = C.jalali(dt)
        except Exception:
            jd, tm = "", ""
        def rl(cr, lr):
            return f"جاری {C.fa(cr) if cr else '—'}، قبل {C.fa(lr) if lr else '—'}"
        txt = f"📡 بازار جدید Polymarket (بدون مدل)\n⚽ {home}\n🆚 {away}\n🏆 رقابت: {lab}\n📅 {jd} — ساعت {tm}\n🏅 {home}: {rl(crh, lrh)}\n🏅 {away}: {rl(cra, lra)}\nℹ️ فقط مشاهده — تحلیل مدل جداست\n🔗 لینک:\n{C.poly_link(e)}"
        if C.send(txt, html=False):
            sent += 1
    st["feed_seen"] = list(seen_set)[-2000:]
    C.save_state(st)
    print("feed sent", sent)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        raise
