import httpx, json, math, os, unicodedata
from datetime import datetime, timedelta, timezone

VERSION = "core22"
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ESPN = "https://site.api.espn.com/apis"
POLY = "https://gamma-api.polymarket.com"
TZ = timezone(timedelta(hours=3, minutes=30))
FAD = "".join(chr(1632 + i) for i in range(10))
SOCCER = {"eng.1": "🏴 لیگ برتر انگلیس", "esp.1": "🇪🇸 لالیگا", "ger.1": "🇩🇪 بوندس‌لیگا", "ita.1": "🇮🇹 سری آ", "fra.1": "🇫🇷 لیگ ۱", "por.1": "🇵🇹 پرتغال", "ksa.1": "🇸🇦 عربستان", "eng.2": "🏴 Championship", "esp.2": "🇪🇸 Segunda", "usa.1": "🇺🇸 MLS", "bra.1": "🇧🇷 برزیل", "mex.1": "🇲🇽 مکزیک", "ned.1": "🇳🇱 هلند", "tur.1": "🇹🇷 ترکیه", "jpn.1": "🇯🇵 ژاپن", "ger.2": "🇩🇪 بوندس‌لیگا۲", "ita.2": "🇮 سری B", "eng.3": "🏴 League One", "fra.2": "🇫🇷 لیگ ۲", "arg.1": "🇦🇷 آرژانتین", "uefa.champions": "🇪🇺 لیگ قهرمانان اروپا", "uefa.europa": "🇪🇺 لیگ اروپا"}
VOLATILE = {"eng.2", "eng.3", "esp.2", "fra.2", "ita.2", "ger.2"}
OFF = {"eng.1": 0, "esp.1": 0, "ger.1": 0, "ita.1": 0, "fra.1": 1, "por.1": 4, "bra.1": 4, "ned.1": 5, "arg.1": 5, "tur.1": 6, "ksa.1": 6, "mex.1": 6, "usa.1": 7, "jpn.1": 7, "eng.2": 8, "esp.2": 8, "ger.2": 8, "ita.2": 8, "fra.2": 8, "eng.3": 12}
TENNIS = {"atp": "🎾 ATP", "wta": "🎾 WTA"}
WD = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
MO = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
STOP = {"city", "united", "fc", "sc", "ac", "athletic", "real", "club", "sporting", "county", "town", "rovers", "rangers", "wanderers", "albion", "forest", "north", "south", "east", "west", "dynamo", "nacional", "atletico", "inter", "union", "racing", "stars", "red", "white", "black"}
MIN_EDGE = 0.03
MAX_EDGE = 0.20
SOCCER_GAP = 45
CROSS_GAP = 35
TENNIS_GAP = 30
DEFAULT_RANK = 17

def fa(x):
    return "".join(FAD[int(ch)] if ch.isdigit() else ch for ch in str(x))

def norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", (s or "").lower()) if not unicodedata.combining(c))

def jalali(dt):
    try:
        import jdatetime
        j = jdatetime.datetime.fromgregorian(datetime=dt)
        return f"{WD[j.weekday()]} {j.day} {MO[j.month-1]} {j.year}", j.strftime("%H:%M")
    except Exception:
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")

def model_prob(gap, soft=False):
    if soft:
        if gap >= 55:
            return 0.85
        if gap >= 45:
            return 0.80
        if gap >= 35:
            return 0.75
        if gap >= 25:
            return 0.68
        return 0.60
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
                        pts_raw = st.get("points")
                        if name:
                            t[name] = {"rank": int(st.get("rank", DEFAULT_RANK)), "played": int(st.get("gamesPlayed", 0)), "wins": int(st.get("wins", 0)), "gf": int(st.get("pointsFor", 0)), "ga": int(st.get("pointsAgainst", 0)), "pts": int(pts_raw) if pts_raw not in (None, "") else None}
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
    urls = {"atp": ["https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_rankings_current.csv", "https://raw.githubusercontent.com/Kadantte/tennis_atp/master/atp_rankings_current.csv", "https://raw.githubusercontent.com/beta2k/tennis_atp/master/atp_rankings_current.csv"], "wta": ["https://raw.githubusercontent.com/JeffSackmann/tennis_wta/master/wta_rankings_current.csv", "https://raw.githubusercontent.com/Kadantte/tennis_wta/master/wta_rankings_current.csv", "https://raw.githubusercontent.com/beta2k/tennis_wta/master/wta_rankings_current.csv"]}
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

