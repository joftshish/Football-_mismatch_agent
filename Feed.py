import Core as C
import json
import traceback
from datetime import datetime, timezone

GENERIC = {"sports", "soccer", "all sports", "teams", "games", "polymarket",
           "crypto", "bitcoin", "ethereum", "spanish", "english"}


def fuzzy_find(name, tbl):
    n = C.norm(name)
    for key, d in tbl.items():
        k = C.norm(key)
        if n and len(n) >= 4 and (n in k or k in n):
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
    title = ev.get("title") or ""
    return title[:40] if title else "رقابت نامشخص"


def main():
    print("=== Feed start ===")
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

    # --- بارگذاری همه بازارهای فعال ---
    evs = []
    for tag in ["soccer", "tennis", "basketball", "mma", "boxing",
                "baseball", "hockey", "american-football", "golf",
                "motorsports", "cricket", "rugby"]:
        try:
            d = C.httpx.get(f"{C.POLY}/events",
                            params={"closed": "false", "tag_slug": tag, "limit": 200},
                            timeout=15).json()
            if isinstance(d, list):
                for e in d:
                    e["_tag"] = tag
                evs += d
        except Exception as ex:
            print(f"feed poly err {tag}: {ex}")

    print(f"feed events: {len(evs)}, seen: {len(seen_set)}")

    # --- بار اول: فقط ثبت و فعال‌سازی ---
    if not st.get("feed_init"):
        for e in evs:
            seen_set.add(str(e.get("id")))
        st["feed_init"] = True
        st["feed_seen"] = list(seen_set)[-3000:]
        C.save_state(st)
        C.send(f"📡 فید بازار Polymarket فعال شد\n"
               f"{C.fa(len(seen_set))} بازار موجود بارگذاری شد؛ "
               f"از این به بعد هر بازار جدید اعلام می‌شه (بدون تحلیل مدل)",
               html=False)
        print("feed init done", len(seen_set))
        return

    # --- بازارهای جدید ---
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

    print(f"feed new: {len(new)}")

    sent = 0
    for e in new[:30]:
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

        ch = C.COUNTRY.get(slh, "") if slh else ""
        ca = C.COUNTRY.get(sla, "") if sla else ""

        try:
            dt = datetime.fromisoformat(
                (e.get("startDate") or "").replace("Z", "+00:00")
            ).astimezone(C.TZ)
            jd, tm = C.jalali(dt)
        except Exception:
            jd, tm = "", ""

        link = C.poly_link(e) or ""

        # --- قیمت فعلی (اگه هست) ---
        pline = ""
        try:
            mks = e.get("markets") or []
            if mks:
                oc = mks[0].get("outcomes")
                pr = mks[0].get("outcomePrices")
                if isinstance(oc, str):
                    oc = json.loads(oc)
                if isinstance(pr, str):
                    pr = json.loads(pr)
                if oc and pr and len(oc) == len(pr):
                    pcs = []
                    for i, o in enumerate(oc):
                        pcs.append(f"{o}: {C.fa(round(float(pr[i])*100))}٪")
                    pline = "💰 قیمت: " + " | ".join(pcs)
        except Exception:
            pass

        def rl(cr, lr):
            c = C.fa(cr) if cr else "—"
            l = C.fa(lr) if lr else "—"
            return f"جاری {c}، قبل {l}"

        sport_icon = "⚽" if e.get("_tag") == "soccer" else "🎾" if e.get("_tag") == "tennis" else "🏟️"

        txt = (
            f"📡 بازار جدید Polymarket\n"
            f"\n"
            f"{sport_icon} {home} {ch}\n"
            f"🆚 {away} {ca}\n"
            f"\n"
            f"🏆 {lab}\n"
            f"📅 {jd} — ساعت {tm}\n"
            f"\n"
            f"🏅 {home}: {rl(crh, lrh)}\n"
            f"🏅 {away}: {rl(cra, lra)}\n"
        )
        if pline:
            txt += f"{pline}\n"
        txt += (
            f"\n"
            f"ℹ️ فقط مشاهده — تحلیل مدل جداست\n"
            f"🔗 {link}"
        )

        if C.send(txt.strip(), html=False):
            sent += 1

    st["feed_seen"] = list(seen_set)[-3000:]
    C.save_state(st)
    print(f"feed done, sent: {sent}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        try:
            C.send("❌ خطای Feed:\n" + e[-2000:], html=False)
        except Exception:
            pass
        raise
