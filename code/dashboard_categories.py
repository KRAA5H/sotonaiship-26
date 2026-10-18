"""Extra categories for the council dashboard only (D70).

Imported FixMyStreet reports include council work our rulebook has no category
for, such as traffic lights or street lighting. These ids give them a clear
label on /council and a priority group. They are NOT in agent/categories.json:
the agent never classifies into them and states no facts about them.
"""

EXTRA = {
    # id: (label shown on the dashboard, priority group from priority.EXPOSURE)
    "road_pavement_defect": ("Road or pavement defect", "roads_and_parking"),
    "traffic_lights_signs": ("Traffic lights, signs and markings", "roads_and_parking"),
    "street_lighting": ("Street lighting", "roads_and_parking"),
    "drains_covers": ("Drains, gullies and covers", "roads_and_parking"),
    "trees_vegetation": ("Trees, hedges and verges", "street_cleansing"),
    "street_furniture": ("Bollards, railings and street furniture", "street_cleansing"),
    "general_enquiry": ("General highways enquiry", "roads_and_parking"),
}


def labels():
    return {cid: label for cid, (label, _) in EXTRA.items()}


def groups():
    return {cid: group for cid, (_, group) in EXTRA.items()}
