import Core as C
import traceback
from datetime import datetime, timezone, timedelta

MIN_GAP = 55
MAX_PRICE = 0.65
MIN_EDGE = 0.05

def is_in_range(ds, days_min=14, days_max=30):
    try:
        dt = datetime.fromisoformat(ds.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = (dt - now).days
        return days_min <= delta <= days_max
    except Exception:
        return False

def fetch_long_events():
    out = []
    seen = set()
    for tag in ["soccer", "tennis"]:
        for offset in (0, 200, 400, 600, 800):
            try:
                d = C.httpx.get(f"{C.POLY}/events", params={"closed": "false", "tag_slug": tag, "limit": 200, "offset": offset}, timeout=15).json()
            except Exception:
                break
            if not isinstance(d, list) or not d:
                break
            for e in d:
                eid = str(e.get("id"))
                if eid in seen:
                    continue
                seen.add(eid)
                e["_tag"] = tag
                out.append(e)
            if len(d) < 200:
                break
    return out

def find_slug(name, cur, last):
    for s, t in cur.items():
        if name in t:
            return s
    for s, t in last.items():
        if name in t:
            return s
    return None

def build_m(ev, cur, last, tr):
    title = (ev.get("title") or "").strip()
    sep = " vs " if " vs " in title else (" v " if " v " in title else None)
    if not sep:
        return None
    parts = [x.strip() for x in title.split(sep, 1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    home, away = parts
    sport = ev.get("_tag", "soccer")
    m = {"home": home, "away": away, "sport": sport, "slug": "", "date": ev.get("startDate") or "", "league": "", "id": str(ev.get("id"))}
    if sport == "soccer":
        sh = find_slug(home, cur, last)
        sa = find_slug(away, cur, last)
        if not sh and not sa:
            return None
        slug = sh or sa
        m["slug"] = slug
        if sh and sa and sh == sa:
            m["league"] = C.SOCCER[slug]
        else:
            m["league"] = "🏆 جام حذفی / رقابت ترکیبی"
    else:
        m["slug"] = "atp" if tr.get("atp", {}).get(home.lower().split()[-1]) else "wta"
        m["league"] = "🎾 تنیس"
    return m

def main():
    print("=== LongShot ===")
    st = C.load_state()
    noted = st.setdefault("longshot_noted", [])
    now = datetime.now(timezone.utc)
    ls = (now.year if now.month >= 7 else now.year - 1) - 1
    cache = C.standings_cache_load(st)
    if cache and cache.get("ls") == ls:
        cur, last = cache["cur"], cache["last"]
    else:
        cur = C.soccer_standings()
        last = C.soccer_standings(ls)
        C.standings_cache_save(st, cur, last, ls)
    tr = C.tennis_rankings()
    evs = fetch_long_events()
    print(f"longshot events: {len(evs)}")
    sent = 0
    candidates = []
    for e in evs:
        eid = str(e.get("id"))
        if eid in noted:
            continue
        sd = e.get("startDate") or ""
        if not is_in_range(sd):
            continue
        m = build_m(e, cur, last, tr)
        if not m:
            continue
        c = C.compute(m, cur, last, tr)
        if not c or c["gap"] < MIN_GAP:
            continue
        ph, pa = C.poly_prices(e, m["home"], m["away"], m["sport"])
        if ph is None:
            continue
        price = ph if c["sh"] else pa
        if price > MAX_PRICE:
            continue
        P = c.get("pred", 0.6)
        prob = P * c["prob"] + (1 - P) * price
        edge = prob - price
        if edge < MIN_EDGE:
            continue
        candidates.append({"m": m, "c": c, "price": price, "prob": prob, "edge": edge, "ev": e})
    candidates.sort(key=lambda x: -x["edge"])
    for cand in candidates[:5]:
        m, c, price, prob, edge, e = cand["m"], cand["c"], cand["price"], cand["prob"], cand["edge"], cand["ev"]
        eid = str(e.get("id"))
        noted.append(eid)
        try:
            dt = datetime.fromisoformat(m["date"].replace("Z", "+00:00")).astimezone(C.TZ)
            jd, tm = C.jalali(dt)
            days_away = (dt - now).days
        except Exception:
            jd, tm, days_away = m["date"], "", 0
        stronger = c["stronger"]
        hcty = c.get("hcty", "")
        acty = c.get("acty", "")
        txt = f"🔭 بت دور (سرمایه‌گذاری بلندمدت)\n⚽ {m['home']} {hcty}\n🆚 {m['away']} {acty}\n🏆 {m['league']}\n📅 {jd} — ساعت {tm} ({C.fa(days_away)} روز دیگر)\n\n🏅 رتبه‌ها:\n   {m['home']}: {C.fa(c.get('hcr') or c.get('hr') or '—')}\n   {m['away']}: {C.fa(c.get('acr') or c.get('ar') or '—')}\n\n📊 گپ: {C.fa(round(c['gap']))}\n💰 قیمت بازار: {C.fa(round(price*100))}٪ (هنوز خام!)\n📈 مدل: {C.fa(round(prob*100))}٪ برد {stronger}\n💎 لبه: {C.fa(round(edge*100,1))}٪\n\n🎯 نوع: Trade — ورود زودهنگام\n💵 حداکثر ۱٪ (ریسک زمانی)\n⚠️ بت دور = پول قفل می‌شه؛ فقط اگه مطمئنی\n🔗 {C.poly_link(e)}"
        if C.send(txt, html=False):
            sent += 1
    st["longshot_noted"] = noted[-500:]
    C.save_state(st)
    print("longshot done, sent:", sent)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        try:
            C.send("❌ خطای LongShot:\n" + e[-1500:], html=False)
        except Exception:
            pass
