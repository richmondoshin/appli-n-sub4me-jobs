"""The Hidden Jobs Product & UX feed as a job source (03 section 3.4, G13).

A free public RSS feed of design jobs read from company career pages across Europe. Links go to the employer's own
job page or, for many jobs, to a job board (JOB_BOARD_HOSTS), and users are told so (decided 24 Nov 2026). Rules: read the public feed only, at most once a day; keep UK jobs only; score them like any other job;
show CREDIT wherever its jobs appear. Its repository has no licence, so nothing from it is copied into this skill.

Where it's read from (M0.2, 23 Nov 2026): the repository file on raw.githubusercontent.com works on Free and Pro;
github.io works only where the person has allowed that website, so it is the second choice.
"""
import datetime
import email.utils
import pathlib
import re
import urllib.request
import xml.etree.ElementTree as ET

from scoring import NOT_UK, UK

FEED_URLS = (
    "https://raw.githubusercontent.com/sarabrunettini/hiddenjobs/main/feeds/product-ux.xml",
    "https://sarabrunettini.github.io/hiddenjobs/feeds/product-ux.xml",
)
SOURCE = "Hidden Jobs"
CREDIT = ("Some jobs come from the free Hidden Jobs feed: https://sarabrunettini.github.io/hiddenjobs/ . Some of its "
          "links open the job on a job board (uxjobs.io) instead of the employer's own website.")
# Hidden Jobs links that open a job board, not the employer's page (seen 24 Nov 2026: 18 of 28 UK links). Users are told.
JOB_BOARD_HOSTS = ("jobs.uxjobs.io",)
BOARD_NOTE = ("This link opens the job on uxjobs.io, a job board, not the employer's own website. Check the employer's "
              "careers page before you apply.")
MAX_BYTES = 5 * 1024 * 1024

# Towns that mark a UK job when the feed doesn't say "UK" (for example "London Office").
UK_TOWN_NAMES = ("london", "manchester", "birmingham", "leeds", "bristol", "edinburgh", "glasgow", "cardiff", "belfast",
                 "liverpool", "newcastle", "nottingham", "derby", "leicester", "sheffield", "cambridge", "oxford",
                 "brighton", "reading", "milton keynes", "southampton", "york", "bath", "cheltenham", "coventry",
                 "guildford", "aberdeen", "dundee", "swansea", "norwich", "exeter", "plymouth", "portsmouth", "stoke",
                 "wolverhampton", "bournemouth", "harrogate", "hatfield", "enstone")
UK_TOWNS = re.compile(r"\b(" + "|".join("(?<!new )york" if t == "york" else re.escape(t) for t in UK_TOWN_NAMES)
                      + r")\b", re.I)
# Same names abroad: "London, Ontario", "Manchester, NH", "Newcastle, Australia". Any ", XX" two-letter capital code
# (a US state or Canadian province) counts as abroad; that part is case-sensitive, so "London, On-site" stays UK.
ABROAD = re.compile(r"(?i:\b(ontario|canada|usa|united states|australia|new south wales|nsw|new zealand|"
                    r"south africa)\b)|,\s?(?!UK\b|GB\b)[A-Z]{2}\b")


class FeedUnavailable(Exception):
    """Neither address could be read. The message is plain words for the person."""


def _default_opener(url):
    req = urllib.request.Request(url, headers={"User-Agent": "appli-n-sub4me-job-agent/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(MAX_BYTES + 1)


def fetch(cache_dir=None, today=None, opener=_default_opener):
    """Returns the feed's text, reading it from the internet at most once a day.
    With cache_dir, today's copy is kept there and reused by later runs on the same day."""
    today = today or datetime.date.today()
    cache = pathlib.Path(cache_dir) / f"hidden-jobs-{today.isoformat()}.xml" if cache_dir else None
    if cache and cache.exists():
        return cache.read_text(encoding="utf-8")
    problems = []
    for url in FEED_URLS:
        try:
            data = opener(url)
        except Exception as e:  # network blocked, timeout, HTTP error
            problems.append(f"{url.split('/')[2]}: {e}")
            continue
        if len(data) > MAX_BYTES:
            problems.append(f"{url.split('/')[2]}: bigger than 5 MB")
            continue
        text = data.decode("utf-8", errors="replace")
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            for old in cache.parent.glob("hidden-jobs-*.xml"):
                old.unlink()
            cache.write_text(text, encoding="utf-8")
        return text
    raise FeedUnavailable("The Hidden Jobs feed couldn't be read today, so this run uses your other job sources. "
                          "(" + "; ".join(problems) + ")")


def _iso(pub_date):
    try:
        return email.utils.parsedate_to_datetime(pub_date).date().isoformat()
    except (TypeError, ValueError):
        return ""


def parse(xml_text):
    """Feed text -> jobs {company, title, location, url, date, desc, source}. The feed is untrusted text: only the
    fields below are read, links must be https, and nothing in it is followed or run."""
    if re.search(r"<!DOCTYPE|<!ENTITY", xml_text[:2000], re.I):
        raise ValueError("The Hidden Jobs feed has an unexpected format, so it was skipped.")
    root = ET.fromstring(xml_text)
    jobs = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        parts = [p.strip() for p in (item.findtext("description") or "").split("·")]
        if not title or not url.startswith("https://") or len(parts) < 2:
            continue
        company = parts[0]
        role = title.rsplit(" — ", 1)[0].strip() if " — " in title else title
        location = parts[1]
        if any(p.lower() == "remote" for p in parts[2:]) and "remote" not in location.lower():
            location += " (Remote)"
        jobs.append(dict(company=company, title=role, location=location, url=url,
                         date=_iso(item.findtext("pubDate")), desc=" · ".join(parts), source=SOURCE))
    return jobs


def is_uk(location):
    loc = location or ""
    if UK.search(loc):
        return True
    if NOT_UK.search(loc) or ABROAD.search(loc):
        return False
    return bool(UK_TOWNS.search(loc))


def uk_jobs(jobs):
    """The feed covers Europe; only UK jobs are kept (03 section 3.4)."""
    return [j for j in jobs if is_uk(j.get("location"))]
