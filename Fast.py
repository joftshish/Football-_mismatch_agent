import Core as C
import traceback
from datetime import datetime

def analyze_ev(ev, cur, last, tr):
    title = ev.get("title") or ""
    sep = " vs " if " vs " in title else (" v " if " v " in title else None)
    if not sep:
        return None
    home, away = [x.strip() for x in title.split(sep, 1)]
    sport = ev.get("_tag", "soccer")
    ph, pa = C.poly_prices(ev, home, away, sport)
    if ph is None:
        return None
    if sport == "soccer":
        slug = None
        for s, t in cur.items():
            if home in t or away in t:
                slug = s
                break
        if not slug:
            return None
        hd, ad = cur[slug].get(home, {}), cur[slug].get(away, {})
        hl = hd.get("played", 0) < 5
        al = ad.get("played", 0) < 5
        hr = hd.get("rank", 17) if not hl else last.get(slug, {}).get(home, {}).get("rank", 17)
        ar = ad.get("rank", 17) if not al else last.get(slug, {}).get(away, {}).get("rank", 17)
        hp, ap = C.soccer_power(hr, hd, True), C.soccer_power(ar, ad, False)
        league = C.SOCCER[slug]
        icon = "⚽"
    else:
        hr = tr.get("atp", {}).get(home.lower().split()[-1]) or tr.get("wta", {}).get(home.lower().split()[-1])
        ar = tr.get("atp", {}).get(away.lower().split()[-1]) or tr.get("wta", {}).get(away.lower().split()[-1])
        if not hr or not ar:
            return None
        hp, ap = C.tennis_power(hr), C.tennis_power(ar)
        league = "🎾 تنیس"
        icon = "🎾"
    gap = abs(hp - ap)
    thr = C.SOCCER_GAP if sport == "soccer" else C.TENNIS_GAP
    if gap < thr:
        return None
    strong_home = hp > ap
    stronger = home if strong_home else away
    prob = C.model_prob(gap)
    price = ph if strong_home else pa
    edge = prob - price
    kl = C.kelly(prob, price)
    if edge < C.MIN_EDGE or kl <= 0:
        return None
    return {"title": "VALUE BET زودهنگام ⚡", "league": league, "date": ev.get("startDate") or "", "home": home, "away": away, "stronger": stronger, "prob": prob, "price": price, "edge": edge, "kelly": kl, "label": "به‌وضوح نابرابر 🟠", "icon": icon, "note": "⚡ بازار تازه ایجاد شد — برتری زمانی فعال شد"}

def main():
    st = C.load_state()
    known = st.setdefault("known_poly", [])
    noted = st.setdefault("notified", [])
    evs = C.poly_events()
    fresh = [e for e in evs if str(e.get("id")) not in known]
    print("poly:", len(evs), "fresh:", len(fresh))
    if fresh:
        cur = C.soccer_standings()
        now = datetime.now(timezone.utc)
        ls = (now.year if now.month >= 7 else now.year - 1) - 1
        last = C.soccer_standings(ls)
        tr = C.tennis_rankings()
        sent = 0
        for e in fresh[:10]:
            a = analyze_ev(e, cur, last, tr)
            if a and str(e.get("id")) not in noted and C.notify("⚡", a):
                sent += 1
                noted.append(str(e.get("id")))
        print("sent:", sent)
    for e in evs:
        known.append(str(e.get("id")))
    C.save_state(st)
    print("fast done")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        raise
