import Core as C
import traceback

def main():
    cur = C.soccer_standings()
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    ls = (now.year if now.month >= 7 else now.year - 1) - 1
    last = C.soccer_standings(ls)
    
    tests = [
        ("eng.2", "Burnley", "Bristol City"),
        ("eng.2", "Wrexham", "Burnley"),
        ("eng.1", "Manchester City", "Coventry City"),
    ]
    
    msg = "🔬 DIAGNOSTIC v2 — داده‌های جدول\n\n"
    
    for slug, home, away in tests:
        msg += f"=== {home} vs {away} ({slug}) ===\n"
        
        ht = cur.get(slug, {}).get(home, {})
        at = cur.get(slug, {}).get(away, {})
        
        msg += f"\n📊 جدول فعلی (season {now.year}):\n"
        msg += f"  {home}: rank={ht.get('rank', 'N/A')}, played={ht.get('played', 0)}\n"
        msg += f"  {away}: rank={at.get('rank', 'N/A')}, played={at.get('played', 0)}\n"
        
        lh = last.get(slug, {}).get(home, {})
        la = last.get(slug, {}).get(away, {})
        
        msg += f"\n📊 جدول فصل قبل (season {ls}):\n"
        msg += f"  {home}: rank={lh.get('rank', 'N/A')}, played={lh.get('played', 0)}\n"
        msg += f"  {away}: rank={la.get('rank', 'N/A')}, played={la.get('played', 0)}\n"
        
        m = {"sport": "soccer", "slug": slug, "home": home, "away": away}
        c = C.compute(m, cur, last, {})
        if c:
            msg += f"\n✅ محاسبه مدل:\n"
            msg += f"  stronger: {c['stronger']}\n"
            msg += f"  prob: {round(c['prob']*100)}%\n"
            msg += f"  gap: {round(c['gap'])}\n"
        else:
            msg += f"\n❌ محاسبه مدل: None (gap زیر آستانه)\n"
        
        msg += "\n" + "="*50 + "\n\n"
    
    C.send(msg, html=False)
    print(msg)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        e = traceback.format_exc()
        print(e)
        C.send("❌ خطا:\n" + e[-2000:], html=False)
        raise
