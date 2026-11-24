"""Load the default company list (data/companies.json) that ships with the skill.

companies.json holds:
  companies    [{name, sector, slugs}]  slugs are guesses; the search keeps only those whose job feed answers
  wrong_match  {name: reason}           slugs found to belong to a DIFFERENT company with the same name: never used
  duplicates   [name]                   entries that repeat a company already listed
"""
import json
import pathlib

DEFAULT = pathlib.Path(__file__).resolve().parent.parent / "data" / "companies.json"


def load(path=DEFAULT):
    """Returns (companies, wrong_match). Companies are dicts {name, sector, slugs}; duplicates are left out."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("companies"), list):
        raise ValueError(f"{path}: expected an object with a 'companies' list")
    wrong_match = data.get("wrong_match", {})
    duplicates = set(data.get("duplicates", []))
    if not isinstance(wrong_match, dict):
        raise ValueError(f"{path}: 'wrong_match' must be an object of name: reason")
    companies, seen = [], set()
    for i, c in enumerate(data["companies"]):
        name, sector, slugs = c.get("name"), c.get("sector"), c.get("slugs")
        if not (isinstance(name, str) and name.strip() and isinstance(sector, str)
                and isinstance(slugs, list) and all(isinstance(s, str) and s for s in slugs)):
            raise ValueError(f"{path}: company {i} needs a name, a sector and a list of slugs")
        if name in duplicates or name in seen:
            continue
        seen.add(name)
        companies.append(dict(name=name, sector=sector, slugs=slugs))
    return companies, wrong_match
