import Core as C
from datetime import datetime, timezone

SLUG = "eng.3"
HOME = "Blackpool"
AWAY = "Bromley"

def main():
    now = datetime.now(timezone.utc)
    ls = (now.year if now.month >= 7 else now.year - 1) - 1
    cur = C.soccer_standings()
    last = C.soccer_standings(ls)
    tr = C.tennis_rankings()
    m = {"id": "dbg", "sport": "soccer", "league": "", "slug": SLUG, "date": "", "home": HOME, "away": AWAY}
    c = C.compute(m, cur, last, tr)
    if not c:
        C.send("❌ compute چیزی برنگردوند (داده کم یا gap زیر آستانه)", html=False)
        return
    d = c.get("detail") or {}
    h, a = d.get("h", {}), d.get("a", {})
    msg = f"🔬 آنالیز زنده ({getattr(C, 'VERSION', '?')}) — {HOME} vs {AWAY}\n\n"
    msg += f"حالت: {'اوایل فصل' if d.get('early') else 'معمولی'} | {'پرنوسان' if d.get('soft') else 'پایدار'}\nضرایب: رتبه×{d.get('mult')} | برد×{d.get('fbw')} | گل×{d.get('gbw')} | میزبانی {h.get('home')}\n\n"
    for tag, side, name in (("میزبان", h, HOME), ("مهمان", a, AWAY)):
        msg += f"=== {name} ({tag}) ===\n"
        msg += f"🏅 جاری: {side.get('cr') or '—'} | قبل: {side.get('lr') or '—'} → مؤثر: {side.get('eff')}\n"
        msg += f"➕ base: {side.get('base')} | fb: {side.get('fb')} | gb: {side.get('gb')} | میزبانی: {side.get('home')}\n"
        msg += f"⚡ بوست: {C.boost_tag(side.get('boost'))}\n"
        msg += f"💪 power: {side.get('power')}\n\n"
    msg += f"🎯 GAP: {round(c['gap'],1)}\n📊 احتمال: {C.fa(round(c['prob']*100))}٪\n\n"
    d_base = h.get("base", 0) - a.get("base", 0)
    d_fb = h.get("fb", 0) - a.get("fb", 0)
    d_gb = h.get("gb", 0) - a.get("gb", 0)
    d_hm = h.get("home", 0) - a.get("home", 0)
    tot = d_base + d_fb + d_gb + d_hm
    if tot:
        msg += "🧩 سهم از gap:\n"
        msg += f"  رتبه مؤثر: {round(d_base,1)} ({round(d_base/tot*100)}٪)\n"
        msg += f"  نرخ برد: {round(d_fb,1)} ({round(d_fb/tot*100)}٪)\n"
        msg += f"  تفاضل گل: {round(d_gb,1)} ({round(d_gb/tot*100)}٪)\n"
        msg += f"  میزبانی: {round(d_hm,1)} ({round(d_hm/tot*100)}٪)\n"
    C.send(msg, html=False)
    print(msg)

if __name__ == "__main__":
    main()
