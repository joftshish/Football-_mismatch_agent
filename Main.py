import httpx, json, os, traceback, math
from datetime import datetime, timedelta, timezone

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ESPN_BASE = "https://site.api.espn.com/apis"
POLYMARKET_API = "https://gamma-api.polymarket.com"
TZ = timezone(timedelta(hours=3, minutes=30))

# لیگ‌ها (7 تا فعلی + 2 تا جدید)
LEAGUES = {
    "eng.1": "🏴󠁥󠁧 لیگ برتر انگلیس",
    "esp.1": "🇪🇸 لالیگا",
    "ger.1": "🇩🇪 بوندس‌لیگا",
    "ita.1": "🇮🇹 سری آ",
    "fra.1": "🇫🇷 لیگ ۱ فرانسه",
    "por.1": "🇵🇹 لیگ پرتغال",
    "ksa.1": "🇸🇦 لیگ عربستان",
    "eng.2": "🏴󠁥󠁧 Championship انگلیس",
    "esp.2": "🇪🇸 Segunda اسپانیا",
}

WD = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
MO = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]

# تنظیمات استراتژی کم‌ریسک
MISMATCH_THRESHOLD = 55
MIN_PLAYED = 5
DEFAULT_RANK = 17
MIN_EDGE = 0.03  # حداقل 3% لبه (کم‌ریسک)
KELLY_FRACTION = 0.015  # 1.5% سرمایه

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
                r = httpx.get(f"{ESPN_BASE}/v2/sports/soccer/{slug}/standings", params=p, timeout=15).json()
                for ch in r.get("children", []):
                    for e in ch.get("standings", {}).get("entries", []):
                        name = (e.get("team") or {}).get("displayName", "")
                        st = {s.get("name"): s.get("value", 0) for s in e.get("stats", [])}
                        if name:
                            t[name] = {"rank": int(st.get("rank", DEFAULT_RANK)), "played": int(st.get("gamesPlayed", 0)), "wins": int(st.get("wins", 0)), "gf": int(st.get("pointsFor", 0)), "ga": int(st.get("pointsAgainst", 0))}
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
                r = httpx.get(f"{ESPN_BASE}/site/v2/sports/soccer/{slug}/scoreboard", params={"dates": d}, timeout=15).json()
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
        rank = rank.get("rank", DEFAULT_RANK)
    base = 100 - int(rank) * 3
    played = d.get("played", 0)
    if played > 0:
        form_bonus = (d.get("wins", 0) / played - 0.4) * 15
        gd_bonus = max(-10, min(10, ((d.get("gf", 0) - d.get("ga", 0)) / played) * 5))
    else:
        form_bonus = 0
        gd_bonus = 0
    return max(0, min(100, base + form_bonus + gd_bonus + (8 if home else 0)))

def get_polymarket_price(team_name):
    """دریافت قیمت Polymarket برای یک تیم"""
    try:
        # سرچ مارکت‌های فوتبال
        r = httpx.get(f"{POLYMARKET_API}/markets", params={"active": "true", "closed": "false"}, timeout=10)
        markets = r.json()
        
        for market in markets:
            title = market.get("question", "").lower()
            if team_name.lower() in title and "vs" in title:
                # پیدا کردن قیمت YES
                outcomes = market.get("outcomes", "")
                prices = market.get("outcomePrices", "")
                if outcomes and prices:
                    try:
                        outcomes_list = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
                        prices_list = json.loads(prices) if isinstance(prices, str) else prices
                        for i, outcome in enumerate(outcomes_list):
                            if team_name.lower() in outcome.lower():
                                return float(prices_list[i])
                    except Exception:
                        pass
        return None
    except Exception as ex:
        print("polymarket err:", ex)
        return None

def kelly_criterion(prob, price):
    """محاسبه Kelly fraction برای سایز بت"""
    if prob <= price:
        return 0
    edge = prob - price
    odds = 1 / price
    kelly = (prob * odds - 1) / (odds - 1)
    return max(0, min(kelly * KELLY_FRACTION, 0.02))  # حداکثر 2%

def send(text, html=True):
    try:
        payload = {"chat_id": CHAT_ID, "text": text}
        if html:
            payload["parse_mode"] = "HTML"
        r = httpx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json=payload, timeout=10)
        return r.status_code == 200
    except Exception as ex:
        print("tg err", ex)
        return False

