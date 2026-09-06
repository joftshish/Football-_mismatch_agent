import Core as C
import httpx, traceback
from datetime import datetime, timezone

def api(method, **kw):
    try:
        r = httpx.post(f"https://api.telegram.org/bot{C.TOKEN}/{method}", json=kw, timeout=15)
        return r.json()
    except Exception as ex:
        print("tg err", ex)
        return {}

HELP = "🤖 دستورات:\nراهنما → منو\nوضعیت → تنظیمات\nلیگ‌ها → فهرست لیگ‌ها\nخاموش <لیگ> / روشن <لیگ>\nلبه <عدد> → حداقل لبه درصد\nفقط ارزش / همه\nلینک‌ها → لینک‌های اخیر\nبت <تیم> <قیمت> <درصد>\nگزارش → آمار بت‌ها"

def find_league(q):
    qn = C.norm(q)
    if not qn:
        return None
    for name in list(C.SOCCER.values()) + list(C.TENNIS.values()):
        if qn in C.norm(name):
            return name
    return None

def parse_bet(text):
    t = text.replace("/bet", "بت", 1).replace("بت", "", 1).strip()
    parts = t.split()
    if len(parts) < 3:
        return None
    try:
        stake = float(parts[-1])
        price = float(parts[-2])
    except ValueError:
        return None
    team = " ".join(parts[:-2])
    if not team or not (0.01 < price < 0.99):
        return None
    return {"team": team, "price": price, "pct": min(stake, 5)}

def find_match(team):
    fx = C.soccer_fixtures(6) + C.tennis_fixtures(6)
    tl = C.norm(team)
    for m in fx:
        if tl in C.norm(m["home"]) or tl in C.norm(m["away"]):
            return m
    return None

def result_of(b):
    d = b["date"][:10].replace("-", "")
    kind = b["sport"]
    try:
        r = httpx.get(f"{C.EPSN}/site/v2/sports/{kind}/{b['slug']}/scoreboard", params={"dates": d}, timeout=15).json()
        for ev in r.get("events", []):
            cs = ev.get("competitions", [{}])[0].get("competitors", [])
            names = [C.norm((c.get("athlete") or c.get("team") or {}).get("displayName") or "") for c in cs]
            if C.norm(b["team"]) not in names:
                continue
            if ev.get("status", {}).get("type", {}).get("state") != "post":
                return None
            i = names.index(C.norm(b["team"]))
            if "winner" in cs[i]:
                return "win" if cs[i]["winner"] else "lose"
            try:
                s0, s1 = float(cs[0].get("score", -1)), float(cs[1].get("score", -1))
            except Exception:
                return None
            if s0 == s1:
                return "push"
            mine = s0 if i == 0 else s1
            opp = s1 if i == 0 else s0
            return "win" if mine > opp else "lose"
    except Exception as ex:
        print("res err", ex)
    return None

def report(st):
    bets = st.get("bets", [])
    w = sum(1 for b in bets if b["status"] == "win")
    l = sum(1 for b in bets if b["status"] == "lose")
    o = sum(1 for b in bets if b["status"] == "open")
    bank = st.get("bank", 100)
    roi = bank - 100
    wr = round(w / (w + l) * 100) if w + l else 0
    return f"📊 گزارش بت‌ها\n💳 بانک: {round(bank,1)} (شروع 100)\n📈 سود/ضرر: {round(roi,1)}%\n✅ برد: {w} | ❌ باخت: {l} | ⏳ باز: {o}\n🎯 نرخ برد: {wr}%"

