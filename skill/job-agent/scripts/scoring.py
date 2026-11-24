"""Filters and the match score (rubric in the plan, Section 8).

score = title (25) + seniority (15) + location (15) + skills (30) + sector (10) + salary (5) = 100
Everything here is plain code: no AI, no cost.
"""
import datetime
import re

# ---- Role titles -------------------------------------------------------------
PRIMARY = re.compile(r"\b(product designer|ux designer|ui/ux|ux/ui|ui ?& ?ux|ux ?& ?ui|user experience designer|product design(er)?)\b", re.I)
OPTIONAL = re.compile(r"\b(design systems?|ux research(er)?|user research(er)?|web designer|digital designer|interaction designer|visual designer|content designer|service designer|e-?commerce designer|designer)\b", re.I)
EXCLUDE_TITLE = re.compile(r"\b(graphic|motion|industrial|hardware|interior|mechanical|fashion|instructional|game|level|sound|video|3d|architect|engineer(?!ing manager)|developer|intern|internship|apprentice|director|head of|vp|vice president|chief|recruit)\b", re.I)
NOT_UX = re.compile(r"\b(brand|creative|production|learning|marketing|jersey|arrange|topshop|assistant designer)\b|- (ww|mw)\b", re.I)

# ---- Locations ---------------------------------------------------------------
UK = re.compile(r"\b(united kingdom|uk|england|scotland|wales|gb|great britain)\b", re.I)
REMOTE = re.compile(r"remote|anywhere|distributed", re.I)
EUROPE = re.compile(r"\b(emea|europe)\b", re.I)
NOT_UK = re.compile(r"(?i:\b(usa|united states|massachusetts|alabama)\b)|,\s?(MA|NY|CA|TX|IL|WA|GA|AL|NC|PA|VA|NJ|CO|FL|OR)\b")
EU_COUNTRY = re.compile(r"\b(paris|portugal|germany|spain|ireland|sweden|france|netherlands)\b", re.I)


def city_regex(cities):
    parts = [("(?<!new )york" if c.lower() == "york" else re.escape(c.lower())) for c in cities]
    if not parts:  # no towns given (for example "UK remote" only): match nothing
        return re.compile(r"(?!)")
    return re.compile(r"\b(" + "|".join(parts) + r")\b", re.I)


def location_points(loc, home, wider):
    """15 = a home city, 13 = a wider UK city (relocation), 15 = UK remote, 12 = UK unspecified,
    8 = Europe/EMEA remote (check UK eligibility), 0 = not eligible."""
    abroad = bool(NOT_UK.search(loc)) and not UK.search(loc)
    if home.search(loc) and not (abroad and not re.search(r"london|nottingham|derby|leicester", loc, re.I)):
        return 15, "Target city"
    if wider.search(loc) and not abroad:
        return 13, "UK city (relocation)"
    if abroad:
        return 0, None
    if UK.search(loc) and REMOTE.search(loc):
        return 15, "UK remote"
    if UK.search(loc):
        return 12, "UK (city not stated)"
    if EUROPE.search(loc) and REMOTE.search(loc) and not EU_COUNTRY.search(loc):
        return 8, "Europe/EMEA remote (check UK eligibility)"
    return 0, None


# ---- Salary ------------------------------------------------------------------
def salary_range(text):
    vals = [int(v.replace(",", "")) for v in re.findall(r"£\s?(\d{2,3},\d{3}|\d{5,6})", text or "")]
    vals += [int(k) * 1000 for k in re.findall(r"£\s?(\d{2,3})\s?[kK]\b", text or "")]
    vals = [v for v in vals if 15000 <= v <= 300000]
    return (min(vals), max(vals)) if vals else None


