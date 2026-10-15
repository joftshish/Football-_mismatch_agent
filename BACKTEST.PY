import Core as C
import json
import httpx
from datetime import datetime, timezone

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports"

def fetch_result(home, away, sport, slug, date):
    """نتیجهٔ واقعی بازی رو از ESPN می‌گیره"""
    try:
        d = datetime.fromisoformat(date.replace("Z", "+00:00")).strftime("%Y%m%d")
        if sport == "tennis":
            url = f"{ESPN_SCOREBOARD}/tennis/{slug}/scoreboard"
        else:
            url = f"{ESPN_SCOREBOARD}/soccer/{slug}/scoreboard"
        r = httpx.get(url, params={"dates": d}, timeout=15).json()
        for ev in r.get("events", []):
            cs = ev.get("competitions", [{}])[0].get("competitors", [])
            h = next((c for c in cs if c.get("homeAway") == "home"), None)
            a = next((c for c in cs if c.get("homeAway") == "away"), None)
            if not h or not a:
                continue
            hn = (h.get("team") or {}).get("displayName", "")
            an = (a.get("team") or {}).get("displayName", "")
            kh = C.keys(home, sport)
            ka = C.keys(away, sport)
            h_match = any(k in C.norm(hn) for k in kh)
            a_match = any(k in C.norm(an) for k in ka)
            if h_match and a_match:
                if sport == "tennis":
                    h_score = h.get("score", {}).get("value", "0")
                    a_score = a.get("score", {}).get("value", "0")
                    winner = "home" if int(h_score) > int(a_score) else "away"
                    return {"home": h_score, "away": a_score, "winner": winner}
                else:
                    h_score = int(h.get("score", 0))
                    a_score = int(a.get("score", 0))
                    if h_score > a_score:
                        winner = "home"
                    elif a_score > h_score:
                        winner = "away"
                    else:
                        winner = "draw"
                    return {"home": h_score, "away": a_score, "winner": winner}
    except Exception as ex:
        print(f"fetch_result err: {home} vs {away}", ex)
    return None

def backtest():
    st = C.load_state()
    preds = st.get("preds", [])
    if not preds:
        print("هیچ سیگنالی در state نیست")
        C.send("📊 <b>بک‌تست</b>\n\nهیچ سیگنال قبلی در state یافت نشد.")
        return
    
    results = []
    for p in preds:
        if p.get("status") != "closed":
            continue
        res = fetch_result(p["home"], p["away"], p["sport"], p.get("slug", ""), p["date"])
        if not res:
            continue
        entry = p.get("price", 0.5)
        pnl = p.get("pnl", 0)
        winner = res["winner"]
        stronger = p.get("stronger", "")
        won = (winner == "home" and stronger == p["home"]) or (winner == "away" and stronger == p["away"])
        results.append({
            "home": p["home"],
            "away": p["away"],
            "league": p.get("slug", ""),
            "date": p["date"],
            "entry": entry,
            "exit": entry + pnl,
            "pnl": pnl,
            "result": res,
            "won": won,
            "stronger": stronger,
            "src": p.get("src", "unknown")
        })
    
    if not results:
        C.send("📊 <b>بک‌تست</b>\n\nهیچ سیگنال بسته‌شده‌ای یافت نشد.")
        return
    
    wins = sum(1 for r in results if r["won"])
    losses = len(results) - wins
    total_pnl = sum(r["pnl"] for r in results)
    win_rate = (wins / len(results)) * 100 if results else 0
    
    lines = [
        f"📊 <b>گزارش بک‌تست</b>",
        "",
        f"سیگنال‌های بسته‌شده: {C.fa(len(results))}",
        f"بردها: {C.fa(wins)} | باخت‌ها: {C.fa(losses)}",
        f"نرخ برد: {C.fa(round(win_rate, 1))}٪",
        f"P/L کل: {C.fa(round(total_pnl*100, 1))}٪",
        "",
        "جزئیات:"
    ]
    
    for r in results[:20]:
        status = "✅" if r["won"] else "❌"
        result_str = f"{r['result']['home']}-{r['result']['away']}"
        pnl_str = f"{round(r['pnl']*100, 1)}٪"
        lines.append(f"{status} {r['home']} vs {r['away']} ({result_str}) | ورود: {C.fa(round(r['entry']*100))}٪ → خروج: {C.fa(round(r['exit']*100))}٪ | P/L: {pnl_str}")
    
    C.send("\n".join(lines))
    print(f"Backtest done: {len(results)} signals, {wins}W/{losses}L, P/L: {total_pnl}")

if __name__ == "__main__":
    backtest()
