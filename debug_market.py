import Core as C
import json

def main():
    print("=== Debug Market ===")
    
    # یکی از بازی‌های برتر
    home = "Atlético-MG"
    away = "Chapecoense"
    sport = "soccer"
    
    print(f"\n🔍 جستجو برای: {home} vs {away}")
    
    # ۱. کلیدهای جستجو
    kh = C.keys(home, sport)
    ka = C.keys(away, sport)
    print(f"کلیدهای {home}: {kh}")
    print(f"کلیدهای {away}: {ka}")
    
    # ۲. جستجوی مستقیم
    print("\n📡 جستجوی مستقیم پلی‌مارکت:")
    q = ka[1] if len(ka) > 1 else ka[0]
    try:
        d = C.httpx.get(f"{C.POLY}/public-search", params={"q": q, "limit": 20}, timeout=15).json()
        evs = d.get("events") or (d.get("data") or {}).get("events") or []
        print(f"نتایج جستجو: {len(evs)}")
        for i, ev in enumerate(evs[:5], 1):
            title = ev.get("title", "")
            eid = ev.get("id", "")
            print(f"{i}. {title} (id: {eid})")
    except Exception as ex:
        print(f"خطای جستجو: {ex}")
    
    # ۳. جستجو با fetch_poly
    print("\n📥 بررسی ۶۰۰ رویداد اول:")
    from Fast import fetch_poly
    evs = fetch_poly()
    print(f"کل رویدادها: {len(evs)}")
    
    matches = []
    for ev in evs:
        t = C.norm(ev.get("title", ""))
        if any(k in t for k in kh) and any(k in t for k in ka):
            matches.append(ev)
    
    print(f"تطابق‌ها: {len(matches)}")
    for i, ev in enumerate(matches[:5], 1):
        title = ev.get("title", "")
        eid = ev.get("id", "")
        start = ev.get("startDate", "")
        print(f"{i}. {title} (id: {eid}, start: {start})")
    
    # ۴. اگه پیدا شد، قیمت رو چک کن
    if matches:
        ev = matches[0]
        print(f"\n💰 بررسی قیمت برای: {ev.get('title')}")
        ph, pa = C.poly_prices(ev, home, away, sport)
        print(f"قیمت {home}: {ph}")
        print(f"قیمت {away}: {pa}")
    
    print("\n=== Done ===")

if __name__ == "__main__":
    main()
