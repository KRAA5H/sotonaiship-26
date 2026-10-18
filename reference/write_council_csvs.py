"""Write reference/council_pages.csv and reference/proposed_additions.csv from the pages read on 2026-10-18.
Every value below was read from the cached page named in its row. Blank + "unverified" where we could not read it."""
import csv
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
B = "https://www.southampton.gov.uk"
V = "https://southampton.portal.uk.empro.verintcloudservices.com/site/southampton/request/"
D = "2026-10-18"

PAGES = [
    # category_id, issue, title, path, form_url, handled_by, form_vs_phone, phones, status, notes
    ("pothole; abandoned_vehicle; illegal_parking", "Road issues (index)", "Report a road issue", "/travel-transport/report-issue/", "", "council", "Index page linking to potholes, parking and bus stop pages", "", "verified", "Index only"),
    ("pothole", "Potholes", "Pothole and road defects", "/travel-transport/report-issue/potholes/", V + "roads-report-a-pothole", "council",
     "Use the form; 'complete a new form for each individual pothole'; 'Do not endanger yourself or others'", "", "verified", "Thresholds and timings match our fact sheet"),
    ("new", "Other road and pavement problems: drains and gullies, railings, signs, traffic lights and crossings, faded markings, grit bins, paving", "Other road issues", "/travel-transport/report-issue/potholes/other/", V + "report-highway-issue", "council",
     "Use the form; 'If the problem is not listed use our general road or street problem form'", "", "verified", "Form also takes ?type= values per issue (see council_form_fields.csv)"),
    ("new", "Road safety concern (accident location)", "Other road issues", "/travel-transport/report-issue/potholes/other/", V + "report-a-road-safety-concern", "council",
     "Only considered if injury accident data shows incidents 'within the last three years'", "", "verified", "The form itself did not render in a browser: fields unverified"),
    ("new", "Bus stop or shelter damage", "Report a problem with a bus stop or shelter", "/travel-transport/report-issue/report-a-problem-with-a-bus-stop-or-shelter/", V + "report-damaged-bus-shelter", "council",
     "Use the form for 'vandalism or damage to a bus shelter'", "", "verified", "Our fact sheet says bus shelter graffiti goes to 'the company responsible'; this page takes shelter damage reports itself"),
    ("new", "Street light not working or damaged", "Street lighting in Southampton", "/travel-transport/roadworks/road-maintenance/street-lighting/", "http://www.lightsoninsouthampton.co.uk/Public/ReportFault.aspx", "other",
     "Report council lights 'online via the ENERVEO portal'; lights without the Enerveo label: 'contact the owner directly'", "0800 048 2436", "verified",
     "Maintained under a council PFI contract (Tay Valley Lighting, services by Enerveo). Some lights are privately owned. Lights switched off 1am to 5.30am since 1 Dec 2023. Fault portal not opened"),
    ("illegal_parking", "Parking offences", "Incorrectly parked cars or parking offences", "/travel-transport/report-issue/parking-offence/", V + "report-incorrectly-parked-vehicle", "council; police",
     "Dangerous or obstructive parking with no restriction: 'can only be dealt with by the police', call 101", "101", "verified", "Dropped kerb PCN £70.00"),
    ("illegal_parking", "Verge parking", "Verge parking", "/travel-transport/report-issue/parking-offence/verge-parking/", "", "council", "No report form on the page; describes measures and criteria", "", "verified", ""),
    ("new", "Faulty pay and display machine", "Faulty parking machines", "/travel-transport/report-issue/parking-offence/faulty-parking-machines/", V + "report-a-faulty-parking-machine", "council",
     "Use the form; refund claims in the same form", "", "verified", ""),
    ("abandoned_vehicle", "Abandoned vehicle", "Abandoned vehicles", "/travel-transport/report-issue/parking-offence/abandoned-vehicles/", V + "report-abandoned-vehicle", "council; other",
     "Untaxed: report to DVLA; no MOT: report to the police; abandoned: use the form", "", "verified", "Inspection 'usually ... within a week'; burnt out 'within 24 hours'. Matches our fact sheet"),
    ("abandoned_vehicle", "Hazardous vehicle", "Hazardous vehicles", "/travel-transport/report-issue/parking-offence/abandoned-vehicles/hazardous-vehicles/", V + "report-abandoned-vehicle", "council",
     "Use the abandoned vehicle form", "", "verified", "May be removed 'even if it is taxed or has a foreign registered number plate'"),
    ("fly_tipping; dog_fouling; dead_animal; litter_street_cleaning; graffiti_flyposting; glass_spillage_hazard", "Street cleaning problems", "Report a street cleaning problem", "/environment/street-cleaning/report-a-street-cleaning-problem/", V + "report-street-cleaning-issue", "council; landowner",
     "Use the form; private land clearing is a chargeable quote request by the landowner", "", "verified", "Page says 'over 75% of urgent requests within one working day'; our fact sheet says 'at least 75%'"),
    ("litter_street_cleaning", "Abandoned shopping trolley", "Abandoned shopping trolleys", "/environment/street-cleaning/report-a-street-cleaning-problem/abandoned-shopping-trolleys/", V + "report-street-cleaning-issue", "other; council",
     "Report to the retailer first (list of retailers on the page); the council form otherwise", "", "verified", ""),
    ("dead_animal", "Dead animal", "Dead animals", "/environment/street-cleaning/report-a-street-cleaning-problem/dead-animals/", V + "report-street-cleaning-issue", "council; landowner",
     "Busy carriageway: 'make it clear that it is causing a traffic hazard'", "", "verified", "Routine cases 'attended within one working day'. Private land: owner or occupier"),
    ("dog_fouling", "Animal fouling", "Animal fouling", "/environment/street-cleaning/report-a-street-cleaning-problem/dog-fouling/", V + "report-street-cleaning-issue", "council",
     "Use the form; give 'closest property address, landmark, or lamp column reference number'", "", "verified", "Page title is now 'Animal fouling'"),
    ("fly_tipping", "Fly-tipping", "Fly-tipping", "/environment/street-cleaning/report-a-street-cleaning-problem/fly-tipping/", V + "report-street-cleaning-issue", "council; landowner",
     "Private land: 'resolved by the landowner or occupier'; witnessed with evidence: use the form", "", "verified", "Matches our fact sheet"),
    ("graffiti_flyposting", "Graffiti", "Graffiti", "/environment/street-cleaning/report-a-street-cleaning-problem/graffiti/", V + "report-street-cleaning-issue", "council; landowner; utility",
     "Public land: the form; private land: quote form; BT/Openreach and Virgin Media cabinets: phone the company", "0800 023 2023; 0330 333 0444", "verified", "Cabinet numbers match our fact sheet"),
    ("litter_street_cleaning", "Fallen leaves", "Leaf clearing", "/environment/street-cleaning/report-a-street-cleaning-problem/leaves/", V + "overgrown-grass-hedges-or-fallen-leaves", "council; resident",
     "Use the form; residents clear leaves on their own property", "", "verified", "Cleared 'from October until mid-January'"),
    ("missed_bin", "Missed bin collection", "Report a missed bin collection", "/bins-recycling/bins/missed-collections/", V + "report-missed-bin-collection", "council",
     "'report your missed bin online within 48 hours of your scheduled collection day'", "", "verified", "Our fact sheet says 'within two working days': wording differs"),
    ("lost_damaged_bin", "Lost, damaged or stray bins (index)", "Lost, damaged or stray bins", "/bins-recycling/bins/lost-bin/", "", "council", "Index page", "", "verified", ""),
    ("lost_damaged_bin", "Damaged bin", "My bin is damaged", "/bins-recycling/bins/lost-bin/damaged-bin/", V + "bins-lost-damaged-stray", "council",
     "Use the form", "", "verified", "'replaced free of charge'; 'up to eight weeks'"),
    ("lost_damaged_bin", "Lost or stolen bin", "My bin is lost or stolen", "/bins-recycling/bins/lost-bin/my-bin-is-lost-or-stolen/", V + "bins-lost-damaged-stray", "council",
     "Use the form; 360 litre bins: phone customer services", "023 8083 3005", "verified", "Charges now £35 (140 litre) and £45 (240 litre); 'We no longer provide 360 litre general waste bins'. CONFLICT with our fact sheet (£33/£43/£54)"),
    ("lost_damaged_bin", "Stray or excess bin", "Stray and excess bins", "/bins-recycling/bins/lost-bin/stray-excess-bins/", V + "bins-lost-damaged-stray", "council", "Use the form", "", "verified", ""),
    ("new", "Bins left out on the pavement", "Bins left out on pavements", "/bins-recycling/bins/bins-on-pavements/", V + "report-bins-on-pavement", "council; resident",
     "'speak to your neighbour first', then the form", "", "verified", "Bins out before 6.30am, back by 11.59pm on collection day"),
    ("noise_nuisance; other_nuisance", "Neighbourhood nuisance", "Report a neighbourhood nuisance", "/environment/neighbourhood-nuisances-and-property-concerns/neighbourhood-nuisances/make-a-complaint/", V + "environmental-health-report-local-nuisance-or-concern", "council; landlord",
     "Talk to the neighbour or their landlord first; then the form", "", "verified", ""),
    ("noise_nuisance", "Noise", "Make a noise complaint", "/environment/neighbourhood-nuisances-and-property-concerns/neighbourhood-nuisances/noise/make-a-complaint/", V + "environmental-health-report-local-nuisance-or-concern", "council; police",
     "'If you believe that you or someone else may be in danger please call the police immediately on 999'", "999", "verified", "The form says car or motorcycle noise: 'contact the police first'"),
    ("property_concern", "Concern about a property (index)", "Report a concern about a property", "/environment/neighbourhood-nuisances-and-property-concerns/concern-about-property/", "", "council",
     "'In the first instance, speak to the property owner'", "", "verified", "Index page"),
    ("new", "Blocked drain", "Blocked drains", "/environment/neighbourhood-nuisances-and-property-concerns/concern-about-property/blocked-drain/", V + "environmental-health-report-local-nuisance-or-concern", "utility; landlord; council",
     "Outside the property boundary 'usually lies with Southern Water'; renters tell the landlord; road gullies: highway form", "033 0303 0368", "verified", "Southern Water number written 033 0303 0368 here and 0330 303 0368 on the flood page (same digits)"),
    ("property_concern", "Empty or derelict property", "Empty or derelict properties", "/environment/neighbourhood-nuisances-and-property-concerns/concern-about-property/empty-derelict/", V + "environmental-health-report-local-nuisance-or-concern", "council",
     "Use the form", "", "verified", "Empty means 'not been occupied for six months or more'"),
    ("property_concern", "Filthy or verminous property", "Filthy properties", "/environment/neighbourhood-nuisances-and-property-concerns/concern-about-property/filthy-property/", V + "environmental-health-report-local-nuisance-or-concern", "council",
     "Use the form; welfare concerns: safeguarding", "", "verified", ""),
    ("property_concern", "Overgrown or untidy garden", "Overgrown and untidy gardens", "/environment/neighbourhood-nuisances-and-property-concerns/concern-about-property/untidy-garden/", V + "environmental-health-report-local-nuisance-or-concern", "council; resident",
     "Speak to the neighbour first; council 'only likely to take action' if harmful to health or a nuisance", "", "verified", ""),
    ("new", "Pest control (index)", "Pest control", "/environment/pest-control/", "", "council", "Index page", "", "verified", ""),
    ("new", "Rats", "Report a rat problem", "/environment/pest-control/rats/", V + "environmental-health-report-local-nuisance-or-concern", "council",
     "One sighting outside: 'generally no need to contact us'; rats in a public space: the form", "", "verified", "Rats is an option in the nuisance form's dropdown"),
    ("new", "Trees (index)", "Reporting issues with trees or vegetation", "/environment/trees-grass-hedges/reporting-issues-with-trees-or-vegetation/", "", "council; landowner",
     "Private tree: 'contact the landowner first'; emergency (tree may fall imminently): 'call the council'", "", "verified", "Dangerous council-owned trees 'considered an emergency'"),
    ("new", "Dangerous tree", "Trees in a dangerous condition", "/environment/trees-grass-hedges/reporting-issues-with-trees-or-vegetation/dangerous/", V + "report-tree-in-dangerous-condition", "council",
     "Immediate hazard: this form; no immediate hazard: request works instead", "", "verified", ""),
    ("new", "Overhanging vegetation", "Overhanging vegetation", "/environment/trees-grass-hedges/reporting-issues-with-trees-or-vegetation/overhanging-vegetation/", V + "overgrown-grass-hedges-or-fallen-leaves", "landowner; council",
     "Owner or occupier usually responsible; report via the form", "", "verified", "Page also links the highway issue form"),
    ("new", "Nuisance tree works", "Nuisance trees", "/environment/trees-grass-hedges/reporting-issues-with-trees-or-vegetation/nuisance-trees/", V + "request-works-to-a-tree", "council; utility",
     "Overhead power line emergency: 'call SSE on 0800 0727 282'", "0800 0727 282", "verified", "No works for TV reception, light, seasonal debris, views, overhang, size"),
    ("new", "Trees team contact", "Contact information for trees", "/contact-us/trees-contact/", V + "general-enquiries?service=Tree%20service", "council",
     "Phone in office hours; 'Outside of these times, please call our emergency out of hours team'", "023 8083 3005 (option 5)", "verified", ""),
    ("council_housing_repair", "Council home repair", "Report a repair", "/housing/council-housing-tenants-and-leaseholders/repairs-maintenance-and-improvements/report-a-repair/", V + "report-a-housing-repair-council-tenants-leaseholders", "council",
     "'If you are reporting an emergency repair please phone us instead'", "", "verified", "Repair categories with timings on the page"),
    ("council_housing_repair", "Council home emergency repair", "Emergency repairs", "/housing/council-housing-tenants-and-leaseholders/repairs-maintenance-and-improvements/emergency-repairs/", "", "council; utility",
     "Phone only: office hours 023 8083 3006 (option two); outside hours 023 8023 3344; gas smell 0800 111 999", "023 8083 3006; 023 8023 3344; 0800 111 999", "verified", "Out-of-hours number matches our fact sheet"),
    ("council_housing_repair", "Damp and mould in a council home", "Damp and mould in council homes", "/housing/council-housing-tenants-and-leaseholders/repairs-maintenance-and-improvements/damp-and-mould/", V + "report-a-housing-repair-council-tenants-leaseholders", "council",
     "Report via the repair form", "", "verified", ""),
    ("flooding_severe_weather", "Flooding", "Report a flood", "/environment/emergencies-flooding-and-other-severe-weather/flood-risk-management/report-a-flood/", V + "report-flooding", "council; utility; emergency services",
     "'Call 999 if there is a danger to life'; Southern Water 24-hour line; council form or service centre; out of hours for non-life threatening emergencies",
     "999; 0330 303 0368; 023 8083 3000; 023 8083 3344; 023 8023 3344", "verified",
     "CONFLICT: the out-of-hours number appears as 023 8083 3344 three times and 023 8023 3344 once on this page. Our fact sheet and the emergency out of hours page say 023 8023 3344"),
    ("general", "Emergency out of hours", "Emergency out of hours", "/contact-us/emergency-out-of-hours/", "", "council",
     "'For emergencies outside normal office hours, please ring 023 8023 3344'", "023 8023 3344; 0300 555 1373", "verified", "Matches our fact sheet"),
]

