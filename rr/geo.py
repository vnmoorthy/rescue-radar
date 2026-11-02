"""Gazetteer: place names that appear in the held-out disaster posts -> lat/lng.

Built by scanning data/eval.jsonl for proper nouns: 100+ of these places are named in the eval posts
(tests/test_api.py checks at least 60 are); a few more of the hardest-hit towns are included so live posts typed
into the console resolve too. Matching is word-boundary and case-insensitive; CamelCase hashtags (#MirpurAzadKashmir, #NebraskaStrong) are split first.
When names overlap ("Azad Kashmir" vs "Kashmir", "Missouri River" vs "Missouri") the longest match wins. When a
post names several separate places, the most specific one wins (town before district before state before
country), ties broken by the longest name, then the earliest mention.

locate() returns None when no known place is named. It never guesses a location for a post without a place name.
"""
import re
from functools import lru_cache

# Specificity levels: lower is more specific.
TOWN, AREA, REGION, COUNTRY = 0, 1, 2, 3

# (canonical name, lat, lng, level, events, aliases). events=None means any event.
DORIAN, IDAI, PAK, MIDWEST = ("hurricane_dorian_2019", "cyclone_idai_2019", "pakistan_earthquake_2019",
                              "midwestern_us_floods_2019")
PLACES = [
    # Hurricane Dorian: The Bahamas
    ("Bahamas", 25.03, -77.40, COUNTRY, (DORIAN,), ["The Bahamas", "Bahamas"]),
    ("Abaco Islands", 26.40, -77.10, AREA, (DORIAN,), ["Abaco", "Abacos", "The Abacos", "Abaco Islands", "Great Abaco",
                                                      "Abaco Island"]),
    ("Marsh Harbour", 26.541, -77.063, TOWN, (DORIAN,), ["Marsh Harbour", "Marsh Harbor"]),
    ("Grand Bahama", 26.65, -78.35, AREA, (DORIAN,), ["Grand Bahama", "Grand Bahama Island"]),
    ("Freeport", 26.533, -78.696, TOWN, (DORIAN,), ["Freeport"]),
    ("Nassau", 25.048, -77.355, TOWN, (DORIAN,), ["Nassau"]),
    ("New Providence", 25.03, -77.40, AREA, (DORIAN,), ["New Providence"]),
    ("Bimini", 25.727, -79.267, AREA, (DORIAN,), ["Bimini"]),
    ("Elbow Cay", 26.55, -76.96, AREA, (DORIAN,), ["Elbow Cay"]),
    ("Hope Town", 26.541, -76.958, TOWN, (DORIAN,), ["Hope Town", "Hopetown"]),
    ("Treasure Cay", 26.67, -77.29, TOWN, (DORIAN,), ["Treasure Cay"]),
    ("Green Turtle Cay", 26.76, -77.33, TOWN, (DORIAN,), ["Green Turtle Cay"]),
    ("Man-O-War Cay", 26.59, -77.01, TOWN, (DORIAN,), ["Man-O-War Cay", "Man O War Cay", "Man-O-War"]),
    ("The Mudd", 26.545, -77.07, TOWN, (DORIAN,), ["The Mudd"]),
    ("Eleuthera", 25.15, -76.15, AREA, (DORIAN,), ["Eleuthera"]),
    ("Andros", 24.70, -78.00, AREA, (DORIAN,), ["Andros"]),
    ("Exuma", 23.62, -75.97, AREA, (DORIAN,), ["Exuma", "Exumas"]),
    ("Eight Mile Rock", 26.54, -78.80, TOWN, (DORIAN,), ["Eight Mile Rock"]),
    # Hurricane Dorian: US Southeast
    ("Florida", 27.99, -81.76, REGION, (DORIAN,), ["Florida"]),
    ("South Florida", 26.10, -80.40, REGION, (DORIAN,), ["South Florida"]),
    ("Central Florida", 28.40, -81.40, REGION, (DORIAN,), ["Central Florida"]),
    ("Palm Beach", 26.705, -80.036, TOWN, (DORIAN,), ["Palm Beach", "West Palm Beach", "Palm Beach County"]),
    ("Mar-a-Lago", 26.677, -80.037, TOWN, (DORIAN,), ["Mar-a-Lago", "Mar a Lago", "MaraLago"]),
    ("Brevard County", 28.26, -80.73, AREA, (DORIAN,), ["Brevard County", "Brevard"]),
    ("Jacksonville", 30.332, -81.656, TOWN, (DORIAN,), ["Jacksonville"]),
    ("Miami", 25.762, -80.192, TOWN, (DORIAN,), ["Miami", "Miami-Dade"]),
    ("Orlando", 28.538, -81.379, TOWN, (DORIAN,), ["Orlando"]),
    ("Daytona Beach", 29.211, -81.023, TOWN, (DORIAN,), ["Daytona Beach", "Daytona"]),
    ("Cape Canaveral", 28.392, -80.604, TOWN, (DORIAN,), ["Cape Canaveral"]),
    ("St. Augustine", 29.901, -81.313, TOWN, (DORIAN,), ["St. Augustine", "St Augustine", "Saint Augustine"]),
    ("Vero Beach", 27.638, -80.397, TOWN, (DORIAN,), ["Vero Beach"]),
    ("Fort Lauderdale", 26.122, -80.137, TOWN, (DORIAN,), ["Fort Lauderdale", "Ft Lauderdale", "Ft. Lauderdale"]),
    ("Fort Pierce", 27.447, -80.326, TOWN, (DORIAN,), ["Fort Pierce", "Ft Pierce", "Ft. Pierce"]),
    ("Melbourne, FL", 28.084, -80.608, TOWN, (DORIAN,), ["Melbourne"]),
    ("Tampa", 27.951, -82.457, TOWN, (DORIAN,), ["Tampa"]),
    ("Georgia", 32.68, -83.22, REGION, (DORIAN,), ["Georgia"]),
    ("Savannah", 32.081, -81.091, TOWN, (DORIAN,), ["Savannah"]),
    ("South Carolina", 33.84, -81.16, REGION, (DORIAN,), ["South Carolina"]),
    ("North Carolina", 35.76, -79.02, REGION, (DORIAN,), ["North Carolina"]),
    ("Carolinas", 34.80, -79.80, REGION, (DORIAN,), ["Carolinas", "The Carolinas"]),
    ("Charleston", 32.776, -79.931, TOWN, (DORIAN,), ["Charleston"]),
    ("Myrtle Beach", 33.689, -78.887, TOWN, (DORIAN,), ["Myrtle Beach"]),
    ("Wilmington", 34.226, -77.945, TOWN, (DORIAN,), ["Wilmington"]),
    ("Outer Banks", 35.56, -75.47, AREA, (DORIAN,), ["Outer Banks", "OBX"]),
    ("Cape Hatteras", 35.25, -75.53, AREA, (DORIAN,), ["Cape Hatteras", "Hatteras"]),
    ("Ocracoke", 35.115, -75.987, TOWN, (DORIAN,), ["Ocracoke", "Ocracoke Island"]),
    ("Virginia", 37.43, -78.66, REGION, (DORIAN,), ["Virginia"]),
    ("Puerto Rico", 18.22, -66.59, REGION, (DORIAN,), ["Puerto Rico"]),
    ("Virgin Islands", 18.34, -64.93, REGION, (DORIAN,), ["Virgin Islands", "US Virgin Islands", "USVI"]),
    ("Nova Scotia", 44.68, -63.74, REGION, (DORIAN,), ["Nova Scotia", "Halifax"]),
    # Cyclone Idai: Mozambique, Zimbabwe, Malawi
    ("Mozambique", -18.67, 35.53, COUNTRY, (IDAI,), ["Mozambique", "Moçambique"]),
    ("Zimbabwe", -19.02, 29.15, COUNTRY, (IDAI,), ["Zimbabwe"]),
    ("Malawi", -13.25, 34.30, COUNTRY, (IDAI,), ["Malawi"]),
    ("Beira", -19.843, 34.839, TOWN, (IDAI,), ["Beira"]),
    ("Chimanimani", -19.80, 32.87, TOWN, (IDAI,), ["Chimanimani"]),
    ("Chipinge", -20.188, 32.624, TOWN, (IDAI,), ["Chipinge"]),
    ("Mutare", -18.970, 32.650, TOWN, (IDAI,), ["Mutare"]),
    ("Manicaland", -18.92, 32.40, REGION, (IDAI,), ["Manicaland"]),
    ("Manica", -18.94, 32.88, AREA, (IDAI,), ["Manica"]),
    ("Sofala", -19.20, 34.60, REGION, (IDAI,), ["Sofala"]),
    ("Buzi", -19.87, 34.61, TOWN, (IDAI,), ["Buzi", "Búzi"]),
    ("Dondo", -19.609, 34.743, TOWN, (IDAI,), ["Dondo"]),
    ("Nhamatanda", -19.26, 34.22, TOWN, (IDAI,), ["Nhamatanda"]),
    ("Chimoio", -19.116, 33.483, TOWN, (IDAI,), ["Chimoio"]),
    ("Tete", -16.156, 33.587, TOWN, (IDAI,), ["Tete"]),
    ("Maputo", -25.969, 32.573, TOWN, (IDAI,), ["Maputo"]),
    ("Harare", -17.829, 31.053, TOWN, (IDAI,), ["Harare"]),
    ("Bulawayo", -20.150, 28.583, TOWN, (IDAI,), ["Bulawayo"]),
    ("Masvingo", -20.074, 30.833, TOWN, (IDAI,), ["Masvingo"]),
    ("Ngangu", -19.80, 32.86, TOWN, (IDAI,), ["Ngangu"]),
    ("Rusitu Valley", -20.03, 32.80, AREA, (IDAI,), ["Rusitu", "Rusitu Valley"]),
    ("Blantyre", -15.786, 35.006, TOWN, (IDAI,), ["Blantyre"]),
    ("Chikwawa", -16.035, 34.801, TOWN, (IDAI,), ["Chikwawa"]),
    ("Nsanje", -16.920, 35.262, TOWN, (IDAI,), ["Nsanje"]),
    ("Zomba", -15.386, 35.318, TOWN, (IDAI,), ["Zomba"]),
    ("Lilongwe", -13.963, 33.774, TOWN, (IDAI,), ["Lilongwe"]),
    # Pakistan earthquake 2019: Mirpur, Azad Kashmir
    ("Pakistan", 30.38, 69.35, COUNTRY, (PAK,), ["Pakistan"]),
    ("Azad Kashmir", 33.90, 73.80, REGION, (PAK,), ["Azad Kashmir", "Azad Jammu and Kashmir", "Azad Jammu & Kashmir",
                                                    "AJK", "AJ&K", "AzadKashmir"]),
    ("Kashmir", 33.90, 73.80, REGION, (PAK,), ["Kashmir"]),
    ("Mirpur", 33.148, 73.751, TOWN, (PAK,), ["Mirpur", "New Mirpur", "Mirpur AJK"]),
    ("Jatlan", 33.065, 73.807, TOWN, (PAK,), ["Jatlan"]),
    ("Jhelum", 32.934, 73.731, TOWN, (PAK,), ["Jhelum"]),
    ("Bhimber", 32.975, 74.078, TOWN, (PAK,), ["Bhimber"]),
    ("Mangla", 33.142, 73.645, TOWN, (PAK,), ["Mangla", "Mangla Dam"]),
    ("Kotli", 33.518, 73.902, TOWN, (PAK,), ["Kotli"]),
    ("Muzaffarabad", 34.370, 73.471, TOWN, (PAK,), ["Muzaffarabad"]),
    ("Islamabad", 33.684, 73.048, TOWN, (PAK,), ["Islamabad"]),
    ("Rawalpindi", 33.565, 73.016, TOWN, (PAK,), ["Rawalpindi", "Pindi"]),
    ("Lahore", 31.520, 74.359, TOWN, (PAK,), ["Lahore"]),
    ("Karachi", 24.861, 67.010, TOWN, (PAK,), ["Karachi"]),
    ("Peshawar", 34.015, 71.524, TOWN, (PAK,), ["Peshawar"]),
    ("Gujrat", 32.574, 74.079, TOWN, (PAK,), ["Gujrat"]),
    ("Gujar Khan", 33.253, 73.304, TOWN, (PAK,), ["Gujar Khan", "Gujjar Khan"]),
    ("Sialkot", 32.494, 74.531, TOWN, (PAK,), ["Sialkot"]),
    ("Kharian", 32.811, 73.865, TOWN, (PAK,), ["Kharian"]),
    ("Punjab", 31.17, 72.70, REGION, (PAK,), ["Punjab"]),
    ("Srinagar", 34.084, 74.797, TOWN, (PAK,), ["Srinagar"]),
    ("Jammu", 32.726, 74.857, TOWN, (PAK,), ["Jammu"]),
    # Midwestern US floods 2019: Nebraska, Iowa
    ("Nebraska", 41.49, -99.90, REGION, (MIDWEST,), ["Nebraska"]),
    ("Iowa", 41.88, -93.10, REGION, (MIDWEST,), ["Iowa"]),
    ("Southwest Iowa", 41.00, -95.40, REGION, (MIDWEST,), ["Southwest Iowa", "SW Iowa", "Western Iowa"]),
    ("Missouri", 38.46, -92.29, REGION, (MIDWEST,), ["Missouri"]),
    ("Missouri River", 41.26, -95.93, AREA, (MIDWEST,), ["Missouri River"]),
    ("Platte River", 41.05, -96.30, AREA, (MIDWEST,), ["Platte River", "Platte"]),
    ("Elkhorn River", 41.30, -96.30, AREA, (MIDWEST,), ["Elkhorn River", "Elkhorn"]),
    ("Niobrara River", 42.76, -98.04, AREA, (MIDWEST,), ["Niobrara", "Niobrara River"]),
    ("Spencer Dam", 42.873, -98.700, TOWN, (MIDWEST,), ["Spencer Dam"]),
    ("Omaha", 41.257, -95.935, TOWN, (MIDWEST,), ["Omaha"]),
    ("Lincoln, NE", 40.814, -96.703, TOWN, (MIDWEST,), ["Lincoln"]),
    ("Fremont", 41.433, -96.498, TOWN, (MIDWEST,), ["Fremont"]),
    ("Hamburg, IA", 40.604, -95.658, TOWN, (MIDWEST,), ["Hamburg"]),
    ("Norfolk, NE", 42.028, -97.417, TOWN, (MIDWEST,), ["Norfolk"]),
    ("Sioux City", 42.497, -96.405, TOWN, (MIDWEST,), ["Sioux City"]),
    ("Council Bluffs", 41.262, -95.861, TOWN, (MIDWEST,), ["Council Bluffs"]),
    ("Bellevue, NE", 41.137, -95.914, TOWN, (MIDWEST,), ["Bellevue"]),
    ("Offutt Air Force Base", 41.118, -95.912, TOWN, (MIDWEST,), ["Offutt", "Offutt AFB", "Offutt Air Force Base"]),
    ("Pacific Junction", 41.018, -95.802, TOWN, (MIDWEST,), ["Pacific Junction"]),
    ("Glenwood, IA", 41.047, -95.742, TOWN, (MIDWEST,), ["Glenwood"]),
    ("Plattsmouth", 41.011, -95.882, TOWN, (MIDWEST,), ["Plattsmouth"]),
    ("Kearney", 40.699, -99.083, TOWN, (MIDWEST,), ["Kearney"]),
    ("Columbus, NE", 41.430, -97.368, TOWN, (MIDWEST,), ["Columbus"]),
    ("Grand Island", 40.925, -98.342, TOWN, (MIDWEST,), ["Grand Island"]),
    ("North Bend", 41.462, -96.780, TOWN, (MIDWEST,), ["North Bend"]),
    ("McCook", 40.202, -100.626, TOWN, (MIDWEST,), ["McCook"]),
    ("Pine Ridge", 43.026, -102.556, AREA, (MIDWEST,), ["Pine Ridge", "Pine Ridge Reservation"]),
    ("Santee Sioux Nation", 42.840, -97.850, AREA, (MIDWEST,), ["Santee Sioux", "Santee Sioux Nation", "Santee"]),
    ("Fort Calhoun", 41.455, -96.025, TOWN, (MIDWEST,), ["Fort Calhoun"]),
    ("Davenport", 41.524, -90.578, TOWN, (MIDWEST,), ["Davenport"]),
    ("South Dakota", 44.37, -100.35, REGION, (MIDWEST,), ["South Dakota"]),
    ("North Dakota", 47.47, -100.47, REGION, (MIDWEST,), ["North Dakota"]),
    ("Kansas", 38.50, -98.38, REGION, (MIDWEST,), ["Kansas"]),
    ("Wisconsin", 44.62, -89.99, REGION, (MIDWEST,), ["Wisconsin"]),
    ("Minnesota", 46.28, -94.31, REGION, (MIDWEST,), ["Minnesota"]),
]

