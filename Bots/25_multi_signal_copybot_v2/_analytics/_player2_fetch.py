"""Fetch player2 activity + positions from Polymarket data-api.
Player: 0x9bbd88140ccba06100da00476257d9cffce56e72
"""
import sys, io, json, os, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import urllib.request, urllib.parse

WALLET = "0x9bbd88140ccba06100da00476257d9cffce56e72"
OUT_DIR = r"C:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot_v2/_analytics/data"
os.makedirs(OUT_DIR, exist_ok=True)

def _get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            last = e
            print(f"  retry {i+1}/{tries} on {url[:80]}: {e}")
            time.sleep(2)
    raise last

# 1) Activity pagination
activity = []
offset = 0
limit = 500
while True:
    url = f"https://data-api.polymarket.com/activity?user={WALLET}&limit={limit}&offset={offset}"
    try:
        batch = _get(url)
    except Exception as e:
        print(f"FATAL activity {offset}: {e}")
        break
    if not isinstance(batch, list) or len(batch) == 0:
        break
    activity.extend(batch)
    print(f"activity offset={offset} -> +{len(batch)} total={len(activity)}")
    if len(batch) < limit:
        break
    offset += limit
    time.sleep(0.3)

with open(os.path.join(OUT_DIR, "player2_activity_ALL.json"), "w", encoding="utf-8") as f:
    json.dump(activity, f, ensure_ascii=False)
print(f"SAVED activity: {len(activity)} events")

# 2) Positions
positions = []
offset = 0
while True:
    url = f"https://data-api.polymarket.com/positions?user={WALLET}&limit=500&offset={offset}"
    try:
        batch = _get(url)
    except Exception as e:
        print(f"FATAL positions {offset}: {e}")
        break
    if not isinstance(batch, list) or len(batch) == 0:
        break
    positions.extend(batch)
    print(f"positions offset={offset} -> +{len(batch)} total={len(positions)}")
    if len(batch) < 500:
        break
    offset += 500
    time.sleep(0.3)

with open(os.path.join(OUT_DIR, "player2_positions.json"), "w", encoding="utf-8") as f:
    json.dump(positions, f, ensure_ascii=False)
print(f"SAVED positions: {len(positions)} rows")

# 3) Profile attempt (several possible endpoints)
profile = {}
for pu in [
    f"https://data-api.polymarket.com/profile/{WALLET}",
    f"https://data-api.polymarket.com/profile?user={WALLET}",
    f"https://gamma-api.polymarket.com/profile?wallet={WALLET}",
    f"https://lb-api.polymarket.com/user?user={WALLET}",
]:
    try:
        p = _get(pu, tries=1)
        profile[pu] = p
        print(f"profile OK {pu}")
    except Exception as e:
        print(f"profile fail {pu}: {e}")

# Derive name/pseudonym from first activity row
if activity:
    profile["_from_activity"] = {
        "name": activity[0].get("name"),
        "pseudonym": activity[0].get("pseudonym"),
        "bio": activity[0].get("bio"),
    }
with open(os.path.join(OUT_DIR, "player2_profile.json"), "w", encoding="utf-8") as f:
    json.dump(profile, f, ensure_ascii=False, indent=2)
print("DONE")
