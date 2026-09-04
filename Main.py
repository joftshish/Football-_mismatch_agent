import Core as C
import traceback
from datetime import datetime, timezone

def main():
    print("=== DEBUG v12 ===")
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
    
    debug_msg = f"🔍 DEBUG REPORT\n\nTotal fixtures: {len(fx)}\nPoly events: {len(pev)}\n"
    print(f"fixtures: {len(fx)}, poly: {len(pev)}")
    
    analyzed = []
    skipped_no_poly = 0
    skipped_no_price = 0
    skipped_low_gap = 0
    
    for m in fx:
        ev = C.find_poly(pev, m["home"], m["away"], m["sport"])
        if not ev:
            skipped_no_poly += 1
            continue
        
        ph, pa = C.poly_prices(ev, m["home"], m["away"], m["sport"])
        if ph is None:
            skipped_no_price += 1
            continue
        
        if m["sport"] == "soccer":
            t = cur.get(m["slug"], {})
            hd, ad = t.get(m["home"], {}), t.get(m["away"], {})
            hl = hd.get("played", 0) < 5
            al = ad.get("played", 0) < 5
            hr = hd.get("rank", 17) if not hl else last.get(m["slug"], {}).get(m["home"], {}).get("rank", 17)
            ar = ad.get("rank", 17) if not al else last.get(m["slug"], {}).get(m["away"], {}).get("rank", 17)
            hp, ap = C.soccer_power(hr, hd, True), C.soccer_power(ar, ad, False)
        else:
            hr = tr.get(m["slug"], {}).get(m["home"].lower().split()[-1])
            ar = tr.get(m["slug"], {}).get(m["away"].lower().split()[-1])
            if not hr or not ar:
                continue
            hp, ap = C.tennis_power(hr), C.tennis_power(ar)
        
        gap = abs(hp - ap)
        thr = C.SOCCER_GAP if m["sport"] == "soccer" else C.TENNIS_GAP
        
        if gap < thr:
            skipped_low_gap += 1
            continue
        
        strong_home = hp > ap
        stronger = m["home"] if strong_home else m["away"]
        prob = C.model_prob(gap)
        price = ph if strong_home else pa
        edge = prob - price
        
        analyzed.append({
            "home": m["home"],
            "away": m["away"],
            "gap": gap,
            "prob": prob,
            "price": price,
            "edge": edge,
            "sport": m["sport"]
        })
    
    debug_msg += f"\nSkipped (no Poly market): {skipped_no_poly}"
    debug_msg += f"\nSkipped (no price): {skipped_no_price}"
    debug_msg += f"\nSkipped (low gap): {skipped_low_gap}"
    debug_msg += f"\n\nAnalyzed (passed filters): {len(analyzed)}\n"
    
    if analyzed:
        analyzed.sort(key=lambda x: x["gap"], reverse=True)
        debug_msg += "\nTop mismatches:\n"
        for i, a in enumerate(analyzed[:10], 1):
            icon = "🎾" if a["sport"] == "tennis" else "⚽"
            debug_msg += f"{i}. {icon} {a['home']} vs {a['away']}\n"
            debug_msg += f"   Gap: {round(a['gap'])} | Prob: {round(a['prob']*100)}% | Price: {round(a['price']*100)}% | Edge: {round(a['edge']*100, 1)}%\n"
    else:
        debug_msg += "\n❌ No matches passed all filters"
    
    C.send(debug_msg, html=False)
    print(debug_msg)
    C.save_state(st)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        C.send("❌ خطا:\n" + e[-2000:], html=False)
        raise
