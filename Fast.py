import Core as C
import json
import traceback
from datetime import datetime, timezone, timedelta

FLOW_MIN = 200.0
THIN_VOL = 15000.0
EXIT = 0.08
STOP = -0.08
STEAM = 0.05
MOVE = 0.03
PRESTART_H = 2.0

def is_past(ds, grace=1.0):
    try:
        dt = datetime.fromisoformat(ds.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > dt + timedelta(hours=grace)
    except Exception:
        return False

def hours_to_start(ds):
    try:
        dt = datetime.fromisoformat(ds.replace("Z", "+00:00"))
        return (dt - datetime.now(timezone.utc)).total_seconds() / 3600.0
    except Exception:
        return None

def find_slug(name, cur, last):
    for s, t in cur.items():
        if name in t:
            return s
    for s, t in last.items():
        if name in t:
            return s
    return None

def snap_of(e):
    mks = e.get("markets") or []
    if not mks:
        return None
    mk = mks[0]
    oc, pr = mk.get("outcomes"), mk.get("outcomePrices")
    if isinstance(oc, str):
        try:
            oc = json.loads(oc)
        except Exception:
            return None
    if isinstance(pr, str):
        try:
            pr = json.loads(pr)
        except Exception:
            return None
    if not oc or not pr or len(oc) != len(pr):
        return None
    try:
        vals = [float(x) for x in pr]
    except Exception:
        return None
    idx = max(range(len(vals)), key=lambda i: vals[i])
    return {"side": str(oc[idx]), "p": vals[idx], "vol": float(mk.get("volumeNum") or 0), "liq": float(mk.get("liquidityNum") or 0)}

def fetch_poly():
    out = []
    seen = set()
    for tag in ["soccer", "tennis"]:
        for offset in (0, 200, 400):
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

def flow_for_market(ev, name, sport):
    mks = [mk for mk in (ev.get("markets") or []) if not C.is_closed(mk)]
    if not mks:
        return None
    mk = mks[0]
    cid = mk.get("conditionId")
    if not cid:
        return None
    try:
        oc = mk.get("outcomes")
        ids = mk.get("clobTokenIds")
        if isinstance(oc, str):
            oc = json.loads(oc)
        if isinstance(ids, str):
            ids = json.loads(ids)
    except Exception:
        return None
    if not oc or not ids or len(oc) != len(ids):
        return None
    ks = C.keys(name, sport)
    idx = None
    for i, o in enumerate(oc):
        on = C.norm(o)
        if on in ("yes", "no", "draw"):
            continue
        if any(k in on for k in ks):
            idx = i
            break
    if idx is None:
        q = C.norm((mk.get("question") or "") + " " + (mk.get("groupItemTitle") or ""))
        if len(oc) == 2 and C.norm(oc[0]) == "yes" and any(k in q for k in ks):
            idx = 0
    if idx is None:
        return None
    token = ids[idx]
    try:
        trades = C.httpx.get("https://data-api.polymarket.com/trades", params={"market": cid, "limit": 300}, timeout=15).json()
    except Exception:
        return None
    if not isinstance(trades, list):
        return None
    now_ts = datetime.now(timezone.utc).timestamp()
    total = 0.0
    for t in trades:
        try:
            ts = float(t.get("timestamp"))
        except Exception:
            continue
        if now_ts - ts > 3600:
            continue
        if t.get("asset") != token:
            continue
        try:
            notional = float(t.get("size", 0)) * float(t.get("price", 0))
        except Exception:
            continue
        side = (t.get("side") or "").upper()
        if side == "BUY":
            total += notional
        elif side == "SELL":
            total -= notional
    return total

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

def analyze_ev_for_underpriced(ev, cur, last, tr):
    m = build_m(ev, cur, last, tr)
    if not m:
        return None
    c = C.compute(m, cur, last, tr)
    if not c:
        return None
    if c["gap"] < 50:
        return None
    ph, pa = C.poly_prices(ev, m["home"], m["away"], m["sport"])
    if ph is None:
        return None
    price_strong = ph if c["sh"] else pa
    if price_strong is None:
        return None
    if not (0.40 <= price_strong <= 0.60):
        return None
    return {"m": m, "c": c, "price": price_strong, "stronger": c["stronger"], "hcty": c.get("hcty", ""), "acty": c.get("acty", "")}

def main():
    print("=== Fast v14 ===")
    st = C.load_state()
    known = st.setdefault("known_poly", [])
    noted = st.setdefault("notified", [])
    dup = st.setdefault("dup", [])
    dup_set = set(dup)
    watch = st.setdefault("watchlist", [])
    watch[:] = [w for w in watch if not is_past(w.get("date", ""))]
    preds = st.setdefault("preds", [])
    links = st.setdefault("last_links", [])
    prefs = st.get("prefs", {})
    cal = st.get("calib", 1.0)
    off_l = set(prefs.get("off", []))
    only_v = prefs.get("only_value", False)
    min_e = prefs.get("min_edge", 0.02)
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
    evs = fetch_poly()
    fresh = [e for e in evs if str(e.get("id")) not in known]
    print("poly:", len(evs), "fresh:", len(fresh))
    sent = 0

    for e in fresh[:30]:
        if is_past(e.get("startDate") or ""):
            continue
        try:
            mks = e.get("markets") or []
            vol0 = float(mks[0].get("volumeNum") or 0) if mks else 0.0
            liq0 = float(mks[0].get("liquidityNum") or 0) if mks else 0.0
        except Exception:
            vol0 = liq0 = 0.0
        if vol0 >= 15000:
            continue
        ua = analyze_ev_for_underpriced(e, cur, last, tr)
        if not ua:
            continue
        if ua["m"]["league"] in off_l:
            continue
        eid = str(e.get("id"))
        dkey = f"{ua['m']['home']}|{ua['m']['away']}"
        if eid in noted or dkey in dup_set:
            continue
        noted.append(eid)
        known.append(eid)
        dup.append(dkey)
        dup_set.add(dkey)
        hc = ua["hcty"]
        ac = ua["acty"]
        txt = f"🎯 شکار بازار تازه آندر ولیو\n⚽ {ua['m']['home']} {hc} vs {ua['m']['away']} {ac}\n🏆 {ua['m']['league']}\n📊 مدل (gap {C.fa(round(ua['c']['gap']))}): تیم قوی {ua['stronger']}\n💰 قیمت بازار: ~{C.fa(round(ua['price']*100))}٪ (نزدیک ۵۰/۵۰!)\n💰 حجم: {C.fa(int(vol0))} دلار — {C.STAGE_FA[C.liq_stage(liq0)]}\n🎯 نوع: Trade — خروج قبل از بازی\n💵 حداکثر ۱٪\n⚠️ فقط اطلاع — قضاوت با شما\n📋 لینک:\n{C.poly_link(e)}"
        C.send(txt, html=False)
        preds.append({"home": ua["m"]["home"], "away": ua["m"]["away"], "sport": ua["m"]["sport"], "slug": ua["m"]["slug"], "date": ua["m"]["date"], "prob": ua["price"], "price": round(ua["price"], 3), "stronger": ua["stronger"], "link": C.poly_link(e), "liq0": liq0, "vol0": vol0, "eid": eid, "status": "open", "src": "underpriced"})
        sent += 1

    for p in preds:
        if p.get("status") != "open" or not p.get("link"):
            continue
        h = hours_to_start(p.get("date", ""))
        ev = C.find_poly(evs, p["home"], p["away"], p["sport"])
        if not ev:
            ev, _ = C.search_poly(p["home"], p["away"], p["sport"])
        if not ev:
            continue
        ph, pa = C.poly_prices(ev, p["home"], p["away"], p["sport"])
        if ph is None:
            continue
        curp = ph if p["stronger"] == p["home"] else pa
        if curp is None:
            continue
        stats = C.market_stats(ev, p["home"], p["away"], p["sport"])
        stage = C.liq_stage(stats["vol"])
        money_in = stats["vol"] - p.get("vol0", 0)
        flowline = f"💰 پول از ورود: {C.fa(int(money_in))} دلار | حجم کل: {C.fa(int(stats['vol']))} | {C.STAGE_FA[stage]}"
        nf = flow_for_market(ev, p["stronger"], p.get("sport", "soccer"))
        nfl = f"🌊 جریان خالص ۱ ساعت: {C.fa(int(nf))} دلار" if nf is not None else ""
        entry = p["price"]
        drift = curp - entry
        p["last"] = curp
        head = f"⚽ {p['home']} vs {p['away']}\n📥 ورود: {C.fa(round(entry*100))}٪ | 📤 الان: {C.fa(round(curp*100))}٪"
        msg = None
        if h is not None and h <= 0:
            p["status"] = "closed"
            p["pnl"] = round(drift, 3)
            msg = f"⏱️ بازی شروع شد\n{head}\nℹ️ پنجرهٔ فروش قبل از استارت بسته شد؛ تصمیم دستی\n{flowline}\n📋 {p['link']}"
        elif nf is not None and nf <= -2 * FLOW_MIN:
            p["status"] = "closed"
            p["pnl"] = round(drift, 3)
            ret = round(drift / entry * 100) if entry else 0
            msg = f"🛑 خروج واگرایی جریان\n{head} | P/L: ~{C.fa(ret)}٪\n{nfl}\n{flowline}\n📋 {p['link']}"
        elif h is not None and h <= PRESTART_H and drift >= 0.02:
            p["status"] = "closed"
            p["pnl"] = round(drift, 3)
            ret = round(drift / entry * 100) if entry else 0
            msg = f"🏁 فروش قبل از استارت\n{head}\n💵 سود بدون ریسک بازی: ~{C.fa(ret)}٪\n⏳ تا شروع: {C.fa(round(h,1))} ساعت\n{nfl}\n{flowline}\n📋 لینک فروش:\n{p['link']}"
        elif drift >= EXIT:
            p["status"] = "closed"
            p["pnl"] = round(drift, 3)
            ret = round(drift / entry * 100) if entry else 0
            msg = f"🎯 سیگنال خروج (همگرایی)\n{head}\n💵 سود بدون ریسک بازی: ~{C.fa(ret)}٪\n{nfl}\n{flowline}\n📋 لینک فروش:\n{p['link']}"
        elif stage == "deep" and drift >= 0.03:
            p["status"] = "closed"
            p["pnl"] = round(drift, 3)
            ret = round(drift / entry * 100) if entry else 0
            msg = f"🏊 بازار عمیق شد — خروج\n{head}\n💵 سود همگرایی: ~{C.fa(ret)}٪\n{nfl}\n{flowline}\n📋 لینک فروش:\n{p['link']}"
        elif drift <= STOP:
            p["status"] = "closed"
            p["pnl"] = round(drift, 3)
            ret = round(drift / entry * 100) if entry else 0
            msg = f"🛑 حد ضرر\n{head}\n⚠️ ضرر کاغذی: ~{C.fa(ret)}٪\n{nfl}\n{flowline}\n📋 {p['link']}"
        elif nf is not None and nf >= FLOW_MIN and stats["vol"] < THIN_VOL and not p.get("flowsig"):
            p["flowsig"] = True
            msg = f"🌊 ورود پول هوشمند (جهت واقعی)\n{head}\n{nfl}\n{flowline}\n⏳ نگه دار — هنوز سیگنال خروج نیست\n📋 {p['link']}"
        elif drift >= STEAM and not p.get("steam"):
            p["steam"] = True
            p["mv3"] = True
            msg = f"🚂 بخار قیمت\n{head} (+{C.fa(round(drift*100,1))})\n{nfl}\n{flowline}\n⏳ نگه دار"
        elif abs(drift) >= MOVE and not p.get("mv3"):
            p["mv3"] = True
            arrow = "📈" if drift > 0 else "📉"
            msg = f"📊 حرکت قیمت از لحظه ورود\n{head} ({'+' if drift>0 else ''}{C.fa(round(drift*100,1))})\n{flowline}\nℹ️ فقط اطلاع — هنوز سیگنال خروج نیست"
        if msg:
            C.send(msg, html=False)
            sent += 1

    if watch:
        remaining = []
        for w in watch:
            if w["league"] in off_l:
                continue
            dkey = f"{w['home']}|{w['away']}"
            ev = C.find_poly(evs, w["home"], w["away"], w["sport"])
            if not ev:
                ev, _ = C.search_poly(w["home"], w["away"], w["sport"])
            if not ev:
                remaining.append(w)
                continue
            m = dict(w)
            m["id"] = ""
            c = C.compute(m, cur, last, tr)
            ph, pa = C.poly_prices(ev, w["home"], w["away"], w["sport"])
            if not c or ph is None:
                remaining.append(w)
                continue
            c["prob"] = 0.5 + (c["prob"] - 0.5) * cal
            price = ph if c["sh"] else pa
            P = c.get("pred", 0.6)
            c["prob"] = P * c["prob"] + (1 - P) * price
            edge = c["prob"] - price
            hold_ok = bool(c.get("solid")) and P >= 0.65 and not c.get("cross") and edge >= min_e and edge <= C.MAX_EDGE
            kl = C.kelly(c["prob"], price, 0.02) if hold_ok else 0.0
            is_value = hold_ok and kl > 0
            floor = price <= c["prob"] - 0.08
            sigtype = "✅ Hold — تا پایان بازی" if is_value else "🎯 Trade — خروج قبل از بازی"
            size = f"تا {C.fa(round(kl*100,1))}٪ سرمایه" if is_value else "حداکثر ۱٪ (ترید کوتاه)"
            note = None
            if edge > C.MAX_EDGE:
                note = "⚠️ لبه مشکوک (زیاد) — با احتیاط!"
            elif not c["solid"]:
                note = "⚠️ اوایل فصل/داده کم — فقط اطلاع"
            elif not is_value and edge < min_e:
                note = f"❌ لبه کم ({C.fa(round(edge*100,1))}٪) — فقط برای اطلاع"
            stats = C.market_stats(ev, w["home"], w["away"], w["sport"])
            stage = C.liq_stage(stats["vol"])
            stage_line = f"💰 حجم معامله‌شده: {C.fa(int(stats['vol']))} دلار — {C.STAGE_FA[stage]}\n💧 عمق دفتر سفارش: {C.fa(int(stats['liq']))} دلار"
            note = (note + "\n" + stage_line) if note else stage_line
            title = "بازار باز شد + VALUE BET 💰" if is_value else ("بازار باز شد + 🎯 کف قیمت" if floor else "بازار Polymarket باز شد ⚡")
            a = {"title": title, "league": w["league"], "date": w["date"], "home": w["home"], "away": w["away"], "stronger": c["stronger"], "prob": c["prob"], "price": price, "edge": edge, "kelly": kl if is_value else 0, "label": "به‌وضوح نابرابر 🟠", "icon": "🎾" if w["sport"] == "tennis" else "⚽", "link": C.poly_link(ev), "note": note, "sigtype": sigtype, "size": size, "hcr": c.get("hcr"), "hlr": c.get("hlr"), "acr": c.get("acr"), "alr": c.get("alr"), "hcty": c.get("hcty", ""), "acty": c.get("acty", ""), "bh": c.get("bh"), "ba": c.get("ba")}
            known.append(str(ev.get("id")))
            if dkey in dup_set:
                continue
            if only_v and not is_value:
                continue
            if C.notify("⚡", a):
                sent += 1
                noted.append(str(ev.get("id")))
                dup.append(dkey)
                dup_set.add(dkey)
                preds.append({"home": w["home"], "away": w["away"], "sport": w["sport"], "slug": w["slug"], "date": w["date"], "prob": round(c["prob"], 3), "price": round(price, 3), "stronger": c["stronger"], "link": a.get("link"), "liq0": stats["liq"], "vol0": stats["vol"], "eid": str(ev.get("id")), "status": "open"})
                if a.get("link"):
                    links.append(f"{w['home']} vs {w['away']}\n{a['link']}")
        watch[:] = remaining
    st["preds"] = preds[-300:]
    st["last_links"] = links[-10:]
    st["dup"] = dup[-500:]
    for e in evs:
        known.append(str(e.get("id")))
    C.save_state(st)
    print("fast done, sent:", sent)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        try:
            C.send("❌ خطای Fast:\n" + e[-2000:], html=False)
        except Exception:
            pass
        raise
