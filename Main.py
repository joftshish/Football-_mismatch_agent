import Core as C
import traceback
from datetime import datetime, timezone

def main():
    print("=== v16 ===")
    st = C.load_state()
    noted = st.setdefault("notified", [])
    known = st.setdefault("known_poly", [])
    watch = st.setdefault("watchlist", [])
    watch_noted = st.setdefault("watch_noted", [])
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
            is_value = edge >= C.MIN_EDGE and kl > 0
            lab = "کاملاً نابرابر 🔴" if c["gap"] >= c["thr"] + 10 else "به‌وضوح نابرابر 🟠"
            a = {"title": "VALUE BET 💰" if is_value else "بازی نابرابر ⚔️", "league": m["league"], "date": m["date"], "home": m["home"], "away": m["away"], "stronger": c["stronger"], "prob": c["prob"], "price": price, "edge": edge, "kelly": kl if is_value else 0, "label": lab, "icon": "🎾" if m["sport"] == "tennis" else "⚽", "link": C.poly_link(ev), "note": None}
            if c["low"]:
                a["note"] = "⚠️ داده فصل جاری کم است"
            if not is_value:
                a["note"] = (a["note"] or "") + f"\n❌ لبه کم ({round(edge*100,1)}%) — ارزش بستن ندارد"
            rows.append((c["gap"], f"{m['home']} - {m['away']} | {round(c['gap'])} | بازار {round(price*100)}% | لبه {round(edge*100,1)}"))
            eid = str(ev.get("id"))
            if m["id"] not in noted and eid not in known:
                if C.notify("💰" if is_value else "⚔️", a):
                    if is_value:
                        vb += 1
                    else:
                        mm += 1
                    noted.append(m["id"])
                    known.append(eid)
        else:
            skipped += 1
            status = f"poly:{src}/قیمت‌نه" if ev else "poly:نه"
            if raw and len(dbg) < 2:
                dbg.append(f"{m['home']}-{m['away']}: {raw}")
            rows.append((c["gap"], f"{m['home']} - {m['away']} | {round(c['gap'])} | {status}"))
            key = f"{m['home']}|{m['away']}"
            if key not in watch_noted:
                if C.notify_watch(m, c):
                    watch_noted.append(key)
                    watch.append({"home": m["home"], "away": m["away"], "sport": m["sport"], "slug": m["slug"], "date": m["date"], "league": m["league"]})
                    wl += 1
    rows.sort(reverse=True)
    top = "\n".join(r[1] for r in rows[:8]) or "—"
    extra = ("\n\n🔬 " + "\n".join(dbg)) if dbg else ""
    C.send(f"📊 گزارش v16 | {getattr(C, 'VERSION', 'CORE-GHADIMI!')}\nبازی‌ها: {len(fx)} (تنیس: {nten}) | بدون بازار: {skipped}\n💰 Value: {vb} | ⚔️ نابرابر: {mm} | 👀 Watch: {wl}\n\nبرترین‌ها:\n{top}{extra}", html=False)
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