def tennis_names(cs):
    ns = []
    for c in cs:
        ath = c.get("athlete") or c.get("team") or {}
        name = ath.get("displayName") or ath.get("fullName") or ath.get("shortDisplayName") or ""
        if name:
            ns.append(name)
    return ns

def tennis_fixtures(days=5):
    out = []
    for tour, lname in TENNIS.items():
        got = []
        for i in range(days):
            d = (datetime.now(timezone.utc) + timedelta(days=i)).strftime("%Y%m%d")
            try:
                r = httpx.get(f"{ESPN}/site/v2/sports/tennis/{tour}/scoreboard", params={"dates": d}, timeout=15).json()
                for ev in r.get("events", []):
                    ns = tennis_names(ev.get("competitions", [{}])[0].get("competitors", []))
                    if len(ns) >= 2:
                        got.append({"id": str(ev.get("id")), "sport": "tennis", "league": lname, "slug": tour, "date": ev.get("date", ""), "home": ns[0], "away": ns[1]})
            except Exception as ex:
                print("tfx err", tour, d, ex)
        if not got:
            try:
                r = httpx.get(f"{ESPN}/site/v2/sports/tennis/{tour}/scoreboard", timeout=15).json()
                for ev in r.get("events", []):
                    ns = tennis_names(ev.get("competitions", [{}])[0].get("competitors", []))
                    if len(ns) >= 2:
                        got.append({"id": str(ev.get("id")), "sport": "tennis", "league": lname, "slug": tour, "date": ev.get("date", ""), "home": ns[0], "away": ns[1]})
            except Exception as ex:
                print("tfx2 err", tour, ex)
        out += got
    return out

def tennis_probe():
    try:
        r = httpx.get(f"{ESPN}/site/v2/sports/tennis/atp/scoreboard", timeout=15)
        d = r.json()
        evs = d.get("events", [])
        if not evs:
            return "events=0"
        for ev in evs[:3]:
            cs = ev.get("competitions", [{}])[0].get("competitors", [])
            if cs:
                return f"comp_keys={list(cs[0].keys())[:8]} | ath_keys={list((cs[0].get('athlete') or {}).keys())[:6]}"
        return "raw=" + json.dumps(evs[0], ensure_ascii=False)[:250]
    except Exception as ex:
        return f"err: {ex}"

def boost_of(d, eff_rank):
    played = d.get("played", 0)
    pts = d.get("pts")
    if not played or pts is None:
        return None
    actual = pts / played
    expected = 2.2 - (eff_rank - 1) * 0.068
    return actual - expected

def tennis_power(rank):
    return 100 - 30 * math.log10(max(int(rank), 1) + 1)

def keys(name, sport):
    n = norm(name).strip()
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
        t = norm(ev.get("title") or "")
        if any(h in t for h in kh) and any(a in t for a in ka):
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
            q = norm((mk.get("question") or "") + " " + (mk.get("groupItemTitle") or ""))
            for i, o in enumerate(oc):
                ol = norm(o)
                if ol in ("yes", "no", "draw"):
                    continue
                pv = float(pr[i])
                if pv < 0.02 or pv > 0.98:
                    continue
                if any(k in ol for k in kh):
                    ph = pv
                elif any(k in ol for k in ka):
                    pa = pv
            if len(oc) == 2 and str(oc[0]).lower() == "yes":
                mh = any(k in q for k in kh)
                ma = any(k in q for k in ka)
                yesp = None
                if mk.get("bestAsk") is not None:
                    try:
                        ba = float(mk.get("bestAsk"))
                        if 0.02 <= ba <= 0.98:
                            yesp = ba
                    except Exception:
                        yesp = None
                else:
                    p0 = float(pr[0])
                    if 0.02 <= p0 <= 0.98:
                        yesp = p0
                if yesp is None:
                    continue
                if mh and not ma and ph is None:
                    ph = yesp
                elif ma and not mh and pa is None:
                    pa = yesp
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
        t = norm(ev.get("title") or "")
        if any(h in t for h in kh) and any(a in t for a in ka):
            return ev
    return None

