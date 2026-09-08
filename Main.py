import Core as C

def main():
    cur = C.soccer_standings()
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    ls = (now.year if now.month >= 7 else now.year - 1) - 1
    last = C.soccer_standings(ls)
    
    slug = "eng.3"
    home, away = "Blackpool", "Bromley"
    
    t = cur.get(slug, {})
    hd, ad = t.get(home, {}), t.get(away, {})
    
    def calc(name, d, is_home):
        base = 100 - d.get("rank", 17) * 3
        played = d.get("played", 0)
        wins = d.get("wins", 0)
        gf = d.get("gf", 0)
        ga = d.get("ga", 0)
        if played > 0:
            fb = (wins / played - 0.4) * 15
            gb = max(-10, min(10, ((gf - ga) / played) * 5))
        else:
            fb = gb = 0
        home_bonus = 8 if is_home else 0
        power = max(0, min(100, base + fb + gb + home_bonus))
        return {
            "name": name, "rank": d.get("rank"), "played": played,
            "wins": wins, "gf": gf, "ga": ga,
            "base": base, "fb": round(fb, 2), "gb": round(gb, 2),
            "home_bonus": home_bonus, "power": round(power, 2)
        }
    
    hp = calc(home, hd, True)
    ap = calc(away, ad, False)
    gap = abs(hp["power"] - ap["power"])
    prob = C.model_prob(gap)
    
    msg = f"🔬 آنالیز {home} vs {away}\n\n"
    msg += f"=== {home} (میزبان) ===\n"
    msg += f"🏅 رتبه: {hp['rank']}\n"
    msg += f"📊 بازی: {hp['played']} | برد: {hp['wins']}\n"
    msg += f"⚽ گل: {hp['gf']} زده / {hp['ga']} خورده\n"
    msg += f"➕ base (100 - rank*3): {hp['base']}\n"
    msg += f"➕ fb (نرخ برد): {hp['fb']}\n"
    msg += f"➕ gb (تفاضل گل): {hp['gb']}\n"
    msg += f"➕ میزبانی: {hp['home_bonus']}\n"
    msg += f"💪 power نهایی: {hp['power']}\n\n"
    
    msg += f"=== {away} (مهمان) ===\n"
    msg += f"🏅 رتبه: {ap['rank']}\n"
    msg += f"📊 بازی: {ap['played']} | برد: {ap['wins']}\n"
    msg += f"⚽ گل: {ap['gf']} زده / {ap['ga']} خورده\n"
    msg += f"➕ base (100 - rank*3): {ap['base']}\n"
    msg += f"➕ fb (نرخ برد): {ap['fb']}\n"
    msg += f"➕ gb (تفاضل گل): {ap['gb']}\n"
    msg += f"➕ میزبانی: {ap['home_bonus']}\n"
    msg += f"💪 power نهایی: {ap['power']}\n\n"
    
    msg += f"🎯 GAP: {round(gap)}\n"
    msg += f"📊 احتمال مدل: {round(prob*100)}٪\n"
    msg += f"💰 بازار Polymarket: ۵۴٪\n"
    
    msg += "\n🧩 سهم هر عامل از gap:\n"
    diff_base = hp["base"] - ap["base"]
    diff_fb = hp["fb"] - ap["fb"]
    diff_gb = hp["gb"] - ap["gb"]
    diff_home = hp["home_bonus"] - ap["home_bonus"]
    total = diff_base + diff_fb + diff_gb + diff_home
    msg += f"  تفاوت base (رتبه): {round(diff_base,1)} ({round(diff_base/total*100)}٪ از کل)\n"
    msg += f"  تفاوت fb (نرخ برد): {round(diff_fb,1)} ({round(diff_fb/total*100)}٪ از کل)\n"
    msg += f"  تفاوت gb (تفاضل گل): {round(diff_gb,1)} ({round(diff_gb/total*100)}٪ از کل)\n"
    msg += f"  امتیاز میزبانی: {round(diff_home,1)} ({round(diff_home/total*100)}٪ از کل)\n"
    
    C.send(msg, html=False)
    print(msg)

if __name__ == "__main__":
    main()