def handle(text, st, prefs):
    t = text.strip()
    if t in ("راهنما", "/start", "help"):
        return HELP
    if t == "وضعیت":
        ov = "فقط ارزش 💰" if prefs.get("only_value") else "همه 📢"
        return f"⚙️ وضعیت:\nحداقل لبه: {round(prefs.get('min_edge', 0.03)*100)}%\nحالت: {ov}\nلیگ‌های خاموش: {', '.join(prefs.get('off', [])) or 'هیچ'}"
    if t == "لیگ‌ها":
        lines = [("❌ " if n in prefs.get("off", []) else "✅ ") + n for n in list(C.SOCCER.values()) + list(C.TENNIS.values())]
        return "\n".join(lines)
    if t.startswith("خاموش ") or t.startswith("روشن "):
        on = t.startswith("روشن")
        lg = find_league(t.split(" ", 1)[1])
        if not lg:
            return "لیگ پیدا نشد؛ «لیگ‌ها» رو ببین"
        off = prefs.setdefault("off", [])
        if on and lg in off:
            off.remove(lg)
            return f"✅ روشن شد: {lg}"
        if not on and lg not in off:
            off.append(lg)
            return f"❌ خاموش شد: {lg}"
        return "تغییری لازم نبود"
    if t.startswith("لبه "):
        try:
            v = max(1, min(20, float(t.split()[1])))
            prefs["min_edge"] = v / 100
            return f"⚙️ حداقل لبه: {v}%"
        except Exception:
            return "فرمت: لبه 5"
    if t == "فقط ارزش":
        prefs["only_value"] = True
        return "📢 حالت: فقط Value Bet 💰"
    if t == "همه":
        prefs["only_value"] = False
        return "📢 حالت: همه نوتیف‌ها"
    if t == "لینک‌ها":
        ls = st.get("last_links", [])
        return "\n\n".join(ls[-5:]) if ls else "لینکی ثبت نشده"
    if t.startswith("بت") or t.startswith("/bet"):
        pb = parse_bet(t)
        if not pb:
            return "فرمت: بت Al Hilal 0.80 2"
        m = find_match(pb["team"])
        if not m:
            return f"❌ بازی‌ای برای «{pb['team']}» پیدا نشد"
        st.setdefault("bets", []).append({"team": pb["team"], "price": pb["price"], "pct": pb["pct"], "sport": m["sport"], "slug": m["slug"], "date": m["date"], "status": "open"})
        return f"✅ بت ثبت شد: {pb['team']} @ {pb['price']} | {pb['pct']}%\nبعد از بازی خودکار تسویه می‌شه 🏁"
    if t.startswith("گزارش"):
        return report(st)
    return None

def main():
    st = C.load_state()
    prefs = st.setdefault("prefs", {"off": [], "only_value": False, "min_edge": 0.03})
    off = st.get("tg_offset", 0)
    data = api("getUpdates", offset=off, timeout=5)
    for u in data.get("result", []):
        off = u["update_id"] + 1
        text = ((u.get("message") or {}).get("text")) or ""
        reply = handle(text, st, prefs)
        if reply:
            C.send(reply, html=False)
    st["tg_offset"] = off
    bets = st.get("bets", [])
    bank = st.setdefault("bank", 100.0)
    for b in bets:
        if b["status"] != "open":
            continue
        try:
            if datetime.fromisoformat(b["date"].replace("Z", "+00:00")) > datetime.now(timezone.utc):
                continue
        except Exception:
            continue
        res = result_of(b)
        if not res:
            continue
        stake = bank * b["pct"] / 100
        if res == "win":
            profit = stake * (1 / b["price"] - 1)
            bank += profit
            b["status"] = "win"
            C.send(f"✅ بت برد! {b['team']}\nسود: +{round(profit,2)} | 💳 بانک: {round(bank,1)}")
        elif res == "lose":
            bank -= stake
            b["status"] = "lose"
            C.send(f"❌ بت باخت: {b['team']}\nضرر: -{round(stake,2)} | 💳 بانک: {round(bank,1)}")
        else:
            b["status"] = "push"
            C.send(f"↩️ مساوی — برگشت سرمایه: {b['team']}")
    st["bank"] = bank
    st["bets"] = bets[-200:]
    C.save_state(st)
    print("bot done")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        raise
