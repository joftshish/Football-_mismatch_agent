import Core as C
import traceback
from datetime import datetime, timezone, timedelta

TAGS = ["soccer", "tennis", "basketball", "mma", "boxing", "baseball", "hockey", "american-football", "golf", "cricket", "rugby"]
GENERIC = {"sports", "soccer", "all sports", "teams", "games", "polymarket", "crypto", "bitcoin", "ethereum"}

def fetch_events():
    out = []
    seen = set()
    for tag in TAGS:
        for offset in (0, 200, 400):
            try:
                d = C.httpx.get(f"{C.POLY}/events", params={"closed": "false", "tag_slug": tag, "limit": 200, "offset": offset}, timeout=15).json()
            except Exception as ex:
                print("feed poly err", tag, offset, ex)
                break
            if not isinstance(d, list) or not d:
                break
            for e in d:
                eid = str(e.get("id"))
                if eid in seen:
                    continue
                seen.add(eid)
                e["_tag"] = tag
                out.append(e)
            if len(d) < 200:
                break
    return out

def fuzzy_find(name, tbl):
    n = C.norm(name)
    if len(n) < 4:
        return None
    for key, d in tbl.items():
        k = C.norm(key)
        if n in k or k in n:
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

def split_title(title):
    sep = " vs " if " vs " in title else (" v " if " v " in title else None)
    if not sep:
        return None
    parts = [x.strip() for x in title.split(sep, 1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts

def digest_lines(evs, now, hours=72, cap=12):
    up = []
    for e in evs:
        if C.is_closed(e):
            continue
        sd = e.get("startDate") or ""
        try:
            sdt = datetime.fromisoformat(sd.replace("Z", "+00:00"))
        except Exception:
            continue
        if sdt <= now or sdt > now + timedelta(hours=hours):
            continue
        up.append((sdt, e))
    up.sort(key=lambda x: x[0])
    lines = []
    for i, (sdt, e) in enumerate(up[:cap], 1):
        parts = split_title((e.get("title") or "").strip())
        if not parts:
            continue
        home, away = parts
        jd, tm = C.jalali(sdt.astimezone(C.TZ))
        lines.append(f"{C.fa(i)}. {home} - {away}\n   {jd} — {tm}\n   {C.poly_link(e)}")
    return lines, len(up)

def main():
    print("=== Feed v3 start ===")
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
    evs = fetch_events()
    print("feed events:", len(evs))
    teh_now = now.astimezone(C.TZ)
    today = teh_now.strftime("%Y-%m-%d")

    if not st.get("feed_init"):
        for e in evs:
            seen_set.add(str(e.get("id")))
        st["feed_init"] = True
        lines, total = digest_lines(evs, now)
        msg = f"📡 فید بازار Polymarket فعال شد\n{C.fa(len(seen_set))} بازار موجود ثبت شد.\nاز این به بعد:\n• هر بازار جدید بلافاصله اعلام می‌شه\n• هر روز یک فهرست از بازی‌های ۷۲ ساعت آینده می‌گیری"
        if lines:
            msg += f"\n\n📋 نخستین فهرست ({C.fa(total)} بازی پیشِ رو، {C.fa(len(lines))} تای اول):\n\n" + "\n\n".join(lines)
        C.send(msg, html=False)
        st["feed_seen"] = list(seen_set)[-3000:]
        st["feed_digest_date"] = today
        C.save_state(st)
        print("feed init done")
        return

    sent = 0
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
    print("feed new:", len(new))
    for e in new[:10]:
        eid = str(e.get("id"))
        seen_set.add(eid)
        parts = split_title((e.get("title") or "").strip())
        if not parts:
            continue
        home, away = parts
        crh, lrh, slh = team_info(home, cur, last)
        cra, lra, sla = team_info(away, cur, last)
        slug = slh or sla
        lab = league_label(e, slug)
        ch = C.COUNTRY.get(slh, "") if slh else ""
        ca = C.COUNTRY.get(sla, "") if sla else ""
        try:
            sdt = datetime.fromisoformat((e.get("startDate") or "").replace("Z", "+00:00"))
            jd, tm = C.jalali(sdt.astimezone(C.TZ))
        except Exception:
            jd, tm = "", ""
        def rl(cr, lr):
            return f"جاری {C.fa(cr) if cr else '—'}، قبل {C.fa(lr) if lr else '—'}"
        txt = f"📡 بازار جدید Polymarket\n⚽ {home} {ch}\n🆚 {away} {ca}\n🏆 {lab}\n📅 {jd} — ساعت {tm}\n🏅 {home}: {rl(crh, lrh)}\n🏅 {away}: {rl(cra, lra)}\nℹ️ فقط مشاهده — تحلیل مدل جداست\n🔗 {C.poly_link(e)}"
        if C.send(txt, html=False):
            sent += 1

    if st.get("feed_digest_date") != today and 9 <= teh_now.hour:
        lines, total = digest_lines(evs, now)
        if lines:
            msg = f"📋 فهرست روزانهٔ بازارها ({C.fa(total)} بازی پیشِ رو، {C.fa(len(lines))} تای اول):\n\n" + "\n\n".join(lines)
            if C.send(msg, html=False):
                sent += 1
        st["feed_digest_date"] = today

    st["feed_seen"] = list(seen_set)[-3000:]
    C.save_state(st)
    print("feed done, sent:", sent)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        try:
            C.send("❌ خطای Feed:\n" + e[-1500:], html=False)
        except Exception:
            pass
        raise
