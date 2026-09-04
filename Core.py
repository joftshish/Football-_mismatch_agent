import httpx, json, math, os
from datetime import datetime, timedelta, timezone

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ESPN = "https://site.api.espn.com/apis"
POLY = "https://gamma-api.polymarket.com"
TZ = timezone(timedelta(hours=3, minutes=30))
SOCCER = {"eng.1": "🏴 لیگ برتر انگلیس", "esp.1": "🇪🇸 لالیگا", "ger.1": "🇩🇪 بوندس‌لیگا", "ita.1": "🇮🇹 سری آ", "fra.1": "🇫🇷 لیگ ۱", "por.1": "🇵🇹 پرتغال", "ksa.1": "🇸🇦 عربستان", "eng.2": "🏴 Championship", "esp.2": "🇪 Segunda"}
TENNIS = {"atp": "🎾 ATP", "wta": "🎾 WTA"}
WD = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
MO = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
MIN_EDGE = 0.03
SOCCER_GAP = 55
TENNIS_GAP = 30
DEFAULT_RANK = 17

def jalali(dt):
    try:
        import jdatetime
        j = jdatetime.datetime.fromgregorian(datetime=dt)
        return f"{WD[j.weekday()]} {j.day} {MO[j.month-1]} {j.year}", j.strftime("%H:%M")
    except Exception:
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")

def model_prob(gap):
    return min(0.92, 0.5 + gap * 0.006)

def kelly(p, price):
    if p <= price:
        return 0
    odds = 1 / price
    return max(0, min(((p * odds - 1) / (odds - 1)) * 0.015, 0.02))

def send(text, html=True):
    try:
        pl = {"chat_id": CHAT_ID, "text": text}
        if html:
            pl["parse_mode"] = "HTML"
        r = httpx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json=pl, timeout=10)
        return r.status_code == 200
    except Exception as ex:
        print("tg err", ex)
        return False

def soccer_standings(season=None):
    out = {}
    for slug in SOCCER:
        t = {}
        tries = [{"season": season, "seasontype": 1}, {"season": season}] if season else [{}]
        for p in tries:
            try:
                r = httpx.get(f"{ESPN}/v2/sports/soccer/{slug}/standings", params=p, timeout=15).json()
                for ch in r.get("children", []):
                    for e in ch.get("standings", {}).get("entries", []):
                        name = (e.get("team") or {}).get("displayName", "")
                        st = {s.get("name"): s.get("value", 0) for s in e.get("stats", [])}
                        if name:
                            t[name] = {"rank": int(st.get("rank", DEFAULT_RANK)), "played": int(st.get("gamesPlayed", 0)), "wins": int(st.get("wins", 0)), "gf": int(st.get("pointsFor", 0)), "ga": int(st.get("pointsAgainst", 0))}
                if t:
                    break
            except Exception as ex:
                print("st err", slug, ex)
        out[slug] = t
    return out

def soccer_fixtures(days=5):
    out = []
    for i in range(days):
        d = (datetime.now(timezone.utc) + timedelta(days=i)).strftime("%Y%m%d")
        for slug, lname in SOCCER.items():
            try:
                r = httpx.get(f"{ESPN}/site/v2/sports/soccer/{slug}/scoreboard", params={"dates": d}, timeout=15).json()
                for ev in r.get("events", []):
                    cs = ev.get("competitions", [{}])[0].get("competitors", [])
                    h = next((c for c in cs if c.get("homeAway") == "home"), None)
                    a = next((c for c in cs if c.get("homeAway") == "away"), None)
                    if h and a:
                        hn = (h.get("team") or {}).get("displayName", "")
                        an = (a.get("team") or {}).get("displayName", "")
                        if hn and an:
                            out.append({"id": str(ev.get("id")), "sport": "soccer", "league": lname, "slug": slug, "date": ev.get("date", ""), "home": hn, "away": an})
            except Exception as ex:
                print("fx err", slug, d, ex)
    return out

def tennis_rankings():
    out = {"atp": {}, "wta": {}}
    urls = {"atp": ["https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_rankings_current.csv", "https://raw.githubusercontent.com/Kadantte/tennis_atp/master/atp_rankings_current.csv", "https://raw.githubusercontent.com/beta2k/tennis_atp/master/atp_rankings_current.csv"], "wta": ["https://raw.githubusercontent.com/JeffSackmann/tennis_wta/master/wta_rankings_current.csv", "https://raw.githubusercontent.com/Kadantte/tennis_wta/master/wta_rankings_current.csv"]}
    for tour, lst in urls.items():
        for url in lst:
            try:
                r = httpx.get(url, timeout=15)
                if r.status_code != 200:
                    continue
                tmp = {}
                for ln in r.text.strip().splitlines()[1:]:
                    p = ln.split(",")
                    if len(p) >= 3 and p[1].strip().isdigit():
                        tmp[p[2].strip().split()[0].lower()] = int(p[1])
                if tmp:
                    out[tour] = tmp
                    break
            except Exception:
                continue
    return out

