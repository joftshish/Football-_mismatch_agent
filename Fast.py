import Core as C
import traceback
from datetime import datetime, timezone, timedelta

def is_past(ds, grace=1.0):
    try:
        dt = datetime.fromisoformat(ds.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > dt + timedelta(hours=grace)
    except Exception:
        return False

def analyze_ev(ev, cur, last, tr, min_e, cal):
    title = (ev.get("title") or "").strip()
    sep = " vs " if " vs " in title else (" v " if " v " in title else None)
    if not sep:
        return None
    parts = [x.strip() for x in title.split(sep, 1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    home, away = parts
    sport = ev.get("_tag", "soccer")
    m = {"home": home, "away": away, "sport": sport, "slug": "", "date": ev.get("startDate") or "", "league": "", "id": str(ev.get("id"))}
    if sport == "soccer":
        slug = None
        for s, t in cur.items():
            if home in t or away in t:
                slug = s
                break
        if not slug:
            return None
        m["slug"] = slug
        m["league"] = C.SOCCER[slug]
    else:
        m["slug"] = "atp" if tr.get("atp", {}).get(home.lower().split()[-1]) else "wta"
        m["league"] = "🎾 تنیس"
    c = C.compute(m, cur, last, tr)
    if not c:
        return None
    c["prob"] = 0.5 + (c["prob"] - 0.5) * cal
    ph, pa = C.poly_prices(ev, home, away, sport)
    if ph is None:
        return None
    price = ph if c["sh"] else pa
    edge = c["prob"] - price
    kl = C.kelly(c["prob"], price)
    if edge < min_e or edge > C.MAX_EDGE or kl <= 0 or not c["solid"]:
        return None
    return {"m": m, "c": c, "price": price, "edge": edge, "kl": kl, "title": "VALUE BET زودهنگام ⚡", "league": m["league"], "date": m["date"], "home": home, "away": away, "stronger": c["stronger"], "prob": c["prob"], "label": "به‌وضوح نابرابر 🟠", "icon": "🎾" if sport == "tennis" else "⚽", "link": C.poly_link(ev), "note": "⚡ بازار تازه ایجاد شد", "hcr": c.get("hcr"), "hlr": c.get("hlr"), "acr": c.get("acr"), "alr": c.get("alr"), "bh": c.get("bh"), "ba": c.get("ba")}

def main():
    st = C.load_state()
    known = st.setdefault("known_poly", [])
    noted = st.setdefault("notified", [])
    watch = st.setdefault("watchlist", [])
    watch[:] = [w for w in watch if not is_past(w.get("date", ""))]
    preds = st.setdefault("preds", [])
    links = st.setdefault("last_links", [])
    prefs = st.get("prefs", {})
    cal = st.get("calib", 1.0)
    off_l = set(prefs.get("off", []))
    only_v = prefs.get("only_value", False)
    min_e = prefs.get("min_edge", C.MIN_EDGE)
    evs = C.poly_events()
    fresh = [e for e in evs if str(e.get("id")) not in known]
    print("poly:", len(evs), "fresh:", len(fresh))
    sent = 0
    if fresh or watch:
        cur = C.soccer_standings()
        now = datetime.now(timezone.utc)
        ls = (now.year if now.month >= 7 else now.year - 1) - 1
        last = C.soccer_standings(ls)
        tr = C.tennis_rankings()
        remaining = []
        for w in watch:
            if w["league"] in off_l:
                continue
            ev = C.find_poly(evs, w["home"], w["away"], w["sport"])
            if not ev:
                ev, _ = C.search_poly(w["home"], w["away"], w["sport"])
            if not ev:
                remaining.append(w)
                continue
            m = dict(w)
            m["id"] = ""
            c = C.compute(m, cur, last, tr)
            ph, pa = C.poly_prices(ev, w["home"], w["away"], w["sport"])
            if not c or ph is None:
                remaining.append(w)
                continue
            c["prob"] = 0.5 + (c["prob"] - 0.5) * cal
            price = ph if c["sh"] else pa
            edge = c["prob"] - price
            kl = C.kelly(c["prob"], price)
            is_value = c["solid"] and edge >= min_e and edge <= C.MAX_EDGE and kl > 0
            a = {"title": "بازار باز شد + VALUE BET 💰⚡" if is_value else "بازار Polymarket باز شد ⚡", "league": w["league"], "date": w["date"], "home": w["home"], "away": w["away"], "stronger": c["stronger"], "prob": c["prob"], "price": price, "edge": edge, "kelly": kl if is_value else 0, "label": "به‌وضوح نابرابر 🟠", "icon": "🎾" if w["sport"] == "tennis" else "⚽", "link": C.poly_link(ev),"note": None if is_value else ("⚠️ لبه مشکوک (زیاد) — با احتیاط!" if edge > C.MAX_EDGE else ("⚠️ اوایل فصل/داده کم — فقط اطلاع" if not c["solid"] else f"❌ لبه کم ({C.fa(round(edge*100,1))}٪) — فقط برای اطلاع")), , "hcr": c.get("hcr"), "hlr": c.get("hlr"), "acr": c.get("acr"), "alr": c.get("alr"), "bh": c.get("bh"), "ba": c.get("ba")}
            if only_v and not is_value:
                known.append(str(ev.get("id")))
                continue
            if C.notify("⚡", a):
                sent += 1
                noted.append(str(ev.get("id")))
                preds.append({"home": w["home"], "away": w["away"], "sport": w["sport"], "slug": w["slug"], "date": w["date"], "prob": round(c["prob"], 3), "price": round(price, 3), "stronger": c["stronger"], "link": a.get("link"), "status": "open"})
                if a.get("link"):
                    links.append(f"{w['home']} vs {w['away']}\n{a['link']}")
            known.append(str(ev.get("id")))
        watch[:] = remaining
        for e in fresh[:10]:
            try:
                a = analyze_ev(e, cur, last, tr, min_e, cal)
                if a and a["league"] not in off_l and str(e.get("id")) not in noted and C.notify("⚡", a):
                    sent += 1
                    noted.append(str(e.get("id")))
                    preds.append({"home": a["home"], "away": a["away"], "sport": a["m"]["sport"], "slug": a["m"]["slug"], "date": a["date"], "prob": round(a["prob"], 3), "price": round(a["price"], 3), "stronger": a["stronger"], "link": a.get("link"), "status": "open"})
                    if a.get("link"):
                        links.append(f"{a['home']} vs {a['away']}\n{a['link']}")
            except Exception as ex:
                print("ev err:", ex)
    st["preds"] = preds[-300:]
    st["last_links"] = links[-10:]
    for e in evs:
        known.append(str(e.get("id")))
    C.save_state(st)
    print("fast done, sent:", sent)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        try:
            C.send("❌ خطای Fast:\n" + e[-2000:], html=False)
        except Exception:
            pass
        raise