def cross_info(name, cur, last):
    for tbl in (cur, last):
        for slug, t in tbl.items():
            if slug.startswith("uefa."):
                continue
            if name in t:
                d = t[name]
                return min(24, OFF.get(slug, 10) + d.get("rank", DEFAULT_RANK) - 1), d
    return 18, {}

def compute(m, cur, last, tr):
    solid = False
    rsrc = "cur"
    hr = ar = None
    hcr = hlr = acr = alr = None
    bh = ba = None
    detail = None
    cross = m["sport"] == "soccer" and m["slug"].startswith("uefa.")
    if m["sport"] == "soccer":
        if cross:
            ehr, hd = cross_info(m["home"], cur, last)
            ear, ad = cross_info(m["away"], cur, last)
            hcr, acr = ehr, ear
            hlr = alr = None
            h_played = hd.get("played", 0)
            a_played = ad.get("played", 0)
            bh = boost_of(hd, ehr)
            ba = boost_of(ad, ear)
            early = True
            mult, fbw, gbw, gbc, home_b = 3, 25, 8, 15, 6
            def comps_x(eff_rank, d):
                base = 100 - eff_rank * mult
                played = d.get("played", 0)
                if played:
                    fb = (d.get("wins", 0) / played - 0.4) * fbw
                    gb = max(-gbc, min(gbc, ((d.get("gf", 0) - d.get("ga", 0)) / played) * gbw))
                else:
                    fb = gb = 0
                return base, fb, gb
            base_h, fb_h, gb_h = comps_x(ehr, hd)
            base_a, fb_a, gb_a = comps_x(ear, ad)
            hp = max(0, min(100, base_h + fb_h + gb_h + home_b))
            ap = max(0, min(100, base_a + fb_a + gb_a))
            detail = {"mult": mult, "fbw": fbw, "gbw": gbw, "gbc": gbc, "early": early, "soft": True, "cross": True, "h": {"cr": hcr, "lr": None, "eff": ehr, "base": round(base_h, 1), "fb": round(fb_h, 1), "gb": round(gb_h, 1), "home": home_b, "power": round(hp, 1), "boost": bh}, "a": {"cr": acr, "lr": None, "eff": ear, "base": round(base_a, 1), "fb": round(fb_a, 1), "gb": round(gb_a, 1), "home": 0, "power": round(ap, 1), "boost": ba}}
            hr, ar = ehr, ear
            rsrc = "cross"
            solid = False
            low = True
        else:
            t = cur.get(m["slug"], {})
            hd, ad = t.get(m["home"], {}), t.get(m["away"], {})
            lh = last.get(m["slug"], {}).get(m["home"], {})
            la = last.get(m["slug"], {}).get(m["away"], {})
            h_played = hd.get("played", 0)
            a_played = ad.get("played", 0)
            h_cur = h_played >= 5
            a_cur = a_played >= 5
            if h_cur != a_cur:
                return None
            hcr = hd.get("rank") if h_cur else None
            acr = ad.get("rank") if a_cur else None
            hlr = lh.get("rank")
            alr = la.get("rank")
            def eff(cr, lr, played):
                if cr is None and lr is None:
                    return float(DEFAULT_RANK)
                if cr is None:
                    return float(lr)
                if lr is None:
                    w = min(1.0, played / 15.0)
                    return cr * w + DEFAULT_RANK * (1 - w)
                w = min(1.0, played / 12.0)
                return cr * w + lr * (1 - w)
            ehr = eff(hcr, hlr, h_played)
            ear = eff(acr, alr, a_played)
            bh = boost_of(hd, ehr)
            ba = boost_of(ad, ear)
            early = min(h_played, a_played) < 8
            soft = early or m["slug"] in VOLATILE
            mult = 2 if soft else 3
            fbw = 25 if soft else 15
            gbw = 8 if soft else 5
            gbc = 15 if soft else 10
            home_b = 6 if soft else 8
            def comps(eff_rank, d):
                base = 100 - eff_rank * mult
                played = d.get("played", 0)
                if played:
                    fb = (d.get("wins", 0) / played - 0.4) * fbw
                    gb = max(-gbc, min(gbc, ((d.get("gf", 0) - d.get("ga", 0)) / played) * gbw))
                else:
                    fb = gb = 0
                return base, fb, gb
            base_h, fb_h, gb_h = comps(ehr, hd)
            base_a, fb_a, gb_a = comps(ear, ad)
            hp = max(0, min(100, base_h + fb_h + gb_h + home_b))
            ap = max(0, min(100, base_a + fb_a + gb_a))
            detail = {"mult": mult, "fbw": fbw, "gbw": gbw, "gbc": gbc, "early": early, "soft": soft, "h": {"cr": hcr, "lr": hlr, "eff": round(ehr, 1), "base": round(base_h, 1), "fb": round(fb_h, 1), "gb": round(gb_h, 1), "home": home_b, "power": round(hp, 1), "boost": bh}, "a": {"cr": acr, "lr": alr, "eff": round(ear, 1), "base": round(base_a, 1), "fb": round(fb_a, 1), "gb": round(gb_a, 1), "home": 0, "power": round(ap, 1), "boost": ba}}
            hr = int(round(ehr))
            ar = int(round(ear))
            if h_cur and hlr:
                rsrc = "blend"
            elif h_cur:
                rsrc = "cur"
            else:
                rsrc = "last"
            solid = (h_cur and a_cur and h_played >= 8 and a_played >= 8) or ((not h_cur) and (not a_cur) and lh.get("played", 0) >= 20 and la.get("played", 0) >= 20)
            low = not (h_cur and a_cur)
    else:
        hr = tr.get(m["slug"], {}).get(m["home"].lower().split()[-1])
        ar = tr.get(m["slug"], {}).get(m["away"].lower().split()[-1])
        if not hr or not ar:
            return None
        hp, ap = tennis_power(hr), tennis_power(ar)
        low = False
        solid = True
        rsrc = "rank"
    gap = abs(hp - ap)
    if cross:
        thr = CROSS_GAP
    elif m["sport"] == "soccer":
        thr = SOCCER_GAP
    else:
        thr = TENNIS_GAP
    if gap < thr:
        return None
    sh = hp > ap
    soft = bool(detail and detail.get("soft")) if detail else False
    prob = model_prob(gap, soft or cross)
    if cross or (m["sport"] == "soccer" and min(hd.get("played", 0), ad.get("played", 0)) < 8):
        prob = min(prob, 0.80)
    return {"gap": gap, "thr": thr, "stronger": m["home"] if sh else m["away"], "sh": sh, "prob": prob, "low": low, "solid": solid, "hr": hr, "ar": ar, "rsrc": rsrc, "hcr": hcr, "hlr": hlr, "acr": acr, "alr": alr, "bh": bh, "ba": ba, "detail": detail, "cross": cross}

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
    s["last_links"] = s.get("last_links", [])[-10:]
    json.dump(s, open("state.json", "w"))

