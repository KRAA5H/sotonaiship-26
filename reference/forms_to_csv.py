"""Turn the read-only form reads (reference/.page_cache/forms/*.json, from read_forms.py)
into reference/council_form_fields.csv. No network.

One row per field on the step that was read, plus one row per notice that warns or
redirects (emergency, police, "this form is for"). Map-layer toggles are dropped.
A form that did not render gets one "unverified" row with the value columns blank.

Run: python reference/forms_to_csv.py
"""

import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLUMNS = ["form_url", "step", "field_label", "field_type", "required", "dropdown_options", "warning_text",
           "status", "source_url", "date_read"]
WARNING = re.compile(r"emergenc|999|police|immediate hazard|this form is for|do not|don't|before you report", re.I)
MAP_NOISE = re.compile(r"street name in Southampton and then use the Search|^Street search$|Select here for instructions", re.I)


def short(text, limit=200):
    """First sentence only, capped: a short factual phrase, not the council's whole passage."""
    first = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    return first if len(first) <= limit else first[:limit - 3].rstrip() + "..."


def rows_for(record):
    url, date = record["url"], record["read_at"]
    if not record.get("fields"):
        return [{"form_url": url, "step": "", "field_label": "", "field_type": "", "required": "",
                 "dropdown_options": "", "warning_text": "", "status": "unverified: form did not render in a browser",
                 "source_url": url, "date_read": date}]
    step = len(record.get("earlier_steps", [])) + 1
    section = record.get("section") or ""
    out = []
    for earlier in record.get("earlier_steps", []):
        for notice in earlier.get("notices", []):
            if WARNING.search(notice):
                out.append({"form_url": url, "step": "before fields", "field_label": "", "field_type": "notice",
                            "required": "", "dropdown_options": "", "warning_text": short(notice),
                            "status": "verified", "source_url": url, "date_read": date})
    for field in record["fields"]:
        if field["type"] == "checkbox" and MAP_NOISE.search(field["label"]):
            continue
        label = field["label"]
        options = [o for o in field.get("options", []) if o and o != "Please select..." and o != label]
        out.append({"form_url": url, "step": f"{step} ({section})" if section else str(step),
                    "field_label": label.rstrip("*").strip(), "field_type": field["type"],
                    # From the form's own marker: a trailing * or a required attribute.
                    "required": "yes" if field["required"] else "no",
                    "dropdown_options": "; ".join(options), "warning_text": "",
                    "status": "verified", "source_url": url, "date_read": date})
    for notice in record.get("notices", []):
        if WARNING.search(notice) and "Crown copyright" not in notice:
            out.append({"form_url": url, "step": str(step), "field_label": "", "field_type": "notice",
                        "required": "", "dropdown_options": "", "warning_text": short(notice),
                        "status": "verified", "source_url": url, "date_read": date})
    out.append({"form_url": url, "step": f"after {step}", "field_label": "", "field_type": "", "required": "",
                "dropdown_options": "", "warning_text": "",
                "status": "unverified: later steps not read (they need answers we did not give)",
                "source_url": url, "date_read": date})
    return out


def main():
    rows = []
    for path in sorted((HERE / ".page_cache" / "forms").glob("*.json")):
        rows += rows_for(json.loads(path.read_text(encoding="utf-8")))
    with open(HERE / "council_form_fields.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)
    print(len(rows), "rows")


if __name__ == "__main__":
    main()
