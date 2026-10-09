"""Where is a role? Classifies location strings into south India, the rest of India, or abroad.

The default policy (configurable in settings.toml) is:
  * south India: any work mode
  * rest of India: remote only
  * abroad: remote only, and only when people based in India may apply
"""

from __future__ import annotations

import re

SOUTH_STATES = {"karnataka", "telangana", "andhra pradesh", "tamil nadu", "kerala", "puducherry", "pondicherry"}

SOUTH_CITIES = {
    # Karnataka
    "bengaluru", "bangalore", "mysuru", "mysore", "mangaluru", "mangalore", "hubli", "hubballi", "dharwad",
    "belagavi", "belgaum", "udupi", "manipal", "electronic city", "whitefield", "koramangala", "hsr layout",
    # Telangana
    "hyderabad", "secunderabad", "warangal", "shamshabad", "gachibowli", "hitec city", "hitech city", "madhapur",
    # Tamil Nadu
    "chennai", "madras", "coimbatore", "madurai", "tiruchirappalli", "trichy", "salem", "tiruppur", "vellore",
    "erode", "hosur",
    # Kerala
    "kochi", "cochin", "ernakulam", "thiruvananthapuram", "trivandrum", "kozhikode", "calicut", "thrissur",
    "kannur", "palakkad", "technopark", "infopark",
    # Andhra Pradesh
    "visakhapatnam", "vizag", "vijayawada", "guntur", "tirupati", "nellore", "kakinada", "rajahmundry",
    "anantapur", "kurnool", "amaravati",
    # Puducherry
    "puducherry", "pondicherry",
}

OTHER_INDIA = {
    "delhi", "new delhi", "ncr", "delhi ncr", "gurgaon", "gurugram", "noida", "greater noida", "ghaziabad",
    "faridabad", "mumbai", "navi mumbai", "thane", "pune", "kolkata", "ahmedabad", "gandhinagar", "jaipur",
    "chandigarh", "mohali", "panchkula", "indore", "bhopal", "lucknow", "kanpur", "nagpur", "surat", "vadodara",
    "bhubaneswar", "patna", "dehradun", "goa", "panaji", "guwahati", "ranchi", "raipur", "amritsar", "ludhiana",
    "jalandhar", "varanasi", "nashik", "aurangabad", "maharashtra", "gujarat", "punjab", "haryana",
    "uttar pradesh", "rajasthan", "west bengal", "madhya pradesh", "bihar", "odisha", "assam",
}

ABROAD_HINTS = re.compile(
    r"\b(united states|usa|u\.s\.|canada|united kingdom|uk|london|berlin|germany|france|paris|spain|netherlands|"
    r"amsterdam|ireland|dublin|poland|singapore|dubai|uae|australia|sydney|japan|tokyo|new york|nyc|san francisco|"
    r"sf|bay area|seattle|austin|boston|toronto|vancouver|remote[- ]us|emea|europe)\b",
    re.I,
)


def _has(words: set[str], text: str) -> str:
    for w in sorted(words, key=len, reverse=True):
        if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", text):
            return w
    return ""


def classify(location: str) -> dict:
    """Which buckets does a location string touch?

    Multi-city postings ("Bengaluru, Delhi or Mumbai") touch several; the role
    passes the south-India rule if any listed city is in the south.
    """
    loc = (location or "").lower()
    south = _has(SOUTH_CITIES | SOUTH_STATES, loc)
    other = _has(OTHER_INDIA, loc)
    india = bool(south or other or re.search(r"\bindia\b", loc))
    abroad = bool(ABROAD_HINTS.search(location or "")) and not india
    return {"south": south, "other_india": other, "india": india, "abroad": abroad}