def msg_value_bet(a):
    """پیام برای Value Bet (بازی نابرابر + قیمت ارزون)"""
    try:
        dt = datetime.fromisoformat(a["date"].replace("Z", "+00:00")).astimezone(TZ)
        jd, tm = jalali(dt)
    except Exception:
        jd, tm = a["date"], ""
    
    kelly_pct = round(a["kelly"] * 100, 1)
    edge_pct = round(a["edge"] * 100, 1)
    model_pct = round(a["model_prob"] * 100)
    market_pct = round(a["market_price"] * 100)
    
    t = f"💰 <b>VALUE BET تشخیص داده شد!</b>\n\n🏆 {a['league']}\n📅 {jd} — ساعت {tm}\n\n⚽ <b>{a['home']}</b> vs <b>{a['away']}</b>\n\n📊 تحلیل:\n  مدل ما: {model_pct}% برد {a['stronger']}\n  بازار: {market_pct}%\n  لبه: <b>+{edge_pct}%</b> ✅\n\n💵 پیشنهاد Kelly: {kelly_pct}% سرمایه\n📋 وضعیت: {a['label']}"
    
    if a["low"]:
        t += "\n⚠️ داده فصل جاری کم است"
    return t

def msg_mismatch_only(a):
    """پیام برای بازی نابرابر (بدون value bet)"""
    try:
        dt = datetime.fromisoformat(a["date"].replace("Z", "+00:00")).astimezone(TZ)
        jd, tm = jalali(dt)
    except Exception:
        jd, tm = a["date"], ""
    
    model_pct = round(a["model_prob"] * 100)
    market_pct = round(a["market_price"] * 100) if a["market_price"] else "—"
    
    t = f"⚔️ <b>بازی نابرابر</b>\n\n🏆 {a['league']}\n📅 {jd} — ساعت {tm}\n\n⚽ <b>{a['home']}</b> vs <b>{a['away']}</b>\n\n📊 مدل: {model_pct}% برد {a['stronger']}\n💰 بازار: {market_pct}%\n📋 وضعیت: {a['label']}"
    
    if a["low"]:
        t += "\n⚠️ داده فصل جاری کم است"
    if a["market_price"] and a["edge"] < MIN_EDGE:
        t += f"\n❌ لبه کم ({round(a['edge']*100,1)}%) - ارزش بستن ندارد"
    return t

def main():
    print("=== start v10 ===")
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
    
    value_bets = 0
    mismatches = 0
    rows = []
    
    for m in fs:
        t = cur.get(m["slug"], {})
        hd, ad = t.get(m["home"], {}), t.get(m["away"], {})
        h_low = hd.get("played", 0) < MIN_PLAYED
        a_low = ad.get("played", 0) < MIN_PLAYED
        hr = hd.get("rank", DEFAULT_RANK) if not h_low else last.get(m["slug"], {}).get(m["home"], {}).get("rank", DEFAULT_RANK)
        ar = ad.get("rank", DEFAULT_RANK) if not a_low else last.get(m["slug"], {}).get(m["away"], {}).get("rank", DEFAULT_RANK)
        hp, ap = power(hr, hd, True), power(ar, ad, False)
        gap = abs(hp - ap)
        
        if gap < MISMATCH_THRESHOLD:
            continue
        
        # تعیین تیم قوی‌تر
        stronger_team = m["home"] if hp > ap else m["away"]
        stronger_power = max(hp, ap)
        model_prob = stronger_power / 100
        
        # دریافت قیمت Polymarket
        market_price = get_polymarket_price(stronger_team)
        
        # محاسبه لبه
        if market_price:
            edge = model_prob - market_price
            kelly = kelly_criterion(model_prob, market_price)
        else:
            edge = 0
            kelly = 0
        
        # طبقه‌بندی
        if gap >= 65:
            lab = "کاملاً نابرابر 🔴"
        else:
            lab = "به‌وضوح نابرابر 🟠"
        
        analysis = {
            "league": m["league"],
            "date": m["date"],
            "home": m["home"],
            "away": m["away"],
            "stronger": stronger_team,
            "model_prob": model_prob,
            "market_price": market_price,
            "edge": edge,
            "kelly": kelly,
            "label": lab,
            "low": h_low or a_low,
        }
        
        # فقط نوتیف اگه value bet باشه یا بازی نابرابر جدید باشه
        is_value_bet = market_price and edge >= MIN_EDGE and kelly > 0
        
        if m["id"] not in noted:
            if is_value_bet:
                if send(msg_value_bet(analysis)):
                    noted.append(m["id"])
                    value_bets += 1
            else:
                if send(msg_mismatch_only(analysis)):
                    noted.append(m["id"])
                    mismatches += 1
        
        rows.append((gap, f"{m['home']} - {m['away']} | {round(gap)} | {lab}"))
    
    state["notified"] = noted
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if value_bets > 0 or mismatches > 0 or state.get("last_summary") != today:
        rows.sort(reverse=True)
        top = "\n".join(r[1] for r in rows[:8])
        summary = f"📊 گزارش ایجنت v10\nتعداد بازی‌ها: {len(fs)}\n💰 Value Bets: {value_bets}\n⚔️ بازی‌های نابرابر: {mismatches}\n\nبالاترین اختلاف‌ها:\n{top}"
        send(summary, html=False)
        state["last_summary"] = today
    
    json.dump(state, open("state.json", "w"))
    print("=== done, value_bets:", value_bets, "mismatches:", mismatches, "===")

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
