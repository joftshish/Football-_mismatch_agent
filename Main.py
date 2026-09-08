import Core as C
from datetime import datetime, timezone

def main():
    now = datetime.now(timezone.utc)
    ls = (now.year if now.month >= 7 else now.year - 1) - 1
    cur = C.soccer_standings()
    last = C.soccer_standings(ls)
    slug = "eng.3"
    home, away = "Blackpool", "Bromley"
    t = cur.get(slug, {})
    hd, ad = t.get(home, {}), t.get(away, {})
    lh = last.get(slug, {}).get(home, {})
    la = last.get(slug, {}).get(away, {})
    hp_ = hd.get("played", 0)
    ap_ = ad.get("played", 0)
    hcr = hd.get("rank") if hp_ >= 5 else None
    acr = ad.get("rank") if ap_ >= 5 else None
    hlr = lh.get("rank")
    alr = la.get("rank")
    def eff(cr, lr, played):
        if cr is None and lr is None:
            return float(C.DEFAULT_RANK)
        if cr is None:
            return float(lr)
        if lr is None:
            return float(cr)
        w = min(1.0, played / 12.0)
        return cr * w + lr * (1 - w)
    ehr = eff(hcr, hlr, hp_)
    ear = eff(acr, alr, ap_)
    early = min(hp_, ap_) < 8
    soft = early or slug in C.VOLATILE
    mult = 2 if soft else 3
    fbw = 25 if soft else 15
    gbw = 8 if soft else 5
    gbc = 15 if soft else 10
    home_b = 6 if soft else 8
    def parts(d, played):
        if not played:
            return 0, 0
        fb = (d.get("wins", 0) / played - 0.4) * fbw
        gb = max(-gbc, min(gbc, ((d.get("gf", 0) - d.get("ga", 0)) / played) * gbw))
        return fb, gb
    fb_h, gb_h = parts(hd, hp_)
    fb_a, gb_a = parts(ad, ap_)
    base_h = 100 - ehr * mult
    base_a = 100 - ear * mult
    ph = max(0, min(100, base_h + fb_h + gb_h + home_b))
    pa = max(0, min(100, base_a + fb_a + gb_a))
    gap = abs(ph - pa)
    prob = C.model_prob(gap)
    if early:
        prob = min(prob, 0.80)
    msg = f"🔬 آنالیز زنده (core17) — {home} vs {away}\n\n"
    msg += f"حالت: {'اوایل فصل' if early else 'معمولی'} | {'پرنوسان' if slug in C.VOLATILE else 'پایدار'}\nضرایب: رتبه×{mult} | برد×{fbw} | گل×{gbw} | میزبانی {home_b}\n\n"
    msg += f"=== {home} (میزبان) ===\n"
    msg += f"🏅 جاری: {hcr or '—'} | قبل: {hlr or '—'} → مؤثر: {round(ehr,1)}\n"
    msg += f"➕ base: {round(base_h,1)} | fb: {round(fb_h,1)} | gb: {round(gb_h,1)} | میزبانی: {home_b}\n"
    msg += f"💪 power: {round(ph,1)}\n\n"
    msg += f"=== {away} (مهمان) ===\n"
    msg += f"🏅 جاری: {acr or '—'} | قبل: {alr or '—'} → مؤثر: {round(ear,1)}\n"
    msg += f"➕ base: {round(base_a,1)} | fb: {round(fb_a,1)} | gb: {round(gb_a,1)} | میزبانی: 0\n"
    msg += f"💪 power: {round(pa,1)}\n\n"
    msg += f"🎯 GAP: {round(gap,1)}\n📊 احتمال نهایی: {round(prob*100)}٪\n💰 بازار: ۵۴٪\n\n"
    d_base = base_h - base_a
    d_fb = fb_h - fb_a
    d_gb = gb_h - gb_a
    d_hm = float(home_b)
    tot = d_base + d_fb + d_gb + d_hm
    if tot:
        msg += "🧩 سهم هر عامل از gap:\n"
        msg += f"  رتبه مؤثر (جاری+قبل): {round(d_base,1)} ({round(d_base/tot*100)}٪)\n"
        msg += f"  نرخ برد: {round(d_fb,1)} ({round(d_fb/tot*100)}٪)\n"
        msg += f"  تفاضل گل: {round(d_gb,1)} ({round(d_gb/tot*100)}٪)\n"
        msg += f"  میزبانی: {round(d_hm,1)} ({round(d_hm/tot*100)}٪)\n"
    C.send(msg, html=False)
    print(msg)

if __name__ == "__main__":
    main()
