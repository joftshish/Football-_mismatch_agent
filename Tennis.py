import Core as C
import json, os, time, traceback
from datetime import datetime, timezone

STATE = "tennis_state.json"
THROTTLE = 30 * 60

def load():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE))
        except Exception:
            pass
    return {}

def save(s):
    json.dump(s, open(STATE, "w"))

def notify_tennis(m, c, price, edge, link):
    try:
        dt = datetime.fromisoformat(m["date"].replace("Z", "+00:00")).astimezone(C.TZ)
        jd, tm = C.jalali(dt)
    except Exception:
        jd, tm = m["date"], ""
    stronger = c["stronger"]
    weaker = m["away"] if stronger == m["home"] else m["home"]
    rs = c["hr"] if stronger == m["home"] else c["ar"]
    rw = c["ar"] if stronger == m["home"] else c["hr"]
    L = [
        "🎾 <b>VALUE BET تنیس</b>",
        "",
        f"🏆 تور: {m['league']}",
        f"📅 {jd} — ساعت {tm}",
        "",
        f"🎾 {m['home']} (رنک {C.fa(c['hr'])})",
        f"🆚 {m['away']} (رنک {C.fa(c['ar'])})",
        "",
        f"📊 مدل: {C.fa(round(c['prob']*100))}٪ برد {stronger}",
        f"💰 بازار: {C.fa(round(price*100))}٪ برد {stronger}",
        f"📈 لبه: {C.fa(round(edge*100,1))}٪",
        "",
        "🎯 نوع: Trade — خروج قبل از بازی",
        "💵 حداکثر ۱٪ سرمایه",
    ]
    if link:
        L += ["", "🔗 لینک:", link]
    return C.send("\n".join(L))

def main():
    st = load()
    now = time.time()
    if now - st.get("last_run", 0) < THROTTLE:
        print("tennis throttled, skip")
        return
    st["last_run"] = now
    noted = st.setdefault("notified", [])
    watch = st.setdefault("watch", [])
    tr = C.tennis_rankings()
    fx = C.tennis_fixtures(days=5)
    evs = [e for e in C.poly_events() if e.get("_tag") == "tennis"]
    print(f"tennis: fixtures={len(fx)} markets={len(evs)} atp={len(tr.get('atp',{}))} wta={len(tr.get('wta',{}))}")
    sent = 0
    for m in fx:
        c = C.compute(m, {}, {}, tr)
        if not c:
            continue
        key = m["home"] + "|" + m["away"]
        ev = C.find_poly(evs, m["home"], m["away"], "tennis")
        if not ev:
            ev, _ = C.search_poly(m["home"], m["away"], "tennis")
        ph = pa = None
        if ev:
            ph, pa = C.poly_prices(ev, m["home"], m["away"], "tennis")
        if ev and ph is not None:
            if key in noted:
                continue
            price = ph if c["sh"] else pa
            P = c.get("pred", 0.7)
            prob = P * c["prob"] + (1 - P) * price
            edge = prob - price
            if 0.03 <= edge <= 0.20:
                if notify_tennis(m, c, price, edge, C.poly_link(ev)):
                    noted.append(key)
                    sent += 1
        else:
            if key not in watch and c["gap"] >= C.TENNIS_GAP:
                watch.append(key)
    st["notified"] = noted[-300:]
    st["watch"] = watch[-200:]
    save(st)
    print("tennis done, sent:", sent)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        try:
            C.send("❌ خطای تنیس:\n" + e[-1500:], html=False)
        except Exception:
            pass
