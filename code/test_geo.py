"""Tests for geo/southampton.py: the city boundary and the street list. Offline.

Run: python code/test_geo.py
"""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geo import southampton as city  # noqa: E402


class BoundaryTest(unittest.TestCase):
    INSIDE = {"City centre": (50.9097, -1.4044), "Bitterne": (50.9178, -1.3626), "Woolston": (50.8967, -1.3753),
              "Swaythling": (50.9373, -1.3858), "Bassett": (50.9390, -1.4029), "Lordshill": (50.9420, -1.4590)}
    # SO postcodes, other councils: a postcode prefix would get every one of these wrong.
    OUTSIDE = {"Eastleigh": (50.9686, -1.3527), "Totton": (50.9170, -1.4900), "West End": (50.9286, -1.3367),
               "Netley": (50.8740, -1.3460), "Chandler's Ford": (50.9840, -1.3820), "Hythe": (50.8600, -1.3990)}

    def test_inside_the_city(self):
        for name, point in self.INSIDE.items():
            self.assertTrue(city.in_city(*point), name)

    def test_outside_the_city(self):
        for name, point in self.OUTSIDE.items():
            self.assertFalse(city.in_city(*point), name)

    def test_far_away(self):
        self.assertFalse(city.in_city(51.5074, -0.1278))   # London


class StreetTest(unittest.TestCase):
    def test_the_list_is_loaded(self):
        self.assertGreater(city.street_count(), 2000)

    def test_short_forms_are_the_same_street(self):
        for typed in ("Lawn Road", "lawn rd", "LAWN RD.", "Lawn  Road"):
            self.assertEqual(city.normalise(typed), "lawn rd", typed)
        self.assertEqual(city.normalise("St Mary's Road"), city.normalise("saint marys rd"))

    def test_a_street_inside_a_sentence(self):
        rows = city.street_in_text("massive pothole outside 12 lawn rd, nearly burst my tyre")
        self.assertEqual([r["street"] for r in rows], ["Lawn Road"])
        self.assertEqual(rows[0]["area"], "Portswood Park")

    def test_a_long_road_and_the_area_the_resident_named(self):
        rows = city.street_in_text("bins on burgess rd in swaythling")
        self.assertGreater(len(rows), 1)
        self.assertEqual(city.area_in_text(rows, "bins on burgess rd in swaythling")["area"], "Swaythling")

    def test_no_street_no_match(self):
        for text in ("fly tipping by the shops", "pothole on the M27", "lawn", "", "hi"):
            self.assertEqual(city.street_in_text(text), [], text)

    def test_drop_down_suggestions(self):
        labels = [r["label"] for r in city.find_streets("lawn r")]
        self.assertEqual(labels[0], "Lawn Road, Portswood Park")
        self.assertTrue(any(r["street"].startswith("St Mary") for r in city.find_streets("st mar")))
        self.assertEqual(city.find_streets("a"), [])

    def test_fast_enough_for_every_message(self):
        started = time.perf_counter()
        for _ in range(200):
            city.street_in_text("there is a pothole outside number 12 lawn road in portswood")
        self.assertLess((time.perf_counter() - started) / 200, 0.005)


class SharedLocationTest(unittest.TestCase):
    def test_maps_links_and_cards(self):
        cases = {
            "https://maps.apple.com/place?coordinate=50.906932,-1.405823&name=Dropped%20Pin": (50.906932, -1.405823),
            "https://maps.apple.com/?ll=50.9178,-1.3626&q=Pin": (50.9178, -1.3626),
            "https://www.google.com/maps/@50.9097,-1.4044,17z": (50.9097, -1.4044),
            "geo:50.91,-1.40": None,   # too few decimals to be a real pin
            "URL;type=pref:http://maps.apple.com/?ll=50.937300\\,-1.385800&q=My%20Location": (50.9373, -1.3858),
        }
        for text, want in cases.items():
            self.assertEqual(city.coords_in_text(text), want, text)
        self.assertIsNone(city.coords_in_text("no coordinates in 12.3 here"))


class OutsidePlaceTest(unittest.TestCase):
    def test_towns_outside_the_city(self):
        for text, want in (("pothole in eastleigh", "eastleigh"), ("dumped sofa in totton", "totton"),
                           ("fly tipping in west end", "west end"),
                           ("pothole near chandler's ford", "chandler's ford")):
            self.assertEqual(city.names_outside_place(text), want, text)

    def test_city_streets_named_after_towns_are_not_towns(self):
        for text in ("pothole on west end road", "pothole on west end rd bitterne", "bins on romsey rd shirley",
                     "pothole on portsmouth road woolston", "lawn road"):
            self.assertIsNone(city.names_outside_place(text), text)

    def test_postcodes(self):
        self.assertEqual(city.postcode_in_text("near so17 1bj please"), "SO17 1BJ")
        self.assertIsNone(city.postcode_in_text("no postcode"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
