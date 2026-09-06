"""Regression tests for the Central News Lake inverted indexes.

Two defects motivated these:

1. ``ingest_into_news_lake`` indexed article URLs into ``SECTOR_INVERTED_INDEX``,
   the same dict ``load_master_universe`` fills with ticker symbols and
   ``sector_index_service`` reads back as sector index constituents. Once the
   background news poller had run, sector constituent lists contained URLs.
2. Pruning the lake past ``MAX_LAKE_SIZE`` deleted articles but left the
   inverted indexes untouched, so they grew without bound and referenced
   evicted articles.
"""

import services.stock_service as ss


def _reset():
    ss.CENTRAL_NEWS_LAKE.clear()
    ss.TICKER_INVERTED_INDEX.clear()
    ss.NEWS_SECTOR_INVERTED_INDEX.clear()


def test_news_ingestion_does_not_pollute_sector_constituents():
    """Sector constituents must stay tickers; news links go to their own index."""
    _reset()
    ss.SECTOR_INVERTED_INDEX.setdefault("VNFIN", set()).clear()
    ss.SECTOR_INVERTED_INDEX["VNFIN"].update({"VCB", "TCB"})

    ss.ingest_into_news_lake([{
        "link": "https://cafef.vn/vcb-story-123.htm",
        "title": "VCB bao lai quy 3",
        "summary": "Vietcombank",
        "timestamp": 1,
    }])

    constituents = ss.SECTOR_INVERTED_INDEX["VNFIN"]
    assert constituents == {"VCB", "TCB"}
    assert not any(str(c).startswith("http") for c in constituents)
    # The link is still indexed - just in the news-specific index.
    assert any("cafef.vn" in link
               for links in ss.NEWS_SECTOR_INVERTED_INDEX.values()
               for link in links)
    _reset()


def test_pruning_evicts_links_from_inverted_indexes():
    """Indexes must not outlive the articles they point at."""
    _reset()
    total = ss.MAX_LAKE_SIZE + 600
    ss.ingest_into_news_lake([{
        "link": f"https://example.com/a{i}.htm",
        "title": "VCB bao lai quy 3",
        "summary": "Vietcombank",
        "timestamp": i,
    } for i in range(total)])

    assert len(ss.CENTRAL_NEWS_LAKE) == ss.MAX_LAKE_SIZE, "lake should be pruned"

    live = set(ss.CENTRAL_NEWS_LAKE)
    for index_name in ("TICKER_INVERTED_INDEX", "NEWS_SECTOR_INVERTED_INDEX"):
        index = getattr(ss, index_name)
        indexed = {link for links in index.values() for link in links}
        assert indexed <= live, f"{index_name} references {len(indexed - live)} evicted articles"
        assert all(index[k] for k in index), f"{index_name} retains empty key sets"
    _reset()
