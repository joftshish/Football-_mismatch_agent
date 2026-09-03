import httpx, json, os, traceback
from datetime import datetime, timedelta, timezone

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
BASE = "https://site.api.espn.com/apis"
TZ = timezone(timedelta(hours=3, minutes=30))
LEAGUES = {"eng.1": "لیگ برتر انگلیس", "esp.1": "لالیگا", "ger.1": "بوندس‌لیگا", "ita.1": "سری آ", "fra.1": "لیگ ۱ فرانسه"}
WD = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
MO = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]

MISMATCH_THRESHOLD = 55

def jalali(dt):
    try:
        import jdatetime
        j = jdatetime.datetime.fromgregorian(datetime=dt)
        return f"{WD[j.weekday()]} {j.day} {MO[j.month-1]} {j.year}", j.strftime("%H:%M")
    except Exception:
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")

def standings(season=None):
    out = {}
    for slug in LEAGUES:
        t = {}
        tries = [{"season": season, "seasontype": 1}, {"season": season}] if season else [{}]
        for p in tries:
            try:
                r = httpx.get(f"{BASE}/v2/sports/soccer/{slug}/standings", params=p, timeout=15).json()
                for ch in r.get("children", []):
                    for e in ch.get("standings", {}).get("entries", []):
                        name = (e.get("team") or {}).get("displayName", "")
                        st = {s.get("name"): s.get("value", 0) for s in e.get("stats", [])}
                        if name:
                            t[name] = {
                                "rank": int(st.get("rank", 20)),
                                "played": int(st.get("gamesPlayed", 0)),
                                "wins": int(st.get("wins", 0)),
                                "points": int(st.get("points", 0)),
                                "gf": int(st.get("pointsFor", 0)),
                                "ga": int(st.get("pointsAgainst", 0)),
                            }
                if t:
                    break
            except Exception as ex:
                print("standings err", slug, ex)
        out[slug] = t
    return out

def fixtures():
    out = []
    for i in range(5):
        d = (datetime.now(timezone.utc) + timedelta(days=i)).strftime("%Y%m%d")
        for slug, lname in LEAGUES.items():
            try:
                r = httpx.get(f"{BASE}/site/v2/sports/soccer/{slug}/scoreboard", params={"dates": d}, timeout=15).json()
                for ev in r.get("events", []):
                    cs = ev.get("competitions", [{}])[0].get("competitors", [])
                    h = next((c for c in cs if c.get("homeAway") == "home"), None)
                    a = next((c for c in cs if c.get("homeAway") == "away"), None)
                    if h and a:
                        hn = (h.get("team") or {}).get("displayName", "")
                        an = (a.get("team") or {}).get("displayName", "")
                        if hn and an:
                            out.append({"id": str(ev.get("id")), "league": lname, "slug": slug, "date": ev.get("date", ""), "home": hn, "away": an})
            except Exception as ex:
                print("fixtures err", slug, d, ex)
    return out

def power(rank, d, home):
    if isinstance(rank, dict):
        rank = rank.get("rank", 14)
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

def send(text, html=True):
    try:
        payload = {"chat_id": CHAT_ID, "text": text}
        if html:
            payload["parse_mode"] = "HTML"
        r = httpx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json=payload, timeout=10)
        print("TG status:", r.status_code, r.text[:150])
        return r.status_code == 200
    except Exception as ex:
        print("tg err", ex)
        return False

def msg(a):
    try:
        dt = datetime.fromisoformat(a["date"].replace("Z", "+00:00")).astimezone(TZ)
        jd, tm = jalali(dt)
    except Exception:
        jd, tm = a["date"], ""
    t = f"⚔️ <b>بازی نابرابر!</b>\n\n🏆 {a['league']}\n📅 {jd} — {tm}\n\n⚽ <b>{a['home']}</b> (رتبه {a['hr']}) قدرت {a['hp']}\n🆚 <b>{a['away']}</b> (رتبه {a['ar']}) قدرت {a['ap']}\n\n📊 اختلاف: <b>{a['gap']}/100</b>\n📋 {a['label']}"
    if a["low"]:
        t += "\n⚠️ داده فصل جاری کم است؛ رتبه فصل قبل مبناست"
    return t

def main():
    print("=== start ===")
    state = {}
    if os.path.exists("state.json"):
        try:
            state = json.load(open("state.json"))
        except Exception:
            state = {}
    noted = state.get("notified", [])
    now = datetime.now(timezone.utc)
    ls_year = (now.year if now.month >= 7 else now.year - 1) - 1
    fs = fixtures()
    cur = standings()
    last = standings(ls_year)
    cur_sz = {k: len(v) for k, v in cur.items()}
    last_sz = {k: len(v) for k, v in last.items()}
    print("fixtures:", len(fs), "cur:", cur_sz, "last:", last_sz)
    sent = 0
    rows = []
    for m in fs:
        t = cur.get(m["slug"], {})
        hd, ad = t.get(m["home"], {}), t.get(m["away"], {})
        h_low = hd.get("played", 0) < 5
        a_low = ad.get("played", 0) < 5
        hr = hd.get("rank", 20) if not h_low else last.get(m["slug"], {}).get(m["home"], {}).get("rank", 14)
        ar = ad.get("rank", 20) if not a_low else last.get(m["slug"], {}).get(m["away"], {}).get("rank", 14)
        hp, ap = power(hr, hd, True), power(ar, ad, False)
        gap = abs(hp - ap)
        if gap >= 80:
            lab = "کاملاً نابرابر ⚫"
        elif gap >= 65:
            lab = "به‌وضوح نابرابر 🔴"
        elif gap >= MISMATCH_THRESHOLD:
            lab = "نابرابر 🟠"
        else:
            lab = None
        rows.append((gap, f"{m['home']} - {m['away']} | {round(gap)} | {lab or '-'}"))
        if lab and m["id"] not in noted:
            a = {"league": m["league"], "date": m["date"], "home": m["home"], "away": m["away"], "hr": hr, "ar": ar, "hp": hp, "ap": ap, "gap": gap, "label": lab, "low": h_low or a_low}
            if send(msg(a)):
                noted.append(m["id"])
                sent += 1
    state["notified"] = noted
    json.dump(state, open("state.json", "w"))
    rows.sort(reverse=True)
    top = "\n".join(r[1] for r in rows[:6])
    summary = f"📊 گزارش ایجنت\nتعداد بازی‌ها: {len(fs)}\nجدول فعلی: {cur_sz}\nجدول فصل قبل: {last_sz}\nبالاترین اختلاف‌ها:\n{top}\nنوتیف فرستاده شد: {sent}"
    send(summary, html=False)
    print("=== done, sent:", sent, "===")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        try:
            httpx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": "❌ خطا:\n" + e[-2500:]}, timeout=10)
        except Exception:
            pass
        raise
