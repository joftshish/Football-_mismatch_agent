import Core as C
import traceback
from datetime import datetime, timezone, timedelta

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

def played_of(cur, last, m, side):
    d = cur.get(m["slug"], {}).get(m[side], {})
    p = d.get("played", 0)
    if p:
        return p, True
    ld = last.get(m["slug"], {}).get(m[side], {})
    return ld.get("played", 0), False

def main():
    print("=== v29 ===")
    st = C.load_state()
    prefs = st.get("prefs", {})
    cal = st.get("calib", 1.0)
    force = prefs.get("force", False)
    if force:
        noted, known, watch_noted, dup = [], [], [], []
        prefs["force"] = False
    else:
        noted = st.setdefault("notified", [])
        known = st.setdefault("known_poly", [])
        watch_noted = st.setdefault("watch_noted", [])
    dup = st.setdefault("dup", [])
    dup_set = set(dup)
    watch = st.setdefault("watchlist", [])
    watch[:] = [w for w in watch if not is_past(w.get("date", ""))]
    preds = st.setdefault("preds", [])
    links = st.setdefault("last_links", [])
    off_l = set(prefs.get("off", []))
    only_v = prefs.get("only_value", False)
    min_e = prefs.get("min_edge", 0.02)
    now = datetime.now(timezone.utc)
    ls = (now.year if now.month >= 7 else now.year - 1) - 1
    cache = C.standings_cache_load(st)
    if cache and cache.get("ls") == ls:
        cur, last = cache["cur"], cache["last"]
        fx = C.soccer_fixtures() + C.tennis_fixtures()
        print("standings from cache")
    else:
        fx = C.soccer_fixtures() + C.tennis_fixtures()
        cur = C.soccer_standings()
        last = C.soccer_standings(ls)
        C.standings_cache_save(st, cur, last, ls)
    tr = C.tennis_rankings()
    pev = fetch_poly()
    vb = mm = wl = skipped = 0
    rows = []
    rejected = []
    for m in fx:
        if m["league"] in off_l:
            continue
        c = C.compute(m, cur, last, tr)
        if not c:
            rejected.append((m["home"], m["away"], "گپ زیر آستانه"))
            continue
        c["prob"] = 0.5 + (c["prob"] - 0.5) * cal
        if m["sport"] == "tennis":
            solid2 = bool(c.get("solid"))
            early = False
        else:
            hp, h_cur = played_of(cur, last, m, "home")
            ap, a_cur = played_of(cur, last, m, "away")
            early = min(hp, ap) < 8
            solid2 = (h_cur and a_cur and hp >= 5 and ap >= 5) or ((not h_cur) and (not a_cur) and hp >= 20 and ap >= 20)
        ev = C.find_poly(pev, m["home"], m["away"], m["sport"], m["date"])
        src = "list"
        if not ev:
            ev, _ = C.search_poly(m["home"], m["away"], m["sport"], m["date"])
            src = "search"
        ph = pa = None
        if ev:
            ph, pa = C.poly_prices(ev, m["home"], m["away"], m["sport"])
        dkey = f"{m['home']}|{m['away']}"
        if ev and ph is not None:
            price = ph if c["sh"] else pa
            P = c.get("pred", 0.6)
            c["prob"] = P * c["prob"] + (1 - P) * price
            edge = c["prob"] - price
            cap = 0.01 if early else 0.02
            hold_ok = solid2 and P >= 0.65 and not c.get("cross") and edge >= min_e and edge <= C.MAX_EDGE
            kl = C.kelly(c["prob"], price, cap) if hold_ok else 0.0
            is_value = hold_ok and kl > 0
            sigtype = "✅ Hold — تا پایان بازی" if is_value else "🎯 Trade — خروج قبل از بازی"
            size = f"تا {C.fa(round(kl*100,1))}٪ سرمایه" if is_value else "حداکثر ۱٪ (ترید کوتاه)"
            note = None
            if edge > C.MAX_EDGE:
                note = "⚠️ لبه مشکوک (زیاد) — با احتیاط!"
            elif early:
                note = "⚠️ اوایل فصل — فقط Trade با سایز کوچک"
            elif not is_value and edge < min_e:
                note = f"❌ لبه کم ({C.fa(round(edge*100,1))}٪) — ارزش بستن ندارد"
                rejected.append((m["home"], m["away"], f"لبه {C.fa(round(edge*100,1))}٪"))
            lab = "کاملاً نابرابر 🔴" if c["gap"] >= c["thr"] + 10 else "به‌وضوح نابرابر 🟠"
            a = {"title": "VALUE BET 💰" if is_value else "بازی نابرابر ⚔️", "league": m["league"], "date": m["date"], "home": m["home"], "away": m["away"], "stronger": c["stronger"], "prob": c["prob"], "price": price, "edge": edge, "kelly": kl if is_value else 0, "label": lab, "icon": "🎾" if m["sport"] == "tennis" else "⚽", "link": C.poly_link(ev), "note": note, "sigtype": sigtype, "size": size, "hr": c.get("hr"), "ar": c.get("ar"), "rsrc": c.get("rsrc"), "hcr": c.get("hcr"), "hlr": c.get("hlr"), "acr": c.get("acr"), "alr": c.get("alr"), "hcty": c.get("hcty", ""), "acty": c.get("acty", ""), "bh": c.get("bh"), "ba": c.get("ba")}
            rows.append((c["gap"], f"{m['home']} - {m['away']}\n   گپ {C.fa(round(c['gap']))} | بازار {C.fa(round(price*100))}٪ | لبه {C.fa(round(edge*100,1))}٪"))
            eid = str(ev.get("id"))
            if dkey not in dup_set and m["id"] not in noted and eid not in known:
                if only_v and not is_value:
                    noted.append(m["id"])
                    known.append(eid)
                    continue
                if C.notify("💰" if is_value else "⚔️", a):
                    if is_value:
                        vb += 1
                    else:
                        mm += 1
                    noted.append(m["id"])
                    known.append(eid)
                    dup.append(dkey)
                    dup_set.add(dkey)
                    preds.append({"home": m["home"], "away": m["away"], "sport": m["sport"], "slug": m["slug"], "date": m["date"], "prob": round(c["prob"], 3), "price": round(price, 3), "stronger": c["stronger"], "link": a.get("link"), "eid": eid, "vol0": 0, "liq0": 0, "status": "open"})
                    if a.get("link"):
                        links.append(f"{m['home']} vs {m['away']}\n{a['link']}")
        else:
            if is_past(m["date"]):
                continue
            skipped += 1
            status = "بدون بازار" if not ev else f"بازار هست/قیمت نه ({src})"
            rejected.append((m["home"], m["away"], status))
            rows.append((c["gap"], f"{m['home']} - {m['away']}\n   گپ {C.fa(round(c['gap']))} | {status}"))
            key = dkey
            if key not in watch_noted and key not in dup_set:
                if not only_v and C.notify_watch(m, c):
                    watch_noted.append(key)
                    dup.append(key)
                    dup_set.add(key)
                    watch.append({"home": m["home"], "away": m["away"], "sport": m["sport"], "slug": m["slug"], "date": m["date"], "league": m["league"]})
                    wl += 1
    st["preds"] = preds[-300:]
    st["last_links"] = links[-10:]
    st["dup"] = dup[-500:]
    rows.sort(reverse=True)
    top = "\n".join(r[1] for r in rows[:8]) or "—"
    rej = "\n".join(f"• {h} - {a}: {r}" for h, a, r in rejected[:10]) or "—"
    C.send(f"📊 گزارش v29 | {getattr(C, 'VERSION', '?')}\nبازی‌ها: {C.fa(len(fx))} | بدون بازار: {C.fa(skipped)}\n💰 Value: {C.fa(vb)} | ⚔️ نابرابر: {C.fa(mm)} | 👀 Watch: {C.fa(wl)}\n\nبرترین‌ها:\n{top}\n\n❌ بررسی شد و رد شد:\n{rej}", html=False)
    st["last_summary"] = now.strftime("%Y-%m-%d")
    C.save_state(st)
    print("done", vb, mm, wl)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        C.send("❌ خطا:\n" + e[-2000:], html=False)
        raise
