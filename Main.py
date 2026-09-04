import httpx
import Core as C
import json, traceback
from datetime import datetime, timezone

def main():
    fx = C.soccer_fixtures() + C.tennis_fixtures()
    pev = C.poly_events()
    
    cur = C.soccer_standings()
    now = datetime.now(timezone.utc)
    ls = (now.year if now.month >= 7 else now.year - 1) - 1
    last = C.soccer_standings(ls)
    tr = C.tennis_rankings()
    
    msg = f"🔬 DIAGNOSTIC\nfixtures: {len(fx)}\npoly events: {len(pev)}\n\n"
    
    count = 0
    for m in fx:
        if count >= 3:
            break
        
        c = C.compute(m, cur, last, tr)
        if not c or c["gap"] < 50:
            continue
        
        msg += f"=== {m['home']} vs {m['away']} ===\n"
        msg += f"gap: {round(c['gap'])} | prob: {round(c['prob']*100)}% | stronger: {c['stronger']}\n\n"
        
        ev = C.find_poly(pev, m["home"], m["away"], m["sport"])
        if not ev:
            ev, _ = C.search_poly(m["home"], m["away"], m["sport"])
        
        if not ev:
            msg += "❌ Polymarket NOT found\n\n"
            count += 1
            continue
        
        msg += f"✅ Polymarket: {ev.get('title', '?')[:60]}\n"
        msg += f"slug: {ev.get('slug', '?')[:40]}\n\n"
        
        mks = C.get_markets(ev)
        msg += f"markets: {len(mks)}\n\n"
        
        for i, mk in enumerate(mks[:3]):
            msg += f"Market {i+1}:\n"
            msg += f"  question: {(mk.get('question') or '?')[:80]}\n"
            oc = mk.get("outcomes")
            pr = mk.get("outcomePrices")
            if isinstance(oc, str):
                try:
                    oc = json.loads(oc)
                except:
                    pass
            if isinstance(pr, str):
                try:
                    pr = json.loads(pr)
                except:
                    pass
            msg += f"  outcomes: {str(oc)[:120]}\n"
            msg += f"  prices: {str(pr)[:120]}\n\n"
        
        ph, pa = C.poly_prices(ev, m["home"], m["away"], m["sport"])
        msg += f"✅ poly_prices result:\n"
        msg += f"  home_price: {ph}\n"
        msg += f"  away_price: {pa}\n"
        
        if ph is not None and pa is not None:
            price = ph if c["sh"] else pa
            edge = c["prob"] - price
            msg += f"  → قیمت تیم قوی‌تر ({c['stronger']}): {round(price*100, 1)}%\n"
            msg += f"  → edge: {round(edge*100, 1)}%\n"
        else:
            msg += f"  ❌ prices NOT found\n"
        
        msg += "\n" + "="*50 + "\n\n"
        count += 1
    
    if count == 0:
        msg += "No high-gap matches to debug"
    
    C.send(msg, html=False)
    print(msg)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        C.send("❌ خطا:\n" + e[-2000:], html=False)
        raise
