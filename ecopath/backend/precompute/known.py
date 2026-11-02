"""Species whose status is not in doubt, for reading cutoffs against.

The catalogue's `migratory` column cannot serve this purpose: it holds True for
11 species and False for the other 1,402, which is a column default rather than
a judgement. Treating those Falses as "known resident" would validate any cutoff
against 1,402 unverified labels and make a meaningless agreement figure look
excellent.

So the validation set is named explicitly here. The migrants are the ones the
catalogue does flag; the residents are common, unambiguous Indian breeding
residents that do not undertake latitudinal migration. Both lists are assertions
to be checked by someone who knows the birds — that is the point of showing them
in a table rather than burying them in a score.
"""

from __future__ import annotations

# Flagged migratory in the catalogue. Long-distance or altitudinal migrants
# whose Indian occurrence is strongly seasonal.
KNOWN_MIGRATORY = [
    "Greater Flamingo",
    "Lesser Flamingo",
    "Dalmatian Pelican",
    "Bar-headed Goose",
    "Demoiselle Crane",
    "Ruddy Shelduck",
    "Common Pochard",
    "Indian Spotted Eagle",
    "Indian Pitta",
    "Crab Plover",
    "Amur Falcon",
]

# Widespread Indian residents. Present year-round across their range; any large
# seasonal centroid shift for these is a sampling artefact, not migration.
KNOWN_RESIDENT = [
    "Asian Koel",
    "Red-whiskered Bulbul",
    "Rufous Treepie",
    "White-cheeked Barbet",
    "House Sparrow",
    "Jungle Babbler",
    "Coppersmith Barbet",
    "Brahminy Kite",
    "Laughing Dove",
    "White-breasted Waterhen",
    "Black-rumped Flameback",
    "Grey Francolin",
    "Common Iora",
    "Pied Bushchat",
    "Green Bee-eater",
    "Oriental White-eye",
    "Yellow-billed Babbler",
    "Plain Prinia",
    "Asian Palm-Swift",
    "Pale-billed Flowerpecker",
]


def known_status(common_name: str | None) -> str | None:
    """'migratory', 'resident', or None when the species is not in either list."""
    if not common_name:
        return None
    if common_name in KNOWN_MIGRATORY:
        return "migratory"
    if common_name in KNOWN_RESIDENT:
        return "resident"
    return None


ALL_KNOWN = KNOWN_MIGRATORY + KNOWN_RESIDENT
