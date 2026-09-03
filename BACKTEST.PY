import httpx, os, time, traceback
from datetime import datetime, timedelta

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
BASE = "https://site.api.espn.com/apis"
LEAGUES = {"eng.1": "انگلیس", "esp.1": "اسپانیا", "ger.1": "آلمان", "ita.1": "ایتالیا", "fra.1": "فرانسه"}

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
                        t[name] = int(st.get("rank", 14))
        except Exception as ex:
            print("st err", slug, ex)
        out[slug] = t
        time.sleep(0.2)
    return out

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

def power(rank, home):
    return 100 - int(rank) * 3 + (8 if home else 0)

def send(text):
    try:
        r = httpx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": text}, timeout=10)
        return r.status_code == 200
    except Exception as ex:
        print("tg err", ex)
        return False

def main():
    print("backtest start")
    ranks = standings(2024)
    start = datetime(2025, 8, 8)
    end = datetime(2025, 9, 22)
    total = flagged = flag_win = normal = normal_win = draws = 0
    d = start
    while d <= end:
        dstr = d.strftime("%Y%m%d")
        for slug in LEAGUES:
            for m in day_matches(slug, dstr):
                hr = ranks.get(slug, {}).get(m["home"], 14)
                ar = ranks.get(slug, {}).get(m["away"], 14)
                hp, ap = power(hr, True), power(ar, False)
                gap = abs(hp - ap)
                if gap < 25:
                    continue
                stronger = "home" if hp > ap else "away"
                w = "home" if m["hs"] > m["as"] else ("away" if m["as"] > m["hs"] else "draw")
                total += 1
                if w == "draw":
                    draws += 1
                    continue
                if gap >= 45:
                    flagged += 1
                    if w == stronger:
                        flag_win += 1
                else:
                    normal += 1
                    if w == stronger:
                        normal_win += 1
            time.sleep(0.15)
        d += timedelta(days=1)
    fa = round(flag_win / flagged * 100) if flagged else 0
    na = round(normal_win / normal * 100) if normal else 0
    report = f"📊 گزارش بک‌تست\n(۶ هفته اول فصل قبل)\n\nبازی بررسی‌شده: {total}\nبازی نابرابر: {flagged}\n✅ برد تیم قوی‌تر در نابرابرها: {fa}%\nبرد تیم قوی‌تر در عادی‌ها: {na}%\nمساوی: {draws}\n\nاگه درصد نابرابرها بالا باشه، موتور درست کار می‌کنه."
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
