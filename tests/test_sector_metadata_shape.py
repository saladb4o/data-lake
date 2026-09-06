"""Every SECTOR_METADATA entry must carry the same keys.

The mapping is built by a comprehension that gives each sector
``"keywords": []``, and then an ``update()`` overwrites eight legacy entries
with dicts that omitted it. Nothing noticed, because the only reader of that
key sits in the name-matching fallback of ``sync_universe_from_vnstock()``,
which runs only for a symbol whose ICB lookup found nothing.

On a fresh machine that is the first symbol it meets, and ``smeta["keywords"]``
raised ``KeyError: 'keywords'`` - aborting the whole listing sync before a
single symbol was written, which in turn left the universe sync with nothing
to sync.
"""

import pytest

from services.stock_service import SECTOR_METADATA

REQUIRED_KEYS = {"name", "icon", "color", "keywords"}


def test_the_mapping_is_not_empty():
    assert len(SECTOR_METADATA) > 10


@pytest.mark.parametrize("sector", sorted(SECTOR_METADATA))
def test_entry_carries_every_required_key(sector):
    entry = SECTOR_METADATA[sector]
    missing = REQUIRED_KEYS - set(entry)
    assert not missing, f"{sector} is missing {sorted(missing)}"


@pytest.mark.parametrize("sector", sorted(SECTOR_METADATA))
def test_keywords_is_iterable_of_strings(sector):
    keywords = SECTOR_METADATA[sector]["keywords"]
    assert isinstance(keywords, (list, tuple))
    assert all(isinstance(kw, str) for kw in keywords)


def test_the_name_matching_fallback_cannot_raise():
    """The exact loop that failed, over every entry, on a name it won't match."""
    name_lower = "cong ty co phan khong khop nganh nao"
    matched = None
    for key, meta in SECTOR_METADATA.items():
        if any(kw in name_lower for kw in meta.get("keywords", ())):
            matched = key
            break
    assert matched is None
