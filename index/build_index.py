"""Builds the shared job index (M7.1, 03 section 3.6): design-uk.json, a daily list of current UK product and UX design
jobs from the default companies' public job feeds. Holds only public job postings: no CVs, no user data.

Runs daily in the public repo with GitHub Actions. Free users' Claude reads the result from raw.githubusercontent.com,
because Free sandboxes can't reach job sites (M0.2). The Hidden Jobs feed is not copied in (its repository has no
licence); the skill reads that feed's own GitHub file instead.

    python index/build_index.py                 # writes design-uk.json in the current folder
    python index/build_index.py --limit 20      # quick test: first 20 companies only
"""
import argparse
import datetime
import json
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "job-agent" / "scripts"))

import companies as company_list  # noqa: E402
import feeds  # noqa: E402
from hidden_jobs import is_uk  # noqa: E402
from scoring import EU_COUNTRY, EUROPE, EXCLUDE_TITLE, NOT_UK, NOT_UX, OPTIONAL, PRIMARY, REMOTE  # noqa: E402

VERSION = 1
MAX_DESC = 6000          # characters kept from each description (enough for skills and salary)
MAX_AGE_DAYS = 183       # same cut-off as scoring.py: older postings are likely stale
MIN_JOBS = 5             # fewer than this means the feeds failed: keep yesterday's file instead


def is_design_title(title):
    """The same title rules as scoring.py's hard filter, without any personal details."""
    t = title or ""
    return bool((PRIMARY.search(t) or OPTIONAL.search(t)) and not NOT_UX.search(t) and not EXCLUDE_TITLE.search(t))


def is_uk_eligible(location):
    """UK jobs (including UK towns with no country named), plus Europe/EMEA remote that may allow the UK."""
    loc = location or ""
    if is_uk(loc):
        return True
    return bool(EUROPE.search(loc) and REMOTE.search(loc) and not EU_COUNTRY.search(loc) and not NOT_UK.search(loc))


def keep(job, today):
    if not (is_design_title(job.get("title")) and is_uk_eligible(job.get("location"))):
        return False
    date = job.get("date") or ""
    return not date or date >= (today - datetime.timedelta(days=MAX_AGE_DAYS)).isoformat()


def build(boards, sectors, today, describe=feeds.smartrecruiters_description):
    """Boards from feeds.find_board -> the index dict. Pure apart from `describe` (SmartRecruiters descriptions)."""
    jobs, seen = [], set()
    for b in boards:
        for j in b["jobs"]:
            if not keep(j, today) or not str(j.get("url", "")).startswith("https://") or j["url"] in seen:
                continue
            seen.add(j["url"])
            desc = j.get("desc") or ""
            if not desc and b["ats"] == "SmartRecruiters" and j.get("detail_url"):
                desc = describe(j["detail_url"]) or ""
            jobs.append(dict(company=b["company"], sector=sectors.get(b["company"], ""), title=j["title"].strip(),
                             location=(j.get("location") or "").strip(), url=j["url"], date=j.get("date") or None,
                             ats=b["ats"], desc=desc[:MAX_DESC]))
    jobs.sort(key=lambda x: (x["company"].lower(), x["title"].lower()))
    return dict(version=VERSION, updated=today.isoformat(),
                about="Public UK product and UX design job postings from company job feeds. No personal data.",
                count=len(jobs), jobs=jobs)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="design-uk.json")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    companies, wrong = company_list.load()
    if args.limit:
        companies = companies[: args.limit]
    print(f"Checking {len(companies)} companies' job feeds...")
    with ThreadPoolExecutor(12) as ex:
        boards = list(ex.map(lambda c: feeds.find_board(c["name"], c["slugs"], wrong), companies))
    index = build(boards, {c["name"]: c["sector"] for c in companies}, datetime.date.today())
    print(f"{index['count']} UK design jobs from {sum(1 for b in boards if b['ats'])} job boards.")
    if index["count"] < MIN_JOBS and not args.limit:
        print("Too few jobs: the feeds probably failed. Keeping the previous file.")
        return 1
    pathlib.Path(args.out).write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
