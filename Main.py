import Core as C
import traceback
from datetime import datetime, timezone

def main():
    print("=== v21 ===")
    st = C.load_state()
    noted = st.setdefault("notified", [])
    known = st.setdefault("known_poly", [])
    watch = st.setdefault("watchlist", [])
    watch_noted = st.setdefault("watch_noted", [])
    links = st.setdefault("last_links", [])
    prefs = st.get("prefs", {})
    off_l = set(prefs.get("off", []))
    only_v = prefs.get("only_value", False)
    min_e = prefs.get("min_edge", C.MIN_EDGE)
    now = datetime.now(timezone.utc)
    ls = (now.year if now.month >= 7 else now.year - 1) - 1
    fx = C.soccer_fixtures() + C.tennis_fixtures()
    nten = sum(1 for m in fx if m["sport"] == "tennis")
    cur = C.soccer_standings()
    last = C.soccer_standings(ls)
    tr = C.tennis_rankings()
    pev = C.poly_events()
    vb = mm = wl = skipped = 0
    rows = []
    dbg = []
    for m in fx:
        if m["league"] in off_l:
            continue
        c = C.compute(m, cur, last, tr)
        if not c:
            continue
        ev = C.find_poly(pev, m["home"], m["away"], m["sport"], m["date"])
        src = "list"
        raw = ""
        if not ev:
            ev, raw = C.search_poly(m["home"], m["away"], m["sport"], m["date"])
            src = "search"
        ph = pa = None
        if ev:
            ph, pa = C.poly_prices(ev, m["home"], m["away"], m["sport"])
        if ev and ph is not None:
            price = ph if c["sh"] else pa
            edge = c["prob"] - price
            kl = C.kelly(c["prob"], price)
            is_value = c["solid"] and edge >= min_e and edge <= C.MAX_EDGE and kl > 0
            note = None
            if edge > C.MAX_EDGE:
                note = "⚠️ لبه مشکوک (زیاد) — با احتیاط!"
            elif not c["solid"]:
                note = "⚠️ اوایل فصل/داده کم — فقط اطلاع، بت سنگین ممنوع"
            elif not is_value and edge < min_e:
                note = f"❌ لبه کم ({round(edge*100,1)}%) — ارزش بستن ندارد"
            lab = "کاملاً نابرابر 🔴" if c["gap"] >= c["thr"] + 10 else "به‌وضوح نابرابر 🟠"
            a = {"title": "VALUE BET 💰" if is_value else "بازی نابرابر ⚔️", "league": m["league"], "date": m["date"], "home": m["home"], "away": m["away"], "stronger": c["stronger"], "prob": c["prob"], "price": price, "edge": edge, "kelly": kl if is_value else 0, "label": lab, "icon": "🎾" if m["sport"] == "tennis" else "⚽", "link": C.poly_link(ev), "note": note}
            rows.append((c["gap"], f"{m['home']} - {m['away']} | {round(c['gap'])} | بازار {round(price*100)}% | لبه {round(edge*100,1)}"))
            eid = str(ev.get("id"))
            if m["id"] not in noted and eid not in known:
                if only_v and not is_value:
                    noted.append(m["id"])
                    known.append(eid)
                    continue
                if C.notify("💰" if is_value else "⚔️", a):
                    if is_value:
                        vb += 1
                    else:
                        mm += 1
                    noted.append(m["id"])
                    known.append(eid)
                    if a.get("link"):
                        links.append(f"{m['home']} vs {m['away']}\n{a['link']}")
        else:
            skipped += 1
            status = f"poly:{src}/قیمت‌نه" if ev else "poly:نه"
            if raw and len(dbg) < 2:
                dbg.append(f"{m['home']}-{m['away']}: {raw}")
            rows.append((c["gap"], f"{m['home']} - {m['away']} | {round(c['gap'])} | {status}"))
            key = f"{m['home']}|{m['away']}"
            if key not in watch_noted:
                if not only_v and C.notify_watch(m, c):
                    watch_noted.append(key)
                    watch.append({"home": m["home"], "away": m["away"], "sport": m["sport"], "slug": m["slug"], "date": m["date"], "league": m["league"]})
                    wl += 1
    st["last_links"] = links[-10:]
    rows.sort(reverse=True)
    top = "\n".join(r[1] for r in rows[:8]) or "—"
    extra = ("\n\n🔬 " + "\n".join(dbg)) if dbg else ""
    probe = ("\n\n🎾 probe: " + C.tennis_probe()) if nten == 0 else ""
    C.send(f"📊 گزارش v21 | {getattr(C, 'VERSION', 'CORE-GHADIMI!')}\nبازی‌ها: {len(fx)} (تنیس: {nten}) | بدون بازار: {skipped}\n💰 Value: {vb} | ⚔️ نابرابر: {mm} | 👀 Watch: {wl}\n\nبرترین‌ها:\n{top}{extra}{probe}", html=False)
    st["last_summary"] = now.strftime("%Y-%m-%d")
    C.save_state(st)
    print("done", vb, mm, wl)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        C.send("❌ خطا:\n" + e[-2000:], html=False)
        raise