COLS = ["category_id", "issue", "page_title", "page_url", "form_url", "handled_by", "form_vs_phone_or_emergency",
        "phone_numbers", "status", "notes", "date_read"]
with open(REPO / "reference" / "council_pages.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f, quoting=csv.QUOTE_ALL)
    w.writerow(COLS)
    for row in PAGES:
        cat, issue, title, path, form, who, when, phones, status, notes = row
        w.writerow([cat, issue, title, B + path, form, who, when, phones, status, notes, D])
print(len(PAGES), "pages")

# Facts fully confirmed from a page read today and NOT already in agent/confirmed_with_websites.csv.
# Same columns as that file. For the owner to review and merge by hand.
P = [
    ("new", "Street light faults", "Council street lights are maintained under a PFI contract with Tay Valley Lighting, with services by Enerveo. Faults on lights with the Enerveo label are reported online via the Enerveo portal or on 0800 048 2436. Lights without the label may be privately owned: contact the owner shown on the column.", "/travel-transport/roadworks/road-maintenance/street-lighting/", "Street lighting in Southampton", ""),
    ("new", "Street lights at night", "Since 1 December 2023 street lighting is switched off between 1am and 5.30am, in certain areas of the city.", "/travel-transport/roadworks/road-maintenance/street-lighting/", "Street lighting in Southampton", "Some 'exemption' areas keep lights on."),
    ("new", "Other road problems", "Drains and gullies, railings, road signs, traffic lights and crossings, faded markings, grit bins and paving are reported on the council's 'report a road or street problem' form.", "/travel-transport/report-issue/potholes/other/", "Other road issues", ""),
    ("new", "Road safety concerns", "The council only considers road safety improvements if injury accident data shows incidents involving personal injury within the last three years.", "/travel-transport/report-issue/potholes/other/", "Other road issues", ""),
    ("new", "Bus stops and shelters", "Vandalism or damage to a bus shelter can be reported to the council on its bus stop or shelter form.", "/travel-transport/report-issue/report-a-problem-with-a-bus-stop-or-shelter/", "Report a problem with a bus stop or shelter", ""),
    ("illegal_parking", "Dangerous parking without restrictions", "The council cannot fine vehicles parked dangerously or causing an obstruction where there is no parking restriction. These can only be dealt with by the police: call Hampshire Constabulary on 101.", "/travel-transport/report-issue/parking-offence/", "Incorrectly parked cars or parking offences", ""),
    ("new", "Faulty parking machines", "A faulty pay and display machine can be reported on the council's online form, which also takes refund claims. Refunds are investigated, not automatic.", "/travel-transport/report-issue/parking-offence/faulty-parking-machines/", "Faulty parking machines", ""),
    ("lost_damaged_bin", "Replacement charges", "Replacing a green-lidded general waste bin costs £35 for 140 litre and £45 for 240 litre. Charges are non-refundable. The council no longer provides 360 litre general waste bins: call 023 8083 3005. Other bins are replaced free.", "/bins-recycling/bins/lost-bin/my-bin-is-lost-or-stolen/", "My bin is lost or stolen", "Replaces the existing charges row (£33/£43/£54), which no longer matches the page."),
    ("lost_damaged_bin", "Damaged bins", "Any type of damaged bin is replaced free of charge. Replacement bins can take up to eight weeks to be delivered.", "/bins-recycling/bins/lost-bin/damaged-bin/", "My bin is damaged", ""),
    ("new", "Bins left on pavements", "Residents should put bins out before 6.30am on collection day and take them back by 11.59pm. The council asks residents to speak to the neighbour first, then use its form.", "/bins-recycling/bins/bins-on-pavements/", "Bins left out on pavements", ""),
    ("noise_nuisance", "Danger", "If you believe that you or someone else may be in danger, call the police on 999.", "/environment/neighbourhood-nuisances-and-property-concerns/neighbourhood-nuisances/noise/make-a-complaint/", "Make a noise complaint", ""),
    ("new", "Blocked drains", "Problems with drains or overflowing manholes outside a property's boundary usually lie with Southern Water (033 0303 0368), with exceptions. Tenants should tell their landlord.", "/environment/neighbourhood-nuisances-and-property-concerns/concern-about-property/blocked-drain/", "Blocked drains", ""),
    ("new", "Rats", "One sighting of a rat outside a property generally needs no report. Rats in a public space can be reported to the council on its nuisance form.", "/environment/pest-control/rats/", "Report a rat problem", ""),
    ("new", "Dangerous trees", "A council-owned tree that is dangerous is treated as an emergency. A tree that is an immediate hazard to life or property is reported on the 'tree in a dangerous condition' form. For a private tree, contact the landowner first.", "/environment/trees-grass-hedges/reporting-issues-with-trees-or-vegetation/", "Reporting issues with trees or vegetation", ""),
    ("new", "Nuisance trees", "The council does not carry out tree work for television reception, obstructed light or views, seasonal debris, overhang into gardens or parking areas, or general size.", "/environment/trees-grass-hedges/reporting-issues-with-trees-or-vegetation/nuisance-trees/", "Nuisance trees", ""),
    ("not_council_utility", "Overhead power lines", "To report an emergency with an overhead power line, call SSE on 0800 0727 282.", "/environment/trees-grass-hedges/reporting-issues-with-trees-or-vegetation/nuisance-trees/", "Nuisance trees", ""),
    ("council_housing_repair", "Emergency repairs: who and when", "Council tenants report emergency repairs by phone, not online: 023 8083 3006 (option two) in office hours, 023 8023 3344 outside them. Emergency means immediate danger to you, your family or property.", "/housing/council-housing-tenants-and-leaseholders/repairs-maintenance-and-improvements/emergency-repairs/", "Emergency repairs", ""),
    ("council_housing_repair", "Repair timings", "Emergency repairs are usually done the same day, within four hours; urgent repairs within two days; prioritised standard repairs get an appointment within 10 days; standard repairs within 25 days.", "/housing/council-housing-tenants-and-leaseholders/repairs-maintenance-and-improvements/report-a-repair/", "Report a repair", ""),
    ("flooding_severe_weather", "Flooding: who to call", "Call 999 if there is a danger to life. Southern Water has a 24-hour emergency line on 0330 303 0368. Non-life threatening flooding can be reported to the council on its form or on 023 8083 3000 in office hours.", "/environment/emergencies-flooding-and-other-severe-weather/flood-risk-management/report-a-flood/", "Report a flood", "The same page gives the out-of-hours number two ways; that number is left out here (see report)."),
]
with open(REPO / "agent" / "confirmed_with_websites.csv", encoding="utf-8") as f:
    cols = next(csv.reader(f))
with open(REPO / "reference" / "proposed_additions.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f, quoting=csv.QUOTE_ALL)
    w.writerow(cols)
    for cat, topic, fact, path, name, caveat in P:
        row = {"category_id": cat, "topic": topic, "confirmed_fact": fact, "source_type": "council_page",
               "source_name": name, "url": B + path, "date_checked": D, "caveat": caveat}
        w.writerow([row.get(c, "") for c in cols])
print(len(P), "proposed facts; columns:", cols)
