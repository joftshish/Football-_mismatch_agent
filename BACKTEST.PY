import httpx, os, time, traceback
from datetime import datetime, timedelta

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
BASE = "https://site.api.espn.com/apis"
LEAGUES = {"eng.1": "انگلیس", "esp.1": "اسپانیا", "ger.1": "آلمان", "ita.1": "ایتالیا", "fra.1": "فرانسه"}

DEFAULT_TEAM = {"rank": 17, "played": 10, "wins": 3, "gf": 12, "ga": 20}

def standings(season):
    out = {}
    for slug in LEAGUES:
        t = {}
        try:
            r = httpx.get(f"{BASE}/v2/sports/soccer/{slug}/standings", params={"season": season, "seasontype": 1}, timeout=15).json()
            for ch in r.get("children", []):
                for e in ch.get("standings", {}).get("entries", []):
                    name = (e.get("team") or {}).get("displayName", "")
                    st = {s.get("name"): s.get("value", 0) for s in e.get("stats", [])}
                    if name:
                        t[name] = {"rank": int(st.get("rank", 14)), "played": int(st.get("gamesPlayed", 0)), "wins": int(st.get("wins", 0)), "gf": int(st.get("pointsFor", 0)), "ga": int(st.get("pointsAgainst", 0))}
        except Exception as ex:
            print("st err", slug, ex)
        out[slug] = t
        time.sleep(0.2)
    return out

def power(rank, d, home):
    base = 100 - int(rank) * 3
    played = d.get("played", 0)
    if played > 0:
        form_bonus = ((d.get("wins", 0) / played) - 0.4) * 15
        gd_bonus = max(-10, min(10, ((d.get("gf", 0) - d.get("ga", 0)) / played) * 5))
    else:
        form_bonus = 0
        gd_bonus = 0
    return max(0, min(100, base + form_bonus + gd_bonus + (8 if home else 0)))

def day_matches(slug, dstr):
    out = []
    try:
        r = httpx.get(f"{BASE}/site/v2/sports/soccer/{slug}/scoreboard", params={"dates": dstr}, timeout=15).json()
        for ev in r.get("events", []):
            comp = ev.get("competitions", [{}])[0]
            if comp.get("status", {}).get("type", {}).get("state") != "post":
                continue
            cs = comp.get("competitors", [])
            h = next((c for c in cs if c.get("homeAway") == "home"), None)
            a = next((c for c in cs if c.get("homeAway") == "away"), None)
            if h and a and "score" in h and "score" in a:
                out.append({"home": (h.get("team") or {}).get("displayName", ""), "away": (a.get("team") or {}).get("displayName", ""), "hs": int(float(h["score"])), "as": int(float(a["score"]))})
    except Exception as ex:
        print("fx err", slug, dstr, ex)
    return out

def send(text):
    try:
        r = httpx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": text}, timeout=10)
        return r.status_code == 200
    except Exception as ex:
        print("tg err", ex)
        return False

def main():
    print("calibration start")
    ranks = standings(2024)
    start = datetime(2025, 8, 8)
    end = datetime(2025, 9, 22)
    B = [(25, 35, "25-35"), (35, 45, "35-45"), (45, 55, "45-55"), (55, 65, "55-65"), (65, 1000, "65+")]
    stats = {lab: [0, 0] for _, _, lab in B}
    total = 0
    draws = 0
    d = start
    while d <= end:
        dstr = d.strftime("%Y%m%d")
        for slug in LEAGUES:
            for m in day_matches(slug, dstr):
                hd = ranks.get(slug, {}).get(m["home"], DEFAULT_TEAM)
                ad = ranks.get(slug, {}).get(m["away"], DEFAULT_TEAM)
                hp = power(hd["rank"], hd, True)
                ap = power(ad["rank"], ad, False)
                gap = abs(hp - ap)
                if gap < 25:
                    continue
                stronger = "home" if hp > ap else "away"
                w = "home" if m["hs"] > m["as"] else ("away" if m["as"] > m["hs"] else "draw")
                total += 1
                if w == "draw":
                    draws += 1
                    continue
                for lo, hi, lab in B:
                    if lo <= gap < hi:
                        stats[lab][0] += 1
                        if w == stronger:
                            stats[lab][1] += 1
                        break
            time.sleep(0.15)
        d += timedelta(days=1)
    lines = []
    for _, _, lab in B:
        n, c = stats[lab]
        pct = round(c / n * 100) if n else 0
        lines.append(f"اختلاف {lab}: {n} بازی، برد قوی‌تر {pct}%")
    report = "📊 کالیبراسیون آستانه\n(تیم‌های تازه‌صعود = رتبه 17)\n\n" + "\n".join(lines) + f"\n\nکل بازی‌ها: {total} | مساوی: {draws}\n\nهر بازه‌ای که درصدش یهو بالا پرید، آستانه طلاییه 🏆"
    send(report)
    print(report)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        send("❌ خطای کالیبراسیون:\n" + e[-2000:])
        raise
