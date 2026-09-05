import Core as C
import json, traceback

BAD_WORDS = {"45", "draw", "total", "over", "under", "exact", "score", "corners", "cards", "card", "penalty", "champion", "winner", "advance", "round", "tournament", "margin", "spread", "handicap", "series", "half", "ot", "shootout", "clean", "sheet", "substitute", "replace", "yellow", "red"}
BAD_PHRASES = ["first half", "both teams", "to score", "win by", "extra time", "score first", "within the", "how many", "will there be", "correct score", "goals", "points"]

def is_moneyline(q):
    toks = set(q.replace(".", " ").replace(",", " ").split())
    if toks & BAD_WORDS:
        return False
    for p in BAD_PHRASES:
        if p in q:
            return False
    return True

def main():
    pev = C.poly_events()
    msg = "🔬 DEBUG v3\n\n== A) بازارهای فوتبال ==\n"
    for home, away in [("Lyon", "AJ Auxerre"), ("Wrexham", "Burnley")]:
        ev = C.find_poly(pev, home, away, "soccer", "")
        if not ev:
            ev, _ = C.search_poly(home, away, "soccer", "")
        if not ev:
            msg += f"{home}: NOT found\n"
            continue
        msg += f"\n{home} vs {away}\n→ {ev.get('title','?')[:50]}\n→ start: {str(ev.get('startDate'))[:10]} | closed: {ev.get('closed')}\n"
        for mk in C.get_markets(ev)[:8]:
            q = ((mk.get("question") or "") + " " + (mk.get("groupItemTitle") or "")).lower()
            oc = mk.get("outcomes")
            pr = mk.get("outcomePrices")
            mark = "✅" if is_moneyline(q) else "❌"
            msg += f"  [{mark}] {q[:65]}\n      oc: {str(oc)[:50]} | pr: {str(pr)[:50]}\n"
    msg += "\n== B) لوله تنیس ==\n"
    tf = C.tennis_fixtures()
    msg += f"tennis fixtures: {len(tf)}\n"
    tr = C.tennis_rankings()
    msg += f"ranks loaded → atp: {len(tr.get('atp', {}))} | wta: {len(tr.get('wta', {}))}\n"
        m = tf[0]
        last_name = m["home"].lower().split()[-1]
        msg += f"sample: {m['home']} vs {m['away']} ({m['slug']})\n"
        msg += f"lookup '{last_name}' → {tr.get(m['slug'], {}).get(last_name)}\n"
    tev = [e for e in pev if e.get("_tag") == "tennis"]
    msg += f"poly tennis events: {len(tev)}\n"
    if tev:
        msg += f"sample: {tev[0].get('title','?')[:60]}\n"
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