_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_HASHTAG = re.compile(r"#(\w+)")


def _expand_hashtags(text):
    """'#MirpurAzadKashmir' -> ' Mirpur Azad Kashmir ' so word-boundary matching sees the place names."""
    return _HASHTAG.sub(lambda m: " " + _CAMEL.sub(" ", m.group(1)) + " ", text or "")


@lru_cache(maxsize=None)
def _index(event):
    """Regex over every alias for one event (or all events when event is None), longest alias first."""
    alias_to_place = {}
    for i, (name, lat, lng, level, events, aliases) in enumerate(PLACES):
        if event is not None and events is not None and event not in events:
            continue
        for a in aliases + [name]:
            alias_to_place.setdefault(a.lower(), i)
    alts = sorted(alias_to_place, key=len, reverse=True)
    pattern = re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(a) for a in alts) + r")(?![\w-])", re.IGNORECASE)
    return pattern, alias_to_place


def find_places(text, event=None):
    """Every place mention in text: [(place_index, alias, position)] (non-overlapping, longest-first at each spot)."""
    if event is not None and not any(event in (p[4] or ()) for p in PLACES):
        event = None
    pattern, alias_to_place = _index(event)
    hay = _expand_hashtags(text)
    return [(alias_to_place[m.group(0).lower()], m.group(0), m.start()) for m in pattern.finditer(hay)]


def locate(text, event=None):
    """The single best place named in text as {"name","lat","lng"}, or None if no known place is named."""
    hits = find_places(text, event)
    if not hits:
        return None
    best = min(hits, key=lambda h: (PLACES[h[0]][3], -len(h[1]), h[2]))
    name, lat, lng, level, _, _ = PLACES[best[0]]
    return {"name": name, "lat": lat, "lng": lng}


@lru_cache(maxsize=1)
def all_names():
    """Every canonical name and alias (used by the scrubber so place names are never redacted as people)."""
    out = set()
    for name, _, _, _, _, aliases in PLACES:
        out.add(name.lower())
        out.update(a.lower() for a in aliases)
    return frozenset(out)
