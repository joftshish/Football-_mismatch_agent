"""⚽ ایجنت بازی‌های نابرابر - نسخه ۲ (با گزارش خطا به تلگرام)"""
import httpx
import json
import os
import traceback
from datetime import datetime, timedelta, timezone

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE = "state.json"
DAYS_AHEAD = 5
MIN_PLAYED = 5
MISMATCH_THRESHOLD = 45
HOME_ADVANTAGE = 8

LEAGUES = {
    "eng.1": "🏴 لیگ برتر انگلیس",
    "esp.1": "🇪 لالیگا",
    "ger.1": "🇩🇪 بوندس‌لیگا",
    "ita.1": "🇮 سری آ",
    "fra.1": "🇫🇷 لیگ ۱ فرانسه",
}

LAST_SEASON = {
    "eng.1": {"Manchester City":1,"Arsenal":2,"Liverpool":3,"Chelsea":4,
              "Newcastle United":5,"Tottenham Hotspur":6,"Brighton & Hove Albion":7,
              "Aston Villa":8,"West Ham United":9,"Crystal Palace":10,
              "Brentford":11,"Fulham":12,"Wolverhampton Wanderers":13,
              "Everton":14,"AFC Bournemouth":15,"Nottingham Forest":16,
              "Luton Town":17,"Burnley":18,"Sheffield United":19,"Ipswich Town":20},
    "esp.1": {"Real Madrid":1,"FC Barcelona":2,"Atlético Madrid":3,"Athletic Club":4,
              "Real Sociedad":5,"Villarreal":6,"Real Betis":7,"Valencia":8,
              "Sevilla":9,"Getafe":10,"Osasuna":11,"Girona":12,"Celta Vigo":13,
              "Mallorca":14,"Las Palmas":15,"Rayo Vallecano":16,"Alavés":17,
              "Granada":18,"Cádiz":19,"Almería":20},
    "ger.1": {"Bayern Munich":1,"Borussia Dortmund":2,"RB Leipzig":3,"Bayer Leverkusen":4,
              "Eintracht Frankfurt":5,"VfB Stuttgart":6,"SC Freiburg":7,"TSG Hoffenheim":8,
              "VfL Wolfsburg":9,"Borussia Mönchengladbach":10,"Werder Bremen":11,
              "FC Augsburg":12,"1. FC Union Berlin":13,"1. FC Köln":14,
              "SV Darmstadt 98":15,"1. FSV Mainz 05":16,"FC Heidenheim":17,"FC Schalke 04":18},
    "ita.1": {"Inter Milan":1,"AC Milan":2,"Juventus":3,"Napoli":4,"Atalanta":5,
              "Roma":6,"Lazio":7,"Fiorentina":8,"Bologna":9,"Torino":10,"Monza":11,
              "Udinese":12,"Sassuolo":13,"Empoli":14,"Cagliari":15,"Verona":16,
              "Lecce":17,"Frosinone":18,"Salernitana":19,"Genoa":20},
    "fra.1": {"Paris Saint-Germain":1,"Monaco":2,"Marseille":3,"Lille":4,"Lyon":5,
              "Nice":6,"Lens":7,"Rennes":8,"Strasbourg":9,"Nantes":10,"Montpellier":11,
              "Toulouse":12,"Brest":13,"Le Havre":14,"Reims":15,"Metz":16,
              "Lorient":17,"Clermont":18},
}

WEEKDAYS = ["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنجشنبه","جمعه"]
MONTHS = ["فروردین","اردیبهشت","خرداد","تیر","مرداد","شهریور",
          "مهر","آبان","آذر","دی","بهمن","اسفند"]


