import Core as C
import json
import traceback
from datetime import datetime, timezone, timedelta

def is_past(ds, grace=1.0):
    try:
        dt = datetime.fromisoformat(ds.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > dt + timedelta(hours=grace)
    except Exception:
        return False

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
    edge = c["prob"] - price
    kl = C.kelly(c["prob"], price)
    if edge < min_e or edge > C.MAX_EDGE or kl <= 0 or not c["solid"]:
        return None
    return {"m": m, "c": c, "price": price, "edge": edge, "kl": kl, "title": "VALUE BET زودهنگام ⚡", "league": m["league"], "date": m["date"], "home": m["home"], "away": m["away"], "stronger": c["stronger"], "prob": c["prob"], "label": "به‌وضوح نابرابر 🟠", "icon": "🎾" if m["sport"] == "tennis" else "⚽", "link": C.poly_link(ev), "note": "⚡ بازار تازه ایجاد شد", "hcr": c.get("hcr"), "hlr": c.get("hlr"), "acr": c.get("acr"), "alr": c.get("alr"), "bh": c.get("bh"), "ba": c.get("ba")}

def main():
    st = C.load_state()
    known = st.setdefault("known_poly", [])
    noted = st.setdefault("notified", [])
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
    min_e = prefs.get("min_edge", C.MIN_EDGE)
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    evs = C.poly_events()
    fresh = [e for e in evs if str(e.get("id")) not in known]
    print("poly:", len(evs), "fresh:", len(fresh))
    sent = 0
    EXIT = 0.08
    STOP = -0.08
    STEAM = 0.05
    MOVE = 0.03
    open_eids = set()
    for p in preds:
        if p.get("status") == "open" and p.get("eid"):
            open_eids.add(p["eid"])
    cur = tr = last = None
    for e in evs[:150]:
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
        if eid in open_eids or eid in flow_sig or is_past(e.get("startDate") or ""):
            continue
        if hour_flow >= 500 and s["liq"] < 15000:
            if cur is None:
                cur = C.soccer_standings()
                tr = C.tennis_rankings()
            m = build_m(e, cur, tr)
            if not m or m["league"] in off_l:
                continue
            hn, an = C.norm(m["home"]), C.norm(m["away"])
            sn = C.norm(rec["side"])
            if sn in hn or hn in sn:
                stronger = m["home"]
            elif sn in an or an in sn:
                stronger = m["away"]
            else:
                continue
            flow_sig.append(eid)
            C.send(f"🌊 سیگنال ورود پول هوشمند\n⚽ {m['home']} vs {m['away']}\n💰 پول ۱ ساعت: {C.fa(int(hour_flow))} دلار\n🎯 سمت جریان: {stronger} @ {C.fa(round(rec['p']*100))}٪\n💧 {C.STAGE_FA[C.liq_stage(s['liq'])]}\n⚠️ بر پایه جریان پول (نه مدل) — احتیاط\n📋 لینک:\n{C.poly_link(e)}", html=False)
            preds.append({"home": m["home"], "away": m["away"], "sport": m["sport"], "slug": m["slug"], "date": m["date"], "prob": rec["p"], "price": round(rec["p"], 3), "stronger": stronger, "link": C.poly_link(e), "liq0": s["liq"], "vol0": s["vol"], "eid": eid, "status": "open", "src": "flow"})
            sent += 1
    flow_sig[:] = flow_sig[-200:]
    if len(flow) > 200:
        for k in list(flow.keys())[:len(flow) - 200]:
            flow.pop(k, None)
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
        stage = C.liq_stage(stats["liq"])
        money_in = stats["vol"] - p.get("vol0", 0)
        flowline = f"💰 پول از ورود: {C.fa(int(money_in))} دلار | {C.STAGE_FA[stage]}"
        rec = flow.get(p.get("eid", ""))
        reversal = bool(rec) and C.norm(rec["side"]) == C.norm(p["stronger"]) and rec.get("hf", 0) >= 1000 and rec.get("hdp", 0) <= -0.03
        entry = p["price"]
        drift = curp - entry
        p["last"] = curp
        if reversal:
            p["status"] = "closed"
            p["pnl"] = round(drift, 3)
            ret = round(drift / entry * 100) if entry else 0
            C.send(f"🛑 خروج واگرایی جریان\n⚽ {p['home']} vs {p['away']}\n💰 پول اومد ولی قیمت برگشت علیه ما\n📥 ورود: {C.fa(round(entry*100))}٪ | 📤 الان: {C.fa(round(curp*100))}٪ | P/L: ~{C.fa(ret)}٪\n{flowline}\n📋 {p['link']}", html=False)
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
    if fresh or watch:
        if cur is None:
            cur = C.soccer_standings()
            tr = C.tennis_rankings()
        ls = (now.year if now.month >= 7 else now.year - 1) - 1
        last = C.soccer_standings(ls)
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
            edge = c["prob"] - price
            kl = C.kelly(c["prob"], price)
            is_value = c["solid"] and edge >= min_e and edge <= C.MAX_EDGE and kl > 0
            note = None
            if edge > C.MAX_EDGE:
                note = "⚠️ لبه مشکوک (زیاد) — با احتیاط!"
            elif not c["solid"]:
                note = "⚠️ اوایل فصل/داده کم — فقط اطلاع"
            elif not is_value and edge < min_e:
                note = f"❌ لبه کم ({C.fa(round(edge*100,1))}٪) — فقط برای اطلاع"
            stats = C.market_stats(ev, w["home"], w["away"], w["sport"])
            stage = C.liq_stage(stats["liq"])
            stage_line = f"💧 نقدینگی: {C.fa(int(stats['liq']))} دلار — {C.STAGE_FA[stage]}"
            note = (note + "\n" + stage_line) if note else stage_line
            a = {"title": "بازار باز شد + VALUE BET 💰" if is_value else "بازار Polymarket باز شد ⚡", "league": w["league"], "date": w["date"], "home": w["home"], "away": w["away"], "stronger": c["stronger"], "prob": c["prob"], "price": price, "edge": edge, "kelly": kl if is_value else 0, "label": "به‌وضوح نابرابر 🟠", "icon": "🎾" if w["sport"] == "tennis" else "⚽", "link": C.poly_link(ev), "note": note, "hcr": c.get("hcr"), "hlr": c.get("hlr"), "acr": c.get("acr"), "alr": c.get("alr"), "bh": c.get("bh"), "ba": c.get("ba")}
            if only_v and not is_value:
                known.append(str(ev.get("id")))
                continue
            if C.notify("⚡", a):
                sent += 1
                noted.append(str(ev.get("id")))
                preds.append({"home": w["home"], "away": w["away"], "sport": w["sport"], "slug": w["slug"], "date": w["date"], "prob": round(c["prob"], 3), "price": round(price, 3), "stronger": c["stronger"], "link": a.get("link"), "liq0": stats["liq"], "vol0": stats["vol"], "eid": str(ev.get("id")), "status": "open"})
                if a.get("link"):
                    links.append(f"{w['home']} vs {w['away']}\n{a['link']}")
            known.append(str(ev.get("id")))
        watch[:] = remaining
        for e in fresh[:10]:
            try:
                a = analyze_ev(e, cur, last, tr, min_e, cal)
                if a and a["league"] not in off_l and str(e.get("id")) not in noted:
                    stats = C.market_stats(e, a["home"], a["away"], a["m"]["sport"])
                    stage = C.liq_stage(stats["liq"])
                    stage_line = f"💧 نقدینگی: {C.fa(int(stats['liq']))} دلار — {C.STAGE_FA[stage]}"
                    a["note"] = (a["note"] + "\n" + stage_line) if a.get("note") else stage_line
                    if C.notify("⚡", a):
                        sent += 1
                        noted.append(str(e.get("id")))
                        preds.append({"home": a["home"], "away": a["away"], "sport": a["m"]["sport"], "slug": a["m"]["slug"], "date": a["date"], "prob": round(a["prob"], 3), "price": round(a["price"], 3), "stronger": a["stronger"], "link": a.get("link"), "liq0": stats["liq"], "vol0": stats["vol"], "eid": str(e.get("id")), "status": "open"})
                        if a.get("link"):
                            links.append(f"{a['home']} vs {a['away']}\n{a['link']}")
            except Exception as ex:
                print("ev err:", ex)
    st["preds"] = preds[-300:]
    st["last_links"] = links[-10:]
    st["flow"] = flow
    st["flow_sig"] = flow_sig
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
