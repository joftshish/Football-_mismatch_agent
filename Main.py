import Core as C
import traceback
from datetime import datetime, timezone

def main():
    print("=== v12 ===")
    st = C.load_state()
    noted = st.setdefault("notified", [])
    known = st.setdefault("known_poly", [])
    now = datetime.now(timezone.utc)
    ls = (now.year if now.month >= 7 else now.year - 1) - 1
    fx = C.soccer_fixtures() + C.tennis_fixtures()
    cur = C.soccer_standings()
    last = C.soccer_standings(ls)
    tr = C.tennis_rankings()
    pev = C.poly_events()
    print("fixtures:", len(fx), "poly:", len(pev))
    vb = mm = skipped = 0
    rows = []
    for m in fx:
        ev = C.find_poly(pev, m["home"], m["away"], m["sport"])
        if not ev:
            skipped += 1
            continue
        ph, pa = C.poly_prices(ev, m["home"], m["away"], m["sport"])
        if ph is None:
            skipped += 1
            continue
        if m["sport"] == "soccer":
            t = cur.get(m["slug"], {})
            hd, ad = t.get(m["home"], {}), t.get(m["away"], {})
            hl = hd.get("played", 0) < 5
            al = ad.get("played", 0) < 5
            hr = hd.get("rank", 17) if not hl else last.get(m["slug"], {}).get(m["home"], {}).get("rank", 17)
            ar = ad.get("rank", 17) if not al else last.get(m["slug"], {}).get(m["away"], {}).get("rank", 17)
            hp, ap = C.soccer_power(hr, hd, True), C.soccer_power(ar, ad, False)
            low = hl or al
        else:
            hr = tr.get(m["slug"], {}).get(m["home"].lower().split()[-1])
            ar = tr.get(m["slug"], {}).get(m["away"].lower().split()[-1])
            if not hr or not ar:
                skipped += 1
                continue
            hp, ap = C.tennis_power(hr), C.tennis_power(ar)
            low = False
        gap = abs(hp - ap)
        thr = C.SOCCER_GAP if m["sport"] == "soccer" else C.TENNIS_GAP
        if gap < thr:
            continue
        strong_home = hp > ap
        stronger = m["home"] if strong_home else m["away"]
        prob = C.model_prob(gap)
        price = ph if strong_home else pa
        edge = prob - price
        kl = C.kelly(prob, price)
        lab = "کاملاً نابرابر 🔴" if gap >= thr + 10 else "به‌وضوح نابرابر 🟠"
        eid = str(ev.get("id"))
        rows.append((gap, f"{m['home']} - {m['away']} | {round(gap)} | بازار {round(price*100)}% | لبه {round(edge*100,1)}"))
        if m["id"] in noted or eid in known:
            continue
        is_value = edge >= C.MIN_EDGE and kl > 0
        a = {"title": "VALUE BET 💰" if is_value else "بازی نابرابر ⚔️", "league": m["league"], "date": m["date"], "home": m["home"], "away": m["away"], "stronger": stronger, "prob": prob, "price": price, "edge": edge, "kelly": kl if is_value else 0, "label": lab, "icon": "🎾" if m["sport"] == "tennis" else "⚽", "note": None}
        if low:
            a["note"] = "⚠️ داده فصل جاری کم است"
        if not is_value:
            a["note"] = (a["note"] or "") + f"\n❌ لبه کم ({round(edge*100,1)}%) — ارزش بستن ندارد"
        if C.notify("💰" if is_value else "⚔️", a):
            if is_value:
                vb += 1
            else:
                mm += 1
            noted.append(m["id"])
            known.append(eid)
    today = now.strftime("%Y-%m-%d")
    if vb or mm or st.get("last_summary") != today:
        rows.sort(reverse=True)
        top = "\n".join(r[1] for r in rows[:8]) or "—"
        C.send(f"📊 گزارش ایجنت v12\nبازی‌ها: {len(fx)} | با بازار Poly: {len(fx)-skipped} | بدون بازار: {skipped}\n💰 Value: {vb} | ⚔️ نابرابر: {mm}\n\nبرترین‌ها (فقط با بازار):\n{top}", html=False)
        st["last_summary"] = today
    C.save_state(st)
    print("done", vb, mm)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        C.send("❌ خطا:\n" + e[-2000:], html=False)
        raise