def rank_of(cr, lr):
    def rr(x):
        return fa(x) if x else "—"
    return f"جاری {rr(cr)}، قبل {rr(lr)}"

def btag(b):
    if b is None:
        return "—"
    if b >= 0.5:
        return f"🚀 {fa(round(b,2))} بالاتر از انتظار"
    if b <= -0.5:
        return f"📉 {fa(round(abs(b),2))} پایین‌تر از انتظار"
    return f"➖ {fa(round(abs(b),2))} نزدیک انتظار"

def notify(emoji, a):
    try:
        dt = datetime.fromisoformat(a["date"].replace("Z", "+00:00")).astimezone(TZ)
        jd, tm = jalali(dt)
    except Exception:
        jd, tm = a["date"], ""
    L = [f"{emoji} <b>{a['title']}</b>", "", f"🏆 لیگ: {a['league']}", f"📅 {jd} — ساعت {tm}", "", f"⚽ {a['home']}", f"🆚 {a['away']}"]
    if a.get("hcr") is not None or a.get("hlr") is not None:
        L += ["", "🏅 رتبه‌ها:", f"   {a['home']}: {rank_of(a.get('hcr'), a.get('hlr'))}", f"   {a['away']}: {rank_of(a.get('acr'), a.get('alr'))}"]
    elif a.get("hr") is not None:
        src = {"cur": "فصل جاری", "last": "فصل قبل", "rank": "رنکینگ جهانی", "blend": "ترکیب جاری و قبل", "cross": "معادل اروپایی"}.get(a.get("rsrc"), "")
        L += ["", "🏅 رتبه‌ها:", f"   {a['home']}: {fa(a['hr'])} ({src})", f"   {a['away']}: {fa(a['ar'])} ({src})"]
    if a.get("bh") is not None or a.get("ba") is not None:
        L += ["", "⚡ فرم نسبت به انتظار:", f"   {a['home']}: {btag(a.get('bh'))}", f"   {a['away']}: {btag(a.get('ba'))}"]
    L += ["", f"📊 نظر مدل: {fa(round(a['prob']*100))}٪ برد {a['stronger']}", f"💰 نظر بازار: {fa(round(a['price']*100))}٪ برد {a['stronger']}", f"📈 لبه: {fa(round(a['edge']*100,1))}٪"]
    if a.get("kelly"):
        L.append(f"💵 پیشنهاد Kelly: {fa(round(a['kelly']*100,1))}٪ سرمایه")
    L += ["", f"📋 {a['label']}"]
    if a.get("note"):
        L.append(a["note"])
    if a.get("link"):
        L += ["", "🔗 لینک بت:", a["link"]]
    return send("\n".join(L))

