"""Read public job feeds from company job systems (no login needed).

Supported: Greenhouse, Lever, Ashby, SmartRecruiters. Each fetcher returns a dict:
    {ats, board_name, careers, jobs: [{title, location, url, date, desc}]}
or None if the company has no board on that system.
"""
import html
import re
import time

import requests

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "appli-n-sub4me-research/0.2"


def _get(url, tries=2):
    for i in range(tries):
        try:
            r = SESSION.get(url, timeout=25)
            if r.status_code == 429:  # rate limited: wait and retry
                time.sleep(3 * (i + 1))
                continue
            return r
        except requests.RequestException:
            time.sleep(1)
    return None


def _strip(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(text or ""))).strip()


def greenhouse(slug):
    r = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    if not r or r.status_code != 200:
        return None
    board = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}")
    name = board.json().get("name") if board and board.status_code == 200 else None
    jobs = [dict(title=j["title"], location=(j.get("location") or {}).get("name", ""),
                 url=j.get("absolute_url"), date=(j.get("updated_at") or "")[:10],
                 desc=_strip(j.get("content")), gh_id=j.get("id"))
            for j in r.json().get("jobs", [])]
    return dict(ats="Greenhouse", board_name=name, careers=f"https://boards.greenhouse.io/{slug}", jobs=jobs)


def greenhouse_questions(slug, job_id):
    """Exact application-form questions for one Greenhouse job (public)."""
    r = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}?questions=true")
    if not r or r.status_code != 200:
        return []
    return [dict(label=q["label"], required=bool(q.get("required")), types=[f["type"] for f in q["fields"]])
            for q in r.json().get("questions", [])]


def lever(slug):
    r = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if not r or r.status_code != 200 or "json" not in r.headers.get("content-type", ""):
        return None
    data = r.json()
    if not isinstance(data, list):
        return None
    jobs = []
    for j in data:
        c = j.get("categories") or {}
        locs = [c.get("location", "")] + (c.get("allLocations") or [])
        loc = " / ".join(dict.fromkeys(l for l in locs if l))
        if j.get("workplaceType"):
            loc += f" ({j['workplaceType']})"
        ts = j.get("createdAt")
        jobs.append(dict(title=j.get("text", ""), location=loc, url=j.get("hostedUrl"),
                         date=time.strftime("%Y-%m-%d", time.gmtime(ts / 1000)) if ts else "",
                         desc=_strip((j.get("descriptionPlain") or "") + " " +
                                     " ".join(x.get("content", "") for x in j.get("lists", [])))))
    return dict(ats="Lever", board_name=None, careers=f"https://jobs.lever.co/{slug}", jobs=jobs)


def ashby(slug):
    r = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")
    if not r or r.status_code != 200:
        return None
    jobs = []
    for j in r.json().get("jobs", []):
        locs = [j.get("location", "")] + [s.get("location", "") for s in (j.get("secondaryLocations") or [])]
        loc = " / ".join(dict.fromkeys(l for l in locs if l))
        if j.get("isRemote"):
            loc += " (Remote)"
        comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
        jobs.append(dict(title=j.get("title", ""), location=loc, url=j.get("jobUrl"),
                         date=(j.get("publishedAt") or "")[:10], desc=_strip((j.get("descriptionPlain") or "") + " " + comp)))
    return dict(ats="Ashby", board_name=None, careers=f"https://jobs.ashbyhq.com/{slug}", jobs=jobs)


def smartrecruiters(slug):
    r = _get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100")
    if not r or r.status_code != 200:
        return None
    d = r.json()
    if not d.get("totalFound"):
        return None
    jobs = []
    for j in d.get("content", []):
        l = j.get("location") or {}
        loc = ", ".join(x for x in [l.get("city"), (l.get("country") or "").upper()] if x)
        if l.get("remote"):
            loc += " (Remote)"
        jobs.append(dict(title=j.get("name", ""), location=loc, url=f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}",
                         date=(j.get("releasedDate") or "")[:10], desc="", detail_url=j.get("ref")))
    name = (d["content"][0].get("company") or {}).get("name") if d.get("content") else None
    return dict(ats="SmartRecruiters", board_name=name, careers=f"https://jobs.smartrecruiters.com/{slug}", jobs=jobs)


def smartrecruiters_description(detail_url):
    r = _get(detail_url)
    if not r or r.status_code != 200:
        return ""
    sections = (r.json().get("jobAd") or {}).get("sections") or {}
    return _strip(" ".join((v or {}).get("text", "") for v in sections.values()))


FETCHERS = [greenhouse, lever, ashby, smartrecruiters]


def find_board(name, slugs, wrong_match=()):
    """Try each slug on each job system. Returns the first board found, or an empty record.
    Companies in wrong_match are skipped: their slug belongs to a different company."""
    if name in wrong_match:
        return dict(company=name, slug=None, ats=None, jobs=[], wrong=True)
    for slug in slugs:
        for fetch in FETCHERS:
            board = fetch(slug)
            if board is not None:
                board.update(company=name, slug=slug, wrong=False)
                return board
    return dict(company=name, slug=None, ats=None, jobs=[], wrong=False)
