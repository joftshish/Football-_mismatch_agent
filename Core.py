import httpx, json, math, os
from datetime import datetime, timedelta, timezone

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ESPN = "https://site.api.espn.com/apis"
POLY = "https://gamma-api.polymarket.com"
TZ = timezone(timedelta(hours=3, minutes=30))
SOCCER = {"eng.1": "🏴 لیگ برتر انگلیس", "esp.1": "🇪🇸 لالیگا", "ger.1": "🇩🇪 بوندس‌لیگا", "ita.1": "🇮🇹 سری آ", "fra.1": "🇫 لیگ ۱", "por.1": "🇵🇹 پرتغال", "ksa.1": "🇸 عربستان", "eng.2": "🏴 Championship", "esp.2": "🇪🇸 Segunda"}
TENNIS = {"atp": "🎾 ATP", "wta": "🎾 WTA"}
WD = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
MO = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
STOP = {"city", "united", "fc", "sc", "ac", "athletic", "real", "club", "sporting", "county", "town", "rovers", "rangers", "wanderers", "albion", "forest", "north", "south", "east", "west", "dynamo", "nacional", "atletico", "inter", "union", "racing", "stars", "red", "white", "black"}
MIN_EDGE = 0.03
SOCCER_GAP = 45
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
    if gap >= 55:
        return 0.92
    if gap >= 45:
        return 0.90
    if gap >= 35:
        return 0.84
    if gap >= 25:
        return 0.75
    return 0.65

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

def same_day(d1, d2):
    try:
        a = datetime.fromisoformat(d1.replace("Z", "+00:00"))
        b = datetime.fromisoformat(d2.replace("Z", "+00:00"))
        return abs((a - b).total_seconds()) < 30 * 3600
    except Exception:
        return True

def is_closed(x):
    return x.get("closed") in (True, "true")

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
    ks = [n]
    for p in parts:
        if p not in STOP and len(p) >= 4:
            ks.append(p)
    out = []
    for k in ks:
        if k not in out:
            out.append(k)
    return out

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

def search_poly(home, away, sport, date=""):
    kh, ka = keys(home, sport), keys(away, sport)
    toks = [k for k in (ka + kh) if len(k) >= 5 and " " not in k]
    q = toks[0] if toks else away
    try:
        d = httpx.get(f"{POLY}/public-search", params={"q": q, "limit": 20}, timeout=15).json()
    except Exception:
        return None, ""
    evs = d.get("events") or (d.get("data") or {}).get("events") or []
    for ev in evs:
        if is_closed(ev):
            continue
        t = (ev.get("title") or "").lower()
        if any(h in t for h in kh) and any(a in t for a in ka) and same_day(ev.get("startDate") or "", date):
            ev["_tag"] = sport
            return ev, ""
    return None, json.dumps(d, ensure_ascii=False)[:200]

def get_markets(ev):
    mks = ev.get("markets") or []
    if not mks:
        try:
            d = httpx.get(f"{POLY}/markets", params={"event_id": ev.get("id")}, timeout=15).json()
            if isinstance(d, list):
                mks = d
        except Exception:
            mks = []
    return [m for m in mks if not is_closed(m)]

def poly_prices(ev, home, away, sport):
    kh, ka = keys(home, sport), keys(away, sport)
    ph = pa = None
    for mk in get_markets(ev):
        try:
            oc, pr = mk.get("outcomes"), mk.get("outcomePrices")
            if isinstance(oc, str):
                oc = json.loads(oc)
            if isinstance(pr, str):
                pr = json.loads(pr)
            if not oc or not pr or len(oc) != len(pr):
                continue
            if set(str(x) for x in pr) <= {"0", "1"}:
                continue
            q = ((mk.get("question") or "") + " " + (mk.get("groupItemTitle") or "")).lower()
            for i, o in enumerate(oc):
                ol = str(o).lower()
                if ol in ("yes", "no", "draw"):
                    continue
                if any(k in ol for k in kh):
                    ph = float(pr[i])
                elif any(k in ol for k in ka):
                    pa = float(pr[i])
            if len(oc) == 2 and str(oc[0]).lower() == "yes":
                mh = any(k in q for k in kh)
                ma = any(k in q for k in ka)
                if mh and not ma and ph is None:
                    ph = float(pr[0])
                elif ma and not mh and pa is None:
                    pa = float(pr[0])
        except Exception:
            continue
        if ph is not None and pa is not None:
            return ph, pa
    return None, None

def poly_link(ev):
    s = ev.get("slug") or ""
    return f"https://polymarket.com/event/{s}" if s else None

def find_poly(evlist, home, away, sport, date=""):
    kh, ka = keys(home, sport), keys(away, sport)
    for ev in evlist:
        if is_closed(ev):
            continue
        t = (ev.get("title") or "").lower()
        if any(h in t for h in kh) and any(a in t for a in ka) and same_day(ev.get("startDate") or "", date):
            return ev
    return None

def compute(m, cur, last, tr):
    if m["sport"] == "soccer":
        t = cur.get(m["slug"], {})
        hd, ad = t.get(m["home"], {}), t.get(m["away"], {})
        h_cur = hd.get("played", 0) >= 5
        a_cur = ad.get("played", 0) >= 5
        if h_cur != a_cur:
            return None
        hr = hd.get("rank", DEFAULT_RANK) if h_cur else last.get(m["slug"], {}).get(m["home"], {}).get("rank", DEFAULT_RANK)
        ar = ad.get("rank", DEFAULT_RANK) if a_cur else last.get(m["slug"], {}).get(m["away"], {}).get("rank", DEFAULT_RANK)
        hp, ap = soccer_power(hr, hd, True), soccer_power(ar, ad, False)
        low = not (h_cur and a_cur)
    else:
        hr = tr.get(m["slug"], {}).get(m["home"].lower().split()[-1])
        ar = tr.get(m["slug"], {}).get(m["away"].lower().split()[-1])
        if not hr or not ar:
            return None
        hp, ap = tennis_power(hr), tennis_power(ar)
        low = False
    gap = abs(hp - ap)
    thr = SOCCER_GAP if m["sport"] == "soccer" else TENNIS_GAP
    if gap < thr:
        return None
    sh = hp > ap
    return {"gap": gap, "thr": thr, "stronger": m["home"] if sh else m["away"], "sh": sh, "prob": model_prob(gap), "low": low}

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
    s["watch_noted"] = s.get("watch_noted", [])[-300:]
    s["watchlist"] = s.get("watchlist", [])[-100:]
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
    if a.get("link"):
        t += f"\n\n🔗 <a href=\"{a['link']}\">باز کردن مستقیم بت در Polymarket</a>"
    return send(t)

def notify_watch(m, c):
    try:
        dt = datetime.fromisoformat(m["date"].replace("Z", "+00:00")).astimezone(TZ)
        jd, tm = jalali(dt)
    except Exception:
        jd, tm = m["date"], ""
    icon = "🎾" if m["sport"] == "tennis" else "⚽"
    t = f"👀 <b>بازی نابرابر — منتظر بازار Polymarket</b>\n\n🏆 {m['league']}\n📅 {jd} — ساعت {tm}\n\n{icon} <b>{m['home']}</b> vs <b>{m['away']}</b>\n\n📊 مدل: {round(c['prob']*100)}% برد {c['stronger']}\n💰 بازار: هنوز باز نشده\n\n⏰ Fast Scan هر 5 دقیقه چک می‌کنه؛ به محض باز شدن، نوتیف ⚡ با لینک مستقیم می‌گیری"
    return send(t)