def notify_watch(m, c):
    try:
        dt = datetime.fromisoformat(m["date"].replace("Z", "+00:00")).astimezone(TZ)
        jd, tm = jalali(dt)
    except Exception:
        jd, tm = m["date"], ""
    icon = "🎾" if m["sport"] == "tennis" else "⚽"
    L = ["👀 <b>بازی نابرابر — منتظر بازار Polymarket</b>", "", f"🏆 لیگ: {m['league']}", f"📅 {jd} — ساعت {tm}", "", f"{icon} {m['home']}", f"🆚 {m['away']}"]
    if c.get("hcr") is not None or c.get("hlr") is not None:
        L += ["", "🏅 رتبه‌ها:", f"   {m['home']}: {rank_of(c.get('hcr'), c.get('hlr'))}", f"   {m['away']}: {rank_of(c.get('acr'), c.get('alr'))}"]
    if c.get("bh") is not None or c.get("ba") is not None:
        L += ["", "⚡ فرم نسبت به انتظار:", f"   {m['home']}: {btag(c.get('bh'))}", f"   {m['away']}: {btag(c.get('ba'))}"]
    L += ["", f"📊 نظر مدل: {fa(round(c['prob']*100))}٪ برد {c['stronger']}", "💰 بازار: هنوز باز نشده", "", "⏰ Fast Scan هر ۵ دقیقه چک می‌کنه؛ به محض باز شدن، نوتیف ⚡ با لینک می‌گیری"]
    return send("\n".join(L))

def _f(x):
    try:
        return float(x)
    except Exception:
        return None

def market_stats(ev, home, away, sport):
    kh, ka = keys(home, sport), keys(away, sport)
    mks = get_markets(ev)
    pick = None
    for mk in mks:
        try:
            oc = mk.get("outcomes")
            if isinstance(oc, str):
                oc = json.loads(oc)
            if not (len(oc or []) == 2 and str(oc[0]).lower() == "yes"):
                continue
            q = norm((mk.get("question") or "") + " " + (mk.get("groupItemTitle") or ""))
            if any(k in q for k in kh) or any(k in q for k in ka):
                pick = mk
                break
        except Exception:
            continue
    if pick is None and mks:
        pick = mks[0]
    if not pick:
        return {"vol": 0.0, "liq": 0.0, "bid": None, "ask": None}
    return {"vol": _f(pick.get("volumeNum")) or 0.0, "liq": _f(pick.get("liquidityNum")) or 0.0, "bid": _f(pick.get("bestBid")), "ask": _f(pick.get("bestAsk"))}

def liq_stage(liq):
    if liq < 1500:
        return "thin"
    if liq < 15000:
        return "grow"
    return "deep"

STAGE_FA = {"thin": "🫧 خام (قیمت کشف‌نشده)", "grow": "🌊 در حال رشد (همگرایی)", "deep": "🏊 عمیق (کارا — زمان خروج)"}