# ---- Skills ------------------------------------------------------------------
SKILL_LABELS = {
    "figma": "Figma", "user research": "user research", "usability": "usability testing", "prototyp": "prototyping",
    "design system": "design systems", "accessib": "accessibility", "wcag": "WCAG", "journey map": "journey mapping",
    "information architecture": "information architecture", "a/b": "A/B testing", "interaction design": "interaction design",
    "agile": "Agile", "protopie": "ProtoPie", "webflow": "Webflow", "shopify": "Shopify", "analytics": "analytics",
    "hotjar": "Hotjar", "maze": "Maze", "wirefram": "wireframing", "b2b": "B2B", "saas": "SaaS", "fintech": "fintech",
    "payment": "payments", "e-commerce": "e-commerce", "ecommerce": "e-commerce", "mobile": "mobile",
    "end-to-end": "end-to-end", "discovery": "discovery", "stakeholder": "stakeholders",
    "cross-functional": "cross-functional", "experiment": "experimentation",
}


# ---- Seniority ---------------------------------------------------------------
# Job levels in order, and the years of design experience each usually asks for (decided 24 Nov 2026: judge the
# level against the CV's years unless the person changes the years in my-profile.md).
LEVELS = ("Junior", "Mid", "Senior", "Lead/Staff", "Management")
LEVEL_FROM_YEARS = ((2, 0), (5, 1), (8, 2))  # under 2 years: Junior; under 5: Mid; under 8: Senior; else Lead/Staff


def title_level(title):
    low = title.lower()
    if re.search(r"manager|head", low):
        return 4
    if re.search(r"\b(staff|principal|lead)\b", low):
        return 3
    if re.search(r"\b(senior|sr)\b", low):
        return 2
    if re.search(r"\b(junior|jr|associate|graduate|entry)\b", low):
        return 0
    return 1


def years_level(years):
    for limit, level in LEVEL_FROM_YEARS:
        if years < limit:
            return level
    return 3


def seniority_points(title, years):
    """15 = the level fits the person's years, 8 = one level above (stretch) or below, 3 = further away.
    Without years (not in the CV or my-profile.md) the old rule applies: Mid/Senior fit, others are a stretch."""
    lvl = title_level(title)
    if years is None:
        return {0: (5, "Junior (below experience)"), 3: (8, "Lead/Staff (stretch)"),
                4: (5, "Management track (stretch)")}.get(lvl, (15, "Mid/Senior"))
    gap = lvl - years_level(years)
    yrs = f"{years:g} years"
    if gap == 0 or (lvl == 4 and gap == 1 and years >= 8):
        return 15, f"{LEVELS[lvl]} (fits your {yrs})"
    pts = 8 if abs(gap) == 1 else 3
    return pts, f"{LEVELS[lvl]} ({'stretch' if gap > 0 else 'below'} for your {yrs})"


def score_job(job, sector, profile):
    """Return a score dict, or None if a hard filter rules the job out."""
    t = job["title"]
    if NOT_UX.search(t) or EXCLUDE_TITLE.search(t) or not (PRIMARY.search(t) or OPTIONAL.search(t)):
        return None
    home = city_regex(profile["home_cities"])
    wider = city_regex(profile.get("wider_cities", []))
    loc_pts, loc_note = location_points(job["location"], home, wider)
    if not loc_pts:
        return None
    cutoff = (datetime.date.today() - datetime.timedelta(days=183)).isoformat()
    if job.get("date") and job["date"] < cutoff:  # older than ~6 months: likely stale
        return None

    title_pts = 25 if PRIMARY.search(t) else 15
    sen_pts, sen = seniority_points(t, profile.get("years"))

    desc = (job.get("desc") or "").lower()
    hits = list(dict.fromkeys(SKILL_LABELS[k] for k in SKILL_LABELS if k in desc))
    skill_pts = round(30 * min(1, len(hits) / 8)) if desc.strip() else 15
    sec_pts = 10 if re.search(r"fintech|saas|e-commerce|insurtech", sector, re.I) else 8 if re.search(r"edtech|\bai\b", sector, re.I) else 5

    sal = salary_range(job.get("desc"))
    floor = profile["salary"]["london_floor"] if re.search("london", job["location"], re.I) else profile["salary"]["other_floor"]
    if sal and sal[1] < floor:
        return None
    total = title_pts + sen_pts + loc_pts + skill_pts + sec_pts + (5 if sal else 3)
    return dict(score=total, seniority=sen, location_note=loc_note, skills_hit=", ".join(hits[:8]),
                salary=f"£{sal[0]:,}–£{sal[1]:,}" if sal else "Not stated")
