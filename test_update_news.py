import unittest
from datetime import datetime, timezone
from update_news import canonical_url, collect, parse_feed, select_items, short_summary

NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
SOURCE = {"id":"solidot", "name":"Solidot", "url":"https://example.com/rss", "category":"科技", "language":"zh-CN", "limit":6}
RSS = b'<rss><channel><item><title>AI research</title><link>https://example.com/a?utm_source=rss</link><description>&lt;p&gt;Hello &amp;amp; world&lt;/p&gt;</description><pubDate>Fri, 23 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'


class FeedTests(unittest.TestCase):
    def test_rss_classification_date_and_html(self):
        item = parse_feed(RSS, SOURCE, NOW)[0]
        self.assertEqual(item["category"], "AI")
        self.assertEqual(item["summary"], "Hello & world")
        self.assertEqual(item["url"], "https://example.com/a")
        self.assertEqual(item["publishedAt"], "2026-10-23T10:00:00Z")

    def test_rdf_and_atom(self):
        rdf = b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/"><item><title>Research</title><link>https://example.com/r</link><dc:date>2026-10-22</dc:date></item></rdf:RDF>'
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Report</title><link href="https://example.com/b"/><published>2026-10-22T09:00:00Z</published><summary>Short summary</summary></entry></feed>'
        generic_source = dict(SOURCE, id="research")
        self.assertEqual(len(parse_feed(rdf, generic_source, NOW)), 1)
        self.assertEqual(parse_feed(atom, generic_source, NOW)[0]["url"], "https://example.com/b")

    def test_bad_dates_links_and_entities(self):
        self.assertEqual(canonical_url("javascript:alert(1)"), "")
        self.assertEqual(parse_feed(RSS.replace(b"2026", b"2020"), SOURCE, NOW), [])
        self.assertEqual(parse_feed(RSS.replace(b"2026", b"2030"), SOURCE, NOW), [])
        with self.assertRaises(ValueError):
            parse_feed(b'<!DOCTYPE rss [<!ENTITY a "test">]><rss/>', SOURCE, NOW)

    def test_deduplication(self):
        item = parse_feed(RSS, SOURCE, NOW)[0]
        self.assertEqual(len(select_items([item, dict(item, url=item["url"] + "?utm_medium=rss")], 10)), 1)

    def test_partial_failure_retains_previous(self):
        other = dict(SOURCE, id="other", url="https://example.com/bad")
        previous = [dict(parse_feed(RSS, SOURCE, NOW)[0], sourceId="other", url="https://example.com/old", title="Old article")]
        def fetch(url):
            if url == other["url"]:
                raise OSError("offline")
            return RSS
        items, meta = collect([SOURCE, other], previous, NOW, fetch)
        self.assertEqual(len(items), 2)
        self.assertEqual(meta["sources"][1]["status"], "stale")

    def test_total_failure_aborts(self):
        with self.assertRaises(RuntimeError):
            collect([SOURCE], [], NOW, lambda _: b"not xml")

    def test_excerpt_length(self):
        self.assertLessEqual(len(short_summary("中" * 500, "zh-CN")), 81)
        self.assertLessEqual(len(short_summary("word " * 500, "en").split()), 26)


if __name__ == "__main__":
    unittest.main()
