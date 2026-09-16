import Core as C
import json
import traceback
from datetime import datetime, timezone, timedelta

DATA = "https://data-api.polymarket.com"
FLOW_MIN = 200.0
EXIT = 0.08
STOP = -0.08
STEAM = 0.05
MOVE = 0.03

def is_past(ds, grace=1.0):
    try:
        dt = datetime.fromisoformat(ds.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > dt + timedelta(hours=grace)
    except Exception:
        return False

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

def net_flow(mk, hours=1.0):
    cid = mk.get("conditionId")
    if not cid:
        return {}
    try:
        d = C.httpx.get(f"{DATA}/trades", params={"market": cid, "limit": 300}, timeout=15).json()
    except Exception:
        return {}
    if not isinstance(d, list):
        return {}
    now = datetime.now(timezone.utc).timestamp()
    out = {}
    for t in d:
        try:
            ts = float(t.get("timestamp") or 0)
            size = float(t.get("size") or 0)
            px = float(t.get("price") or 0)
        except Exception:
            continue
        if now - ts > hours * 3600:
            continue
        side = (t.get("side") or "").upper()
        oc = t.get("outcome") or ""
        if not oc:
            continue
        dol = size * px
        out[oc] = out.get(oc, 0.0) + (dol if side == "BUY" else -dol)
    return out

def build_m(ev, cur, tr):
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
        slug = None
        for s, t in cur.items():
            if home in t or away in t:
                slug = s
                break
        if not slug:
            if C.cross_info(home, cur, {})[2] or C.cross_info(away, cur, {})[2]:
                m["slug"] = "uefa.champions"
                m["league"] = "🇪🇺 اروپا"
                return m
            return None
        m["slug"] = slug
        m["league"] = C.SOCCER[slug]
    else:
        m["slug"] = "atp" if tr.get("atp", {}).get(home.lower().split()[-1]) else "wta"
        m["league"] = "🎾 تنیس"
    return m

def analyze_ev(ev, cur, last, tr, min_e, cal):
    m = build_m(ev, cur, tr)
    if not m:
        return None
    c = C.compute(m, cur, last, tr)
    if not c:
        return None
    c["prob"] = 0.5 + (c["prob"] - 0.5) * cal
    ph, pa = C.poly_prices(ev, m["home"], m["away"], m["sport"])
    if ph is None:
        return None
    price = ph if c["sh"] else pa
    P = c.get("pred", 0.6)
    c["prob"] = P * c["prob"] + (1 - P) * price
    edge = c["prob"] - price
    hold_ok = bool(c.get("solid")) and P >= 0.65 and not c.get("cross") and edge >= min_e and edge <= C.MAX_EDGE
    kl = C.kelly(c["prob"], price, 0.02) if hold_ok else 0.0
    if edge < min_e or edge > C.MAX_EDGE or kl <= 0 or not hold_ok:
        return None
    return {"m": m, "c": c, "price": price, "edge": edge, "kl": kl, "title": "VALUE BET زودهنگام ⚡", "league": m["league"], "date": m["date"], "home": m["home"], "away": m["away"], "stronger": c["stronger"], "prob": c["prob"], "label": "به‌وضوح نابرابر 🟠", "icon": "🎾" if m["sport"] == "tennis" else "⚽", "link": C.poly_link(ev), "note": "⚡ بازار تازه ایجاد شد", "sigtype": "✅ Hold — تا پایان بازی", "size": f"تا {C.fa(round(kl*100,1))}٪ سرمایه", "hcr": c.get("hcr"), "hlr": c.get("hlr"), "acr": c.get("acr"), "alr": c.get("alr"), "hcty": c.get("hcty", ""), "acty": c.get("acty", ""), "bh": c.get("bh"), "ba": c.get("ba")}

def analyze_ev_for_underpriced(ev, cur, last, tr):
    m = build_m(ev, cur, tr)
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
    st = C.load_state()
    known = st.setdefault("known_poly", [])
    noted = st.setdefault("notified", [])
    dup = st.setdefault("dup", [])
    dup_set = set(dup)
    watch = st.setdefault("watchlist", [])
    watch[:] = [w for w in watch if not is_past(w.get("date", ""))]
    preds = st.setdefault("preds", [])
    links = st.setdefault("last_links", [])
    flow = st.setdefault("flow", {})
    flow_sig = st.setdefault("flow_sig", [])
    prefs = st.get("prefs", {})
    cal = st.get("calib", 1.0)
    off_l = set(prefs.get("off", []))
    only_v = prefs.get("only_value", False)
    min_e = prefs.get("min_edge", 0.02)
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()
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
    open_eids = set()
    for p in preds:
        if p.get("status") == "open" and p.get("eid"):
            open_eids.add(p["eid"])
    for e in evs[:200]:
        eid = str(e.get("id"))
        s = snap_of(e)
        if not s:
            continue
        rec = flow.get(eid)
        if not rec or rec.get("side") != s["side"]:
            flow[eid] = {"side": s["side"], "p": s["p"], "v": s["vol"], "ph": s["p"], "vh": s["vol"], "th": now_ts}
            continue
        hour_flow = rec["v"] - rec["vh"]
        hour_dp = rec["p"] - rec["ph"]
        if now_ts - rec["th"] >= 3600:
            rec["ph"], rec["vh"], rec["th"] = rec["p"], rec["v"], now_ts
        rec["p"], rec["v"] = s["p"], s["vol"]
        rec["hf"], rec["hdp"], rec["liq"], rec["eid"] = hour_flow, hour_dp, s["liq"], eid
    if len(flow) > 300:
        for k in list(flow.keys())[:len(flow) - 300]:
            flow.pop(k, None)
    cand = 0
    for e in evs:
        if cand >= 15:
            break
        eid = str(e.get("id"))
        if eid in flow_sig or eid in open_eids or is_past(e.get("startDate") or ""):
            continue
        mks = e.get("markets") or []
        if not mks:
            continue
        mk = mks[0]
        vol = float(mk.get("volumeNum") or 0)
        if vol >= 15000:
            continue
        sd = e.get("startDate") or ""
        try:
            sdt = datetime.fromisoformat(sd.replace("Z", "+00:00"))
        except Exception:
            continue
        if sdt > now + timedelta(hours=48):
            continue
        m = build_m(e, cur, tr)
        if not m or m["league"] in off_l:
            continue
        cand += 1
        nf = net_flow(mk)
        if not nf:
            continue
        kh, ka = C.keys(m["home"], m["sport"]), C.keys(m["away"], m["sport"])
        best_oc = best_net = None
        for oc, v in nf.items():
            if v >= FLOW_MIN and (best_net is None or v > best_net):
                best_oc, best_net = oc, v
        if not best_oc:
            continue
        ol = C.norm(best_oc)
        if any(k in ol for k in kh):
            stronger = m["home"]
        elif any(k in ol for k in ka):
            stronger = m["away"]
        else:
            continue
        ph, pa = C.poly_prices(e, m["home"], m["away"], m["sport"])
        if ph is None:
            continue
        curp = ph if stronger == m["home"] else pa
        flow_sig.append(eid)
        C.send(f"🌊 ورود پول هوشمند (جهت واقعی)\n⚽ {m['home']} vs {m['away']}\n💰 جریان خالص یک ساعت: +{C.fa(int(best_net))} دلار روی {stronger}\n📍 قیمت فعلی: {C.fa(round(curp*100))}٪\n💰 حجم کل: {C.fa(int(vol))} دلار — {C.STAGE_FA[C.liq_stage(vol)]}\n🎯 نوع: Trade — خروج قبل از بازی\n💵 حداکثر ۱٪\n⚠️ بر پایه جریان پول — احتیاط\n📋 لینک:\n{C.poly_link(e)}", html=False)
        preds.append({"home": m["home"], "away": m["away"], "sport": m["sport"], "slug": m["slug"], "date": m["date"], "prob": curp, "price": round(curp, 3), "stronger": stronger, "link": C.poly_link(e), "liq0": float(mk.get("liquidityNum") or 0), "vol0": vol, "eid": eid, "status": "open", "src": "flow"})
        sent += 1
    flow_sig[:] = flow_sig[-200:]
    for e in fresh[:30]:
        if is_past(e.get("startDate") or ""):
            continue
        mks = e.get("markets") or []
        vol = float(mks[0].get("volumeNum") or 0) if mks else 0.0
        if vol >= 15000:
            continue
        ua = analyze_ev_for_underpriced(e, cur, last, tr)
        if not ua:
            continue
        if ua["m"]["league"] in off_l:
            continue
        eid = str(e.get("id"))
        if eid in noted:
            continue
        noted.append(eid)
        known.append(eid)
        flow_sig.append(eid)
        hc = ua["hcty"]
        ac = ua["acty"]
        txt = f"🎯 شکار بازار تازه آندر ولیو\n⚽ {ua['m']['home']} {hc} vs {ua['m']['away']} {ac}\n🏆 {ua['m']['league']}\n📊 مدل (gap {C.fa(round(ua['c']['gap']))}): تیم قوی {ua['stronger']}\n💰 قیمت بازار: ~{C.fa(round(ua['price']*100))}٪ (نزدیک ۵۰/۵۰!)\n💰 حجم: {C.fa(int(vol))} دلار — {C.STAGE_FA[C.liq_stage(vol)]}\n🎯 نوع: Trade — خروج قبل از بازی\n💵 حداکثر ۱٪\n⚠️ فقط اطلاع — قضاوت با شما\n📋 لینک:\n{C.poly_link(e)}"
        C.send(txt, html=False)
        preds.append({"home": ua["m"]["home"], "away": ua["m"]["away"], "sport": ua["m"]["sport"], "slug": ua["m"]["slug"], "date": ua["m"]["date"], "prob": ua["price"], "price": round(ua["price"], 3), "stronger": ua["stronger"], "link": C.poly_link(e), "liq0": float(mks[0].get("liquidityNum") or 0) if mks else 0, "vol0": vol, "eid": eid, "status": "open", "src": "underpriced"})
        sent += 1
    for p in preds:
        if p.get("status") != "open" or not p.get("link"):
            continue
        if is_past(p.get("date", "")):
            continue
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
        rec = flow.get(p.get("eid", ""))
        reversal = bool(rec) and C.norm(rec["side"]) == C.norm(p["stronger"]) and rec.get("hf", 0) >= 1000 and rec.get("hdp", 0) <= -0.03
        entry = p["price"]
        drift = curp - entry
        p["last"] = curp
        hours_left = None
        try:
            sdt = datetime.fromisoformat(p["date"].replace("Z", "+00:00"))
            hours_left = (sdt - now).total_seconds() / 3600.0
        except Exception:
            hours_left = None
        if reversal:
            p["status"] = "closed"
            p["pnl"] = round(drift, 3)
            ret = round(drift / entry * 100) if entry else 0
            C.send(f"🛑 خروج واگرایی جریان\n⚽ {p['home']} vs {p['away']}\n💰 پول اومد ولی قیمت برگشت علیه ما\n📥 ورود: {C.fa(round(entry*100))}٪ | 📤 الان: {C.fa(round(curp*100))}٪ | P/L: ~{C.fa(ret)}٪\n{flowline}\n📋 {p['link']}", html=False)
            sent += 1
        elif hours_left is not None and 0 < hours_left <= 2 and drift >= 0.01:
            p["status"] = "closed"
            p["pnl"] = round(drift, 3)
            ret = round(drift / entry * 100) if entry else 0
            C.send(f"⏰ فروش قبل از استارت\n⚽ {p['home']} vs {p['away']}\n⏳ کمتر از {C.fa(round(hours_left,1))} ساعت به شروع\n📥 ورود: {C.fa(round(entry*100))}٪ | 📤 الان: {C.fa(round(curp*100))}٪\n💵 سود ایمن: ~{C.fa(ret)}٪\n{flowline}\n📋 لینک فروش:\n{p['link']}", html=False)
            sent += 1
        elif drift >= EXIT:
            p["status"] = "closed"
            p["pnl"] = round(drift, 3)
            ret = round(drift / entry * 100) if entry else 0
            C.send(f"🎯 سیگنال خروج (همگرایی)\n⚽ {p['home']} vs {p['away']}\n📥 ورود: {C.fa(round(entry*100))}٪ | 📤 الان: {C.fa(round(curp*100))}٪\n💵 سود بدون ریسک بازی: ~{C.fa(ret)}٪\n{flowline}\n📋 لینک فروش:\n{p['link']}", html=False)
            sent += 1
        elif stage == "deep" and drift >= 0.03:
            p["status"] = "closed"
            p["pnl"] = round(drift, 3)
            ret = round(drift / entry * 100) if entry else 0
            C.send(f"🏊 بازار عمیق شد — خروج\n⚽ {p['home']} vs {p['away']}\n📥 ورود: {C.fa(round(entry*100))}٪ | 📤 الان: {C.fa(round(curp*100))}٪\n💵 سود همگرایی: ~{C.fa(ret)}٪\n{flowline}\n📋 لینک فروش:\n{p['link']}", html=False)
            sent += 1
        elif drift <= STOP:
            p["status"] = "closed"
            p["pnl"] = round(drift, 3)
            ret = round(drift / entry * 100) if entry else 0
            C.send(f"🛑 حد ضرر\n⚽ {p['home']} vs {p['away']}\n📥 ورود: {C.fa(round(entry*100))}٪ | 📤 الان: {C.fa(round(curp*100))}٪\n⚠️ ضرر کاغذی: ~{C.fa(ret)}٪\n{flowline}\n📋 {p['link']}", html=False)
            sent += 1
        elif drift >= STEAM and not p.get("steam"):
            p["steam"] = True
            p["mv3"] = True
            C.send(f"🚂 بخار قیمت\n⚽ {p['home']} vs {p['away']}\n📥 ورود: {C.fa(round(entry*100))}٪ | 📈 الان: {C.fa(round(curp*100))}٪ (+{C.fa(round(drift*100,1))})\n{flowline}\n⏳ نگه دار", html=False)
            sent += 1
        elif abs(drift) >= MOVE and not p.get("mv3"):
            p["mv3"] = True
            arrow = "📈" if drift > 0 else "📉"
            C.send(f"📊 حرکت قیمت از لحظه ورود\n⚽ {p['home']} vs {p['away']}\n📥 ورود: {C.fa(round(entry*100))}٪ | {arrow} الان: {C.fa(round(curp*100))}٪ ({'+' if drift>0 else ''}{C.fa(round(drift*100,1))})\n{flowline}\nℹ️ فقط اطلاع — هنوز سیگنال خروج نیست", html=False)
            sent += 1
    if watch:
        remaining = []
        for w in watch:
            if w["league"] in off_l:
                continue
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
            sigtype = "✅ Hold — تا پایان بازی" if is_value else "🎯 Trade — خروج قبل از بازی"
            size = f"تا {C.fa(round(kl*100,1))}٪ سرمایه" if is_value else "حداکثر ۱٪ (ترید کوتاه)"
            note = None
            if edge > C.MAX_EDGE:
                note = "⚠️ لبه مشکوک (زیاد) — با احتیاط!"
            elif not c["solid"]:
                note = "⚠️ اوایل فصل/داده کم — فقط اطلاع"
            elif not is_value and edge < min_e:
                note = f"❌ لبه کم ({C.fa(round(edge*100,1))}٪) — فقط برای اطلاع"
            if c["prob"] - price >= 0.08:
                floor = f"🎯 فرصت کف: بازار {C.fa(round(price*100))}٪ در برابر انتظار مدل {C.fa(round(c['prob']*100))}٪"
                note = (note + "\n" + floor) if note else floor
            stats = C.market_stats(ev, w["home"], w["away"], w["sport"])
            stage = C.liq_stage(stats["vol"])
            stage_line = f"💰 حجم معامله‌شده: {C.fa(int(stats['vol']))} دلار — {C.STAGE_FA[stage]}\n💧 عمق دفتر سفارش: {C.fa(int(stats['liq']))} دلار"
            note = (note + "\n" + stage_line) if note else stage_line
            a = {"title": "بازار باز شد + VALUE BET 💰" if is_value else "بازار Polymarket باز شد ⚡", "league": w["league"], "date": w["date"], "home": w["home"], "away": w["away"], "stronger": c["stronger"], "prob": c["prob"], "price": price, "edge": edge, "kelly": kl if is_value else 0, "label": "به‌وضوح نابرابر 🟠", "icon": "🎾" if w["sport"] == "tennis" else "⚽", "link": C.poly_link(ev), "note": note, "sigtype": sigtype, "size": size, "hcr": c.get("hcr"), "hlr": c.get("hlr"), "acr": c.get("acr"), "alr": c.get("alr"), "hcty": c.get("hcty", ""), "acty": c.get("acty", ""), "bh": c.get("bh"), "ba": c.get("ba")}
            wkey = f"{w['home']}|{w['away']}"
            if only_v and not is_value:
                known.append(str(ev.get("id")))
                continue
            if wkey not in dup_set and C.notify("⚡", a):
                sent += 1
                noted.append(str(ev.get("id")))
                dup.append(wkey)
                dup_set.add(wkey)
                preds.append({"home": w["home"], "away": w["away"], "sport": w["sport"], "slug": w["slug"], "date": w["date"], "prob": round(c["prob"], 3), "price": round(price, 3), "stronger": c["stronger"], "link": a.get("link"), "liq0": stats["liq"], "vol0": stats["vol"], "eid": str(ev.get("id")), "status": "open"})
                if a.get("link"):
                    links.append(f"{w['home']} vs {w['away']}\n{a['link']}")
            known.append(str(ev.get("id")))
        watch[:] = remaining
    st["preds"] = preds[-300:]
    st["last_links"] = links[-10:]
    st["flow"] = flow
    st["flow_sig"] = flow_sig
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