def to_jalali(dt):
    try:
        import jdatetime
        j = jdatetime.datetime.fromgregorian(datetime=dt)
        return f"{WEEKDAYS[j.weekday()]} {j.day} {MONTHS[j.month-1]} {j.year}", j.strftime("%H:%M")
    except Exception:
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def fetch_fixtures():
    fixtures = []
    base = "https://site.api.espn.com/apis"
    today = datetime.now(timezone.utc)
    for i in range(DAYS_AHEAD):
        date_str = (today + timedelta(days=i)).strftime("%Y%m%d")
        for slug, name in LEAGUES.items():
            url = f"{base}/site/v2/sports/soccer/{slug}/scoreboard"
            try:
                data = httpx.get(url, params={"dates": date_str}, timeout=15).json()
                for ev in data.get("events", []):
                    comp = ev.get("competitions", [{}])[0]
                    comps = comp.get("competitors", [])
                    home = next((c for c in comps if c.get("homeAway") == "home"), None)
                    away = next((c for c in comps if c.get("homeAway") == "away"), None)
                    if home and away:
                        hn = (home.get("team") or {}).get("displayName", "")
                        an = (away.get("team") or {}).get("displayName", "")
                        if hn and an:
                            fixtures.append({
                                "id": str(ev.get("id", "")),
                                "league": name, "slug": slug,
                                "date": ev.get("date", ""),
                                "home": hn, "away": an,
                            })
            except Exception as e:
                print(f"⚠️ خطا {slug} {date_str}: {e}")
    return fixtures


def fetch_standings():
    standings = {}
    base = "https://site.api.espn.com/apis"
    for slug in LEAGUES:
        url = f"{base}/v2/sports/soccer/{slug}/standings"
        try:
            data = httpx.get(url, timeout=15).json()
            table = {}
            for child in data.get("children", []):
                for entry in child.get("standings", {}).get("entries", []):
                    team = (entry.get("team") or {}).get("displayName", "")
                    stats = {s.get("name"): s.get("value", 0) for s in entry.get("stats", [])}
                    if team:
                        table[team] = {
                            "rank": int(stats.get("rank", 20)),
                            "played": int(stats.get("gamesPlayed", 0)),
                            "wins": int(stats.get("wins", 0)),
                        }
            standings[slug] = table
        except Exception as e:
            print(f"⚠️ خطا جدول {slug}: {e}")
            standings[slug] = {}
    return standings


def effective_rank(team, current, slug):
    if current.get("played", 0) >= MIN_PLAYED:
        return current.get("rank", 20), False
    return LAST_SEASON.get(slug, {}).get(team, 14), True


def calc_power(rank, data, is_home):
    base = 100 - (rank * 3)
    played = data.get("played", 0)
    form_bonus = ((data.get("wins", 0) / played) - 0.4) * 20 if played else 0
    home_bonus = HOME_ADVANTAGE if is_home else 0
    return max(0, min(100, base + form_bonus + home_bonus))


def analyze(match, standings):
    slug = match["slug"]
    table = standings.get(slug, {})
    home_data = table.get(match["home"], {})
    away_data = table.get(match["away"], {})
    home_rank, low1 = effective_rank(match["home"], home_data, slug)
    away_rank, low2 = effective_rank(match["away"], away_data, slug)
    home_power = calc_power(home_rank, home_data, True)
    away_power = calc_power(away_rank, away_data, False)
    gap = abs(home_power - away_power)

    if gap >= 80:
        label = "کاملاً نابرابر ⚫"
    elif gap >= 65:
        label = "به‌وضوح نابرابر 🔴"
    elif gap >= MISMATCH_THRESHOLD:
        label = "نابرابر 🟠"
    else:
        label = None

    return {**match, "home_rank": home_rank, "away_rank": away_rank,
            "home_power": round(home_power, 1), "away_power": round(away_power, 1),
            "gap": round(gap, 1), "label": label,
            "is_mismatch": gap >= MISMATCH_THRESHOLD, "low_data": low1 or low2}


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        r = httpx.post(url, json={"chat_id": CHAT_ID, "text": text,
                                  "parse_mode": "HTML"}, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"❌ خطا تلگرام: {e}")
        return False


def build_message(a):
    try:
