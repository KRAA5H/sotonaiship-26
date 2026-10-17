"""Priority with visible factors. Pure functions: no database, no network.

The score is computed on read from four factors, and every factor is returned
alongside it so an officer can see why a report sits where it does:

  severity   high 3, medium 2, low 1 (not set counts as medium, and says so)
  exposure   how many people the place affects, from the category's group
  cluster    open reports of the same category at the same place, matched with
             the duplicate rule's own location normalisation
  age        days since reported, capped so age alone cannot dominate

score = severity x exposure x cluster factor x age factor, scaled to 0-100.
A resolved report scores 0. Nothing is stored, so there is no migration.
"""

from datetime import datetime, timezone

import tools

# Exposure by category group: roughly how many people one problem affects.
# A defect in the public highway is met by everyone who passes; a problem at
# one neighbouring property mostly affects that household. These are our own
# judgements for ordering work, not council policy, and are kept in one place
# so they are easy to see and change.
EXPOSURE = {
    "roads_and_parking": (1.5, "on the road, met by everyone passing"),
    "street_cleansing": (1.3, "in a public space"),
    "bins": (1.0, "at one address on the street"),
    "housing": (1.0, "inside one home"),
    "neighbourhood_nuisance": (0.8, "at one neighbouring property"),
}
EXPOSURE_DEFAULT = (1.0, "exposure unknown for this category")

SEVERITY = {"high": 3, "medium": 2, "low": 1}
CLUSTER_STEP = 0.5     # each extra open report at the same place adds half again
CLUSTER_CAP = 5        # beyond five reports the factor stops growing
AGE_CAP_DAYS = 14      # older than two weeks counts as two weeks
AGE_MAX_FACTOR = 1.5   # so age can at most add half again to the score
MAX_RAW = (max(SEVERITY.values()) * max(e for e, _ in EXPOSURE.values())
           * (1 + CLUSTER_STEP * (CLUSTER_CAP - 1)) * AGE_MAX_FACTOR)
OPEN = ("new", "in_review")


def severity_factor(severity):
    if severity in SEVERITY:
        return SEVERITY[severity], severity.capitalize()
    return SEVERITY["medium"], "Not set (counted as medium)"


def exposure_factor(category_id, groups):
    return EXPOSURE.get(groups.get(category_id), EXPOSURE_DEFAULT)


def cluster_count(report, reports):
    """Open reports of the same category at the same place, including this one."""
    place = tools._normalise_location(report.get("location") or "")
    if not place or place == "not given":
        return 1
    return sum(
        1 for other in reports
        if other.get("status") in OPEN
        and other.get("category_id") == report.get("category_id")
        and tools._same_place(tools._normalise_location(other.get("location") or ""), place)
    ) or 1


def age_days(report, now):
    created = datetime.fromisoformat(report["created_at"])
    if created.tzinfo is None:  # stored without an offset: treat as UTC
        created = created.replace(tzinfo=timezone.utc)
    return max(0, (now - created).days)


def age_factor(days):
    return 1 + (AGE_MAX_FACTOR - 1) * min(days, AGE_CAP_DAYS) / AGE_CAP_DAYS


def priority(report, reports, groups, now=None):
    """Score and the four factors for one report.

    reports: every report the officer can see (for the cluster count).
    groups:  {category_id: group} from categories.json.
    """
    now = now or datetime.now(timezone.utc)
    sev, sev_label = severity_factor(report.get("severity"))
    exp, exp_label = exposure_factor(report.get("category_id"), groups)
    count = cluster_count(report, reports)
    cluster = 1 + CLUSTER_STEP * (min(count, CLUSTER_CAP) - 1)
    days = age_days(report, now)
    age = age_factor(days)

    resolved = report.get("status") not in OPEN
    score = 0 if resolved else round(100 * sev * exp * cluster * age / MAX_RAW)
    factors = {
        "severity": {"value": sev, "label": sev_label},
        "exposure": {"value": exp, "label": exp_label},
        "cluster": {"value": count, "factor": cluster},
        "age_days": {"value": days, "factor": round(age, 2), "capped": days > AGE_CAP_DAYS},
    }
    return {"score": score, "factors": factors, "explanation": explain(factors, resolved)}


def explain(factors, resolved=False):
    """One plain-English line an officer can read aloud."""
    if resolved:
        return "Resolved, so it no longer needs a place in the queue."
    count = factors["cluster"]["value"]
    days = factors["age_days"]["value"]
    others = "the only open report here" if count == 1 else f"{count} open reports at this place"
    age = "reported today" if days == 0 else "1 day old" if days == 1 else f"{days} days old"
    if factors["age_days"]["capped"]:
        age += f" (counted as {AGE_CAP_DAYS})"
    return f"{factors['severity']['label']} severity, {factors['exposure']['label']}, {others}, {age}."


def score_all(reports, groups, now=None):
    """{report id: priority} for a list of reports, computed on read."""
    now = now or datetime.now(timezone.utc)
    return {r["id"]: priority(r, reports, groups, now) for r in reports}