def tennis_fixtures(days=5):
    out = []
    for i in range(days):
        d = (datetime.now(timezone.utc) + timedelta(days=i)).strftime("%Y%m%d")
        for tour, lname in TENNIS.items():
            try:
                r = httpx.get(f"{ESPN}/site/v2/sports/tennis/{tour}/scoreboard", params={"dates": d}, timeout=15).json()
                for ev in r.get("events", []):
                    cs = ev.get("competitions", [{}])[0].get("competitors", [])
                    ns = [((c.get("athlete") or c.get("team") or {}).get("displayName")) or "" for c in cs]
                    if len(ns) == 2 and ns[0] and ns[1]:
                        out.append({"id": str(ev.get("id")), "sport": "tennis", "league": lname, "slug": tour, "date": ev.get("date", ""), "home": ns[0], "away": ns[1]})
            except Exception as ex:
                print("tfx err", tour, d, ex)
    return out

def soccer_power(rank, d, home):
    base = 100 - int(rank) * 3
    played = d.get("played", 0)
    if played > 0:
        fb = (d.get("wins", 0) / played - 0.4) * 15
        gb = max(-10, min(10, ((d.get("gf", 0) - d.get("ga", 0)) / played) * 5))
    else:
        fb = gb = 0
    return max(0, min(100, base + fb + gb + (8 if home else 0)))

def tennis_power(rank):
    return 100 - 30 * math.log10(max(int(rank), 1) + 1)

def keys(name, sport):
    n = name.lower().strip()
    parts = n.split()
    return [n, parts[0] if sport == "soccer" else parts[-1]]

def poly_events():
    evs = []
    for tag in ["soccer", "tennis"]:
        try:
            d = httpx.get(f"{POLY}/events", params={"closed": "false", "tag_slug": tag, "limit": 200}, timeout=15).json()
            if isinstance(d, list):
                for e in d:
                    e["_tag"] = tag
                evs += d
        except Exception as ex:
            print("poly err", tag, ex)
    return evs

def poly_prices(ev, home, away, sport):
    kh, ka = keys(home, sport), keys(away, sport)
    for mk in ev.get("markets", []):
        try:
            oc, pr = mk.get("outcomes"), mk.get("outcomePrices")
            if isinstance(oc, str):
                oc = json.loads(oc)
            if isinstance(pr, str):
                pr = json.loads(pr)
            if not oc or not pr or len(oc) != len(pr):
                continue
            ph = pa = None
            for i, o in enumerate(oc):
                ol = o.lower()
                if any(k in ol for k in kh):
                    ph = float(pr[i])
                elif any(k in ol for k in ka):
                    pa = float(pr[i])
            if ph is not None and pa is not None:
                return ph, pa
        except Exception:
            continue
    return None, None

def find_poly(evlist, home, away, sport):
    kh, ka = keys(home, sport), keys(away, sport)
    for ev in evlist:
        t = (ev.get("title") or "").lower()
        if any(h in t for h in kh) and any(a in t for a in ka):
            return ev
    return None

def load_state():
    if os.path.exists("state.json"):
        try:
            return json.load(open("state.json"))
        except Exception:
            pass
    return {}

def save_state(s):
    s["known_poly"] = s.get("known_poly", [])[-500:]
    s["notified"] = s.get("notified", [])[-500:]
    json.dump(s, open("state.json", "w"))

def notify(emoji, a):
    try:
        dt = datetime.fromisoformat(a["date"].replace("Z", "+00:00")).astimezone(TZ)
        jd, tm = jalali(dt)
    except Exception:
        jd, tm = a["date"], ""
    t = f"{emoji} <b>{a['title']}</b>\n\n🏆 {a['league']}\n📅 {jd} — ساعت {tm}\n\n{a['icon']} <b>{a['home']}</b> vs <b>{a['away']}</b>\n\n📊 مدل ما: {round(a['prob']*100)}% برد {a['stronger']}\n💰 بازار Polymarket: {round(a['price']*100)}%\n📈 لبه: {round(a['edge']*100,1)}%"
    if a.get("kelly"):
        t += f"\n💵 پیشنهاد Kelly: {round(a['kelly']*100,1)}% سرمایه"
    t += f"\n📋 {a['label']}"
    if a.get("note"):
        t += f"\n{a['note']}"
    return send(t)
