import httpx, os, time, traceback
from datetime import datetime, timedelta

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
BASE = "https://site.api.espn.com/apis"
LEAGUES = {"eng.1": "انگلیس", "esp.1": "اسپانیا", "ger.1": "آلمان", "ita.1": "ایتالیا", "fra.1": "فرانسه"}
MISMATCH_THRESHOLD = 55

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
                        played = int(st.get("gamesPlayed", 0))
                        t[name] = {
                            "rank": int(st.get("rank", 14)),
                            "played": played,
                            "wins": int(st.get("wins", 0)),
                            "gf": int(st.get("pointsFor", 0)),
                            "ga": int(st.get("pointsAgainst", 0)),
                        }
        except Exception as ex:
            print("st err", slug, ex)
        out[slug] = t
        time.sleep(0.2)
    return out

def power(rank, d, home):
    base = 100 - int(rank) * 3
    played = d.get("played", 0)
    if played > 0:
        win_ratio = d.get("wins", 0) / played
        form_bonus = (win_ratio - 0.4) * 15
        gf = d.get("gf", 0)
        ga = d.get("ga", 0)
        gd_per_game = (gf - ga) / played
        gd_bonus = max(-10, min(10, gd_per_game * 5))
    else:
        form_bonus = 0
        gd_bonus = 0
    home_bonus = 8 if home else 0
    return max(0, min(100, base + form_bonus + gd_bonus + home_bonus))

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
                out.append({
                    "home": (h.get("team") or {}).get("displayName", ""),
                    "away": (a.get("team") or {}).get("displayName", ""),
                    "hs": int(float(h["score"])),
                    "as": int(float(a["score"])),
                    "date": ev.get("date", "")[:10],
                })
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

def build_table_at_date(slug, final_table, current_date):
    """ساخت جدول در یک تاریخ خاص (با فیلتر نتایج تا اون روز) - ساده‌سازی"""
    return final_table

def main():
    print("backtest v2 start")
    ranks = standings(2024)
    start = datetime(2025, 8, 8)
    end = datetime(2025, 9, 22)
    total = flagged = flag_win = normal = normal_win = draws = 0
    d = start
    all_matches = []
    while d <= end:
        dstr = d.strftime("%Y%m%d")
        for slug in LEAGUES:
            for m in day_matches(slug, dstr):
                all_matches.append((slug, m, dstr))
            time.sleep(0.15)
        d += timedelta(days=1)
    
    for slug, m, _ in all_matches:
        hd = ranks.get(slug, {}).get(m["home"], {"rank": 14, "played": 10, "wins": 4, "gf": 15, "ga": 15})
        ad = ranks.get(slug, {}).get(m["away"], {"rank": 14, "played": 10, "wins": 4, "gf": 15, "ga": 15})
        hr = hd.get("rank", 14)
        ar = ad.get("rank", 14)
        hp, ap = power(hr, hd, True), power(ar, ad, False)
        gap = abs(hp - ap)
        if gap < 25:
            continue
        stronger = "home" if hp > ap else "away"
        w = "home" if m["hs"] > m["as"] else ("away" if m["as"] > m["hs"] else "draw")
        total += 1
        if w == "draw":
            draws += 1
            continue
        if gap >= MISMATCH_THRESHOLD:
            flagged += 1
            if w == stronger:
                flag_win += 1
        else:
            normal += 1
            if w == stronger:
                normal_win += 1
    
    fa = round(flag_win / flagged * 100) if flagged else 0
    na = round(normal_win / normal * 100) if normal else 0
    report = f"📊 گزارش بک‌تست v2\n(فرمول بهبودیافته، آستانه {MISMATCH_THRESHOLD})\n\nبازی بررسی‌شده: {total}\nبازی نابرابر: {flagged}\n✅ برد تیم قوی‌تر در نابرابرها: {fa}%\nبرد تیم قوی‌تر در عادی‌ها: {na}%\nمساوی: {draws}\n\nاگه fa خیلی بیشتر از na باشه، موتور عالی تبعیض می‌ده."
    send(report)
    print(report)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        send("❌ خطای بک‌تست:\n" + e[-2000:])
        raise
