from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

import ingestion.reconciler as reconciler_module
from ingestion.pdf_parser import extract_text_from_pdf_bytes
from ingestion.dedupe import dedupe_transactions
from ingestion.normalizer import normalize_records, parse_amount_range
from ingestion.reconciler import reconcile_transactions
from scheduler import run_ingest
from sources.committee_memberships import CommitteeSnapshot, parse_committee_snapshot_rows, parse_committee_snapshot_xml, visible_committees
from sources.congressinvests import CongressInvestsSource
from sources.finnhub import FinnhubSource
from sources.fmp import FMPSource
from sources.history_loader import HistorySourceBlocked, load_house_archive_records, load_stock_watcher_records, validate_history_source
from sources.house_clerk import HouseClerkSource, parse_house_index, parse_house_index_zip, parse_house_ptr_text
from sources.base import RawFiling
from sources.senate_efd import SenateEFDSource, parse_senate_ptr_html
from sources.ticker_resolver import TickerResolver
from core.source_registry import load_source_registry


class _FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"", headers: dict | None = None, json_payload=None) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self._json_payload = json_payload

    @property
    def text(self) -> str:
        return self.content.decode("utf-8")

    def json(self):
        return self._json_payload


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = responses
        self.requests = []

    def get(self, url: str, headers: dict | None = None, timeout: int | None = None) -> _FakeResponse:
        self.requests.append({"method": "get", "url": url, "headers": headers or {}, "timeout": timeout})
        return self.responses.pop(0)

    def post(self, url: str, headers: dict | None = None, timeout: int | None = None, data=None) -> _FakeResponse:
        self.requests.append({"method": "post", "url": url, "headers": headers or {}, "timeout": timeout, "data": data})
        return self.responses.pop(0)


def _zip_bytes(name: str, content: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


class SourcesAndIngestionTests(unittest.TestCase):
    def test_house_index_filters_periodic_transaction_reports(self) -> None:
        xml = """
        <FinancialDisclosureReports>
          <Report><DocID>100</DocID><FilingType>P</FilingType><Name>Demo Senator</Name><FilingDate>2026-06-01</FilingDate></Report>
          <Report><DocID>101</DocID><FilingType>A</FilingType><Name>Other</Name><FilingDate>2026-06-01</FilingDate></Report>
          <Report><DocID>103</DocID><FilingType>P</FilingType><First>Mark</First><Last>Alford</Last><FilingDate>2026-06-02</FilingDate></Report>
          <Report><DocID>102</DocID><FilingType>P</FilingType><Name>Bad Date</Name><FilingDate>not-a-date</FilingDate></Report>
        </FinancialDisclosureReports>
        """
        filings = parse_house_index(xml, 2026)
        self.assertEqual(len(filings), 2)
        self.assertEqual(filings[0].doc_id, "100")
        self.assertEqual(filings[1].member_name, "Mark Alford")

    def test_house_index_zip_and_cache_fetch_are_fixture_safe(self) -> None:
        xml = """
        <FinancialDisclosureReports>
          <Report><DocID>200</DocID><FilingType>P</FilingType><Name>Demo Representative</Name><FilingDate>06/01/2026</FilingDate></Report>
        </FinancialDisclosureReports>
        """
        zip_payload = _zip_bytes("2026FD.xml", xml)
        filings = parse_house_index_zip(zip_payload, 2026)
        self.assertEqual(filings[0].doc_id, "200")
        with tempfile.TemporaryDirectory() as tmp:
            session = _FakeSession([_FakeResponse(200, zip_payload, {"ETag": "abc"}), _FakeResponse(304)])
            source = HouseClerkSource(year=2026, cache_dir=tmp, session=session, backoff_seconds=0)
            self.assertEqual(source.fetch(date(2026, 1, 1))[0].doc_id, "200")
            self.assertEqual(source.fetch(date(2026, 1, 1))[0].doc_id, "200")
            self.assertEqual(session.requests[1]["headers"]["If-None-Match"], "abc")
            bad_meta_cache = Path(tmp) / "bad-meta"
            cached_zip = bad_meta_cache / "financial-pdfs" / "2026FD.zip"
            cached_zip.parent.mkdir(parents=True)
            cached_zip.write_bytes(zip_payload)
            cached_zip.with_suffix(cached_zip.suffix + ".meta.json").write_text("{bad json", encoding="utf-8")
            bad_meta_session = _FakeSession([_FakeResponse(200, zip_payload, {"ETag": "fresh"})])
            bad_meta_source = HouseClerkSource(year=2026, cache_dir=bad_meta_cache, session=bad_meta_session, backoff_seconds=0)
            self.assertEqual(bad_meta_source.fetch(date(2026, 1, 1))[0].doc_id, "200")
            self.assertNotIn("If-None-Match", bad_meta_session.requests[0]["headers"])

    def test_pdf_text_extraction_and_house_ptr_rows_normalize(self) -> None:
        pdf = b"%PDF-1.4\n1 0 obj <<>> stream\nBT (Apple Inc. (AAPL) Purchase 2026-05-01 $1,001 - $15,000) Tj ET\nendstream\nendobj\n%%EOF"
        text, confidence = extract_text_from_pdf_bytes(pdf)
        self.assertIn("Apple Inc.", text)
        self.assertGreaterEqual(confidence, 0.6)
        raw = RawFiling("house_clerk", "pdf-1", "Demo Representative", date(2026, 6, 1))
        rows = parse_house_ptr_text(text, raw, confidence)
        self.assertEqual(rows[0]["ticker"], "AAPL")
        _, txs = normalize_records(rows, TickerResolver())
        self.assertEqual(txs[0].ticker, "AAPL")
        self.assertEqual(txs[0].tx_type, "buy")
        raw_pdf_text, raw_pdf_confidence = extract_text_from_pdf_bytes(b"%PDF-1.4\n1 0 obj << /Type /Catalog >>\nendobj\n%%EOF")
        self.assertNotIn("%PDF", raw_pdf_text)
        self.assertLess(raw_pdf_confidence, 0.8)
        plain_text, plain_confidence = extract_text_from_pdf_bytes(b"Transaction Date | Asset | Ticker\n2026-05-01 | Apple Inc. | AAPL")
        self.assertIn("Apple Inc.", plain_text)
        self.assertEqual(plain_confidence, 0.8)

    def test_house_real_ptr_table_blocks_normalize(self) -> None:
        text = """
        Periodic Transaction Report
        ID Owner Asset Transaction
        Type
        Date Notification
        Date
        Amount Cap.
        Gains >
        $200?
        Netflix, Inc. - Common Stock (NFLX)
        [ST]
        P 11/20/202511/20/2025 $100,001 -
        $250,000
        Filing Status: New
        JT CSW Industrials, Inc. Common Stock
        (CSW) [ST]
        P 11/17/202512/04/2025$1,001 - $15,000
        Filing Status: New
        T DC Innovex International, Inc. Common
        Stock (INVX) [ST]
        S 11/25/202511/26/2025 $1,140.00
        Filing Status: New
        BRKB Option [OT] P 11/19/202512/01/2025 $15,001 -
        $50,000
        Description: CALL BERKSHIRE CL B NEW $380 EXP 01/16/26
        """
        raw = RawFiling("house_clerk", "real-1", "Demo Representative", date(2025, 12, 10))
        rows = parse_house_ptr_text(text, raw, 0.9)
        self.assertEqual([row["ticker"] for row in rows], ["NFLX", "CSW", "INVX", None])
        self.assertEqual(rows[0]["asset_type"], "stock")
        self.assertEqual(rows[1]["owner"], "joint")
        self.assertEqual(rows[2]["owner"], "dependent")
        self.assertEqual(rows[3]["asset_type"], "option")
        _, txs = normalize_records(rows, TickerResolver())
        self.assertEqual(txs[0].tx_type, "buy")
        self.assertEqual(txs[2].amount_mid, 1140.0)
        self.assertEqual(txs[3].asset_type, "option")

    def test_house_source_parses_fixture_pdf_and_ingest_source_dry_run(self) -> None:
        xml = """
        <FinancialDisclosureReports>
          <Report><DocID>300</DocID><FilingType>P</FilingType><Name>Demo Representative</Name><FilingDate>2026-06-01</FilingDate></Report>
        </FinancialDisclosureReports>
        """
        pdf = b"Transaction Date | Asset | Ticker | Transaction Type | Amount | Owner\n2026-05-01 | Microsoft Corp | MSFT | Purchase | $15,001 - $50,000 | self"
        source = HouseClerkSource(fixture_xml=xml, fixture_pdfs={"300": pdf}, year=2026)
        records = [row for filing in source.fetch(date(2026, 1, 1)) for row in source.parse(filing)]
        self.assertEqual(records[0]["ticker"], "MSFT")
        result = run_ingest.run(dry_run=True, source="house_clerk", since=date(2026, 1, 1), year=2026)
        self.assertEqual(result["source"], "house_clerk")
        self.assertEqual(result["transactions"], 1)
        self.assertIn("would_write", result)

    def test_senate_html_parser_maps_rows(self) -> None:
        html = "<table><tr><th>Transaction Date</th><th>Asset Name</th><th>Ticker</th><th>Transaction Type</th><th>Amount</th></tr><tr><td>2026-05-01</td><td>Apple Inc.</td><td>AAPL</td><td>Purchase</td><td>$1,001 - $15,000</td></tr></table>"
        rows = parse_senate_ptr_html(html)
        self.assertEqual(rows[0]["tx_date"], "2026-05-01")
        self.assertEqual(rows[0]["ticker"], "AAPL")

    def test_senate_search_flow_and_report_parsing_are_recorded(self) -> None:
        landing = b'<input type="hidden" name="csrfmiddlewaretoken" value="token-1">'
        search_payload = {
            "data": [
                {
                    "doc_id": "sen-1",
                    "member_name": "Demo Senator",
                    "filing_date": "2026-06-02",
                    "url": "/search/view/sen-1/",
                }
            ]
        }
        report = b"""
        <table>
          <tr><th>Transaction Date</th><th>Asset Name</th><th>Ticker</th><th>Transaction Type</th><th>Amount</th><th>Owner</th></tr>
          <tr><td>2026-05-05</td><td>NVIDIA Corporation</td><td>NVDA</td><td>Purchase</td><td>$50,001 - $100,000</td><td>Self</td></tr>
        </table>
        """
        session = _FakeSession([
            _FakeResponse(200, landing),
            _FakeResponse(200, json_payload=search_payload),
            _FakeResponse(200, report, {"Content-Type": "text/html"}),
        ])
        source = SenateEFDSource(session=session, backoff_seconds=0)
        filings = source.fetch(date(2026, 1, 1))
        rows = source.parse(filings[0])
        self.assertEqual(filings[0].doc_id, "sen-1")
        self.assertEqual(rows[0]["ticker"], "NVDA")
        self.assertEqual(rows[0]["source"], "senate_efd")
        self.assertEqual(session.requests[1]["headers"]["X-CSRFToken"], "token-1")

    def test_senate_dry_run_and_options_amendments_normalize(self) -> None:
        result = run_ingest.run(dry_run=True, source="senate_efd", since=date(2026, 1, 1))
        self.assertEqual(result["source"], "senate_efd")
        self.assertEqual(result["transactions"], 1)
        disclosures, txs = normalize_records([
            {
                "doc_id": "opt-1",
                "source": "senate_efd",
                "member_name": "Demo Senator",
                "filing_date": "2026-06-01",
                "tx_date": "2026-05-01",
                "asset_name": "Apple Inc. $200 Call 06/19/2026",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
                "source_quality": "official",
                "parse_confidence": 0.4,
                "amended_doc_id": "old-1",
            }
        ], TickerResolver())
        self.assertEqual(disclosures[0].amends_doc_id, "old-1")
        self.assertEqual(txs[0].asset_type, "option")
        self.assertEqual(txs[0].option_meta["right"], "call")
        self.assertEqual(txs[0].parse_confidence, 0.4)
        _, malformed_expiry_txs = normalize_records([
            {
                "doc_id": "opt-bad-expiry",
                "source": "senate_efd",
                "member_name": "Demo Senator",
                "filing_date": "2026-06-01",
                "tx_date": "2026-05-01",
                "asset_name": "Apple Inc. $200 Call 2026-13-99",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
            }
        ], TickerResolver())
        self.assertEqual(malformed_expiry_txs[0].asset_type, "option")
        self.assertIsNone(malformed_expiry_txs[0].option_meta["expiry"])

    def test_amount_parser_and_normalizer(self) -> None:
        self.assertEqual(parse_amount_range("$1,001 - $15,000"), (1001.0, 15000.0, 8000.5))
        _, txs = normalize_records([
            {
                "doc_id": "d1",
                "source": "house_clerk",
                "member_name": "Demo Senator",
                "filing_date": "2026-06-01",
                "tx_date": "2026-05-01",
                "asset_name": "Apple Inc.",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
                "source_quality": "official",
            }
        ], TickerResolver())
        self.assertEqual(txs[0].ticker, "AAPL")
        self.assertEqual(txs[0].tx_type, "buy")
        self.assertEqual(txs[0].filing_lag_days, 31)

    def test_ticker_resolver_labeled_fixture_set(self) -> None:
        resolver = TickerResolver()
        fixtures = {
            "Apple Inc. Common Stock": "AAPL",
            "Microsoft Corporation": "MSFT",
            "NVIDIA Corp.": "NVDA",
            "Exxon Mobil Corporation": "XOM",
            "UnitedHealth Group Incorporated": "UNH",
            "Amazon.com, Inc.": "AMZN",
            "Alphabet Inc. Class A": "GOOGL",
            "Meta Platforms, Inc.": "META",
            "Tesla Inc": "TSLA",
            "Berkshire Hathaway Inc.": "BRK.B",
            "JPMorgan Chase & Co.": "JPM",
            "Johnson & Johnson": "JNJ",
            "Visa Inc.": "V",
            "Mastercard Incorporated": "MA",
            "Eli Lilly and Company": "LLY",
            "Broadcom Inc.": "AVGO",
            "Costco Wholesale Corporation": "COST",
            "Walmart Inc.": "WMT",
            "Netflix Inc": "NFLX",
            "Home Depot Inc.": "HD",
        }
        resolved = [resolver.resolve(asset) == symbol for asset, symbol in fixtures.items()]
        self.assertGreaterEqual(sum(resolved) / len(resolved), 0.95)
        self.assertEqual(resolver.resolve("Unlisted Holding (aapl)"), "AAPL")

    def test_dedupe_and_reconcile_prefer_official(self) -> None:
        _, txs = normalize_records([
            {
                "doc_id": "third",
                "source": "api",
                "member_name": "Demo Senator",
                "filing_date": "2026-06-01",
                "tx_date": "2026-05-01",
                "ticker": "AAPL",
                "asset_name": "Apple Inc.",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
                "source_quality": "third_party_only",
                "parse_confidence": 1.0,
            },
            {
                "doc_id": "official",
                "source": "house_clerk",
                "member_name": "Demo Senator",
                "filing_date": "2026-06-01",
                "tx_date": "2026-05-01",
                "ticker": "AAPL",
                "asset_name": "Apple Inc.",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
                "source_quality": "official",
                "parse_confidence": 0.8,
            },
        ])
        self.assertEqual(len(dedupe_transactions(txs)), 1)
        reconciled, warnings = reconcile_transactions(txs)
        self.assertEqual(reconciled[0].source, "house_clerk")
        self.assertTrue(warnings)

    def test_optional_sources_self_disable_and_parse_fixtures(self) -> None:
        self.assertEqual(FMPSource().fetch(date(2026, 1, 1)), [])
        self.assertFalse(FMPSource().health().ok)
        self.assertEqual(CongressInvestsSource().fetch(date(2026, 1, 1)), [])
        self.assertFalse(CongressInvestsSource().health().ok)
        self.assertFalse(FinnhubSource().health().ok)
        fixture = [
            {
                "doc_id": "api-1",
                "member_name": "Demo Senator",
                "filing_date": "2026-06-01",
                "transactionDate": "2026-05-01",
                "ticker": "AAPL",
                "assetDescription": "Apple Inc.",
                "transactionType": "Purchase",
                "amountRange": "$1,001 - $15,000",
            }
        ]
        source = FMPSource(fixture_payload=fixture)
        filings = source.fetch(date(2026, 1, 1))
        rows = source.parse(filings[0])
        self.assertEqual(rows[0]["source_quality"], "third_party_only")
        self.assertEqual(rows[0]["ticker"], "AAPL")
        fmp_with_bad_rows = FMPSource(fixture_payload=[{}, {"filing_date": "not-a-date"}, *fixture])
        self.assertEqual(len(fmp_with_bad_rows.fetch(date(2026, 1, 1))), 1)
        self.assertIn("skipped 2 invalid rows", fmp_with_bad_rows.health().message)
        congress_with_bad_rows = CongressInvestsSource(fixture_payload=[{"filingDate": ""}, {"filingDate": "broken"}, *fixture])
        self.assertEqual(len(congress_with_bad_rows.fetch(date(2026, 1, 1))), 1)
        self.assertIn("skipped 2 invalid rows", congress_with_bad_rows.health().message)

    def test_enabled_source_ingest_reports_per_source_health(self) -> None:
        result = run_ingest.run(dry_run=True, source="enabled", since=date(2026, 1, 1), year=2026)
        self.assertGreaterEqual(result["transactions"], 2)
        healthy_sources = {row["source"] for row in result["health"] if row["ok"]}
        self.assertIn("house_clerk", healthy_sources)
        self.assertIn("senate_efd", healthy_sources)

    def test_historical_loaders_are_fixture_safe_and_registry_gated(self) -> None:
        registry = load_source_registry("config/source_registry.yaml")
        with self.assertRaises(HistorySourceBlocked):
            validate_history_source(registry["stock_watcher"], fixture_only=False)
        stock_result = load_stock_watcher_records([
            {"doc_id": "bad-missing-date", "ticker": "MSFT"},
            {"doc_id": "bad-date", "filing_date": "not-a-date", "ticker": "MSFT"},
            {
                "doc_id": "sw-1",
                "member_name": "Demo Senator",
                "filing_date": "2024-06-01",
                "transaction_date": "2024-05-15",
                "ticker": "AAPL",
                "asset_description": "Apple Inc.",
                "type": "Purchase",
                "amount": "$1,001 - $15,000",
            }
        ], date(2024, 1, 1), fixture_only=True)
        self.assertEqual(stock_result.records[0]["source"], "stock_watcher")
        self.assertIn("skipped 2 invalid rows", stock_result.health[0].message)
        house_zip = _zip_bytes(
            "2024FD.xml",
            """
            <FinancialDisclosureReports>
              <Report><DocID>hist-1</DocID><FilingType>P</FilingType><Name>Demo Representative</Name><FilingDate>2024-06-01</FilingDate></Report>
            </FinancialDisclosureReports>
            """,
        )
        house_result = load_house_archive_records(
            {2024: house_zip},
            {"hist-1": b"Transaction Date | Asset | Ticker | Transaction Type | Amount\n2024-05-15 | Microsoft Corp | MSFT | Purchase | $15,001 - $50,000"},
            date(2024, 1, 1),
        )
        self.assertEqual(house_result.records[0]["ticker"], "MSFT")

    def test_historical_ingest_dry_runs_are_deterministic(self) -> None:
        stock = run_ingest.run(dry_run=True, source="stock_watcher", since=date(2024, 1, 1))
        house = run_ingest.run(dry_run=True, source="house_archive", since=date(2024, 1, 1), year=2024)
        self.assertEqual(stock["transactions"], 1)
        self.assertEqual(house["transactions"], 1)
        with self.assertRaises(ValueError):
            run_ingest.run(dry_run=False, source="house_archive", since=date(2024, 1, 1), year=2024)

    def test_ingest_non_dry_run_reports_all_written_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            reports_dir = Path(tmp) / "reports"
            result = run_ingest.run(dry_run=False, source="sample", output_dir=data_dir, reports_dir=reports_dir)

            self.assertIn(str(data_dir / "canonical" / "disclosures.json"), result["would_write"])
            self.assertIn(str(data_dir / "canonical" / "transactions.json"), result["would_write"])
            self.assertIn(str(reports_dir / "reconciliation.json"), result["would_write"])
            self.assertTrue((reports_dir / "reconciliation.json").exists())

    def test_amendments_supersede_and_fuzzy_records_collapse(self) -> None:
        _, txs = normalize_records([
            {
                "doc_id": "old",
                "source": "house_clerk",
                "member_name": "Demo Senator",
                "filing_date": "2026-06-01",
                "tx_date": "2026-05-01",
                "asset_name": "Apple Incorporated",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
                "source_quality": "official",
                "parse_confidence": 0.9,
            },
            {
                "doc_id": "new",
                "source": "house_clerk",
                "member_name": "Demo Senator",
                "filing_date": "2026-06-03",
                "tx_date": "2026-05-01",
                "asset_name": "Apple Inc.",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
                "source_quality": "official",
                "parse_confidence": 0.8,
                "amends_doc_id": "old",
            },
            {
                "doc_id": "api",
                "source": "fmp",
                "member_name": "Demo Senator",
                "filing_date": "2026-06-02",
                "tx_date": "2026-05-01",
                "asset_name": "Apple Inc",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
                "source_quality": "third_party_only",
                "parse_confidence": 1.0,
            },
        ], TickerResolver())
        deduped = dedupe_transactions(txs)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].doc_id, "new")
        reconciled, warnings = reconcile_transactions(txs)
        self.assertEqual(len(reconciled), 1)
        self.assertTrue(any("reconciled" in warning for warning in warnings))

    def test_reconcile_buckets_before_fuzzy_matching(self) -> None:
        _, txs = normalize_records([
            {
                "doc_id": "first",
                "source": "house_clerk",
                "member_name": "Demo Senator",
                "filing_date": "2026-06-01",
                "tx_date": "2026-05-01",
                "asset_name": "Apple Inc.",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
                "source_quality": "official",
            },
            {
                "doc_id": "second",
                "source": "house_clerk",
                "member_name": "Demo Senator",
                "filing_date": "2026-06-02",
                "tx_date": "2026-05-02",
                "asset_name": "Apple Inc.",
                "tx_type": "Purchase",
                "amount": "$1,001 - $15,000",
                "source_quality": "official",
            },
        ], TickerResolver())
        original_same_disclosed_trade = reconciler_module.same_disclosed_trade

        def guarded_same_disclosed_trade(left, right):
            if (left.member_id, left.tx_type, left.tx_date) != (right.member_id, right.tx_type, right.tx_date):
                raise AssertionError("cross-bucket fuzzy comparison")
            return original_same_disclosed_trade(left, right)

        try:
            reconciler_module.same_disclosed_trade = guarded_same_disclosed_trade
            reconciled, _ = reconcile_transactions(txs)
        finally:
            reconciler_module.same_disclosed_trade = original_same_disclosed_trade

        self.assertEqual(len(reconciled), 2)

    def test_committee_snapshots_are_point_in_time(self) -> None:
        snapshots = [
            CommitteeSnapshot(date(2026, 1, 1), "m1", ("Finance",)),
            CommitteeSnapshot(date(2026, 7, 1), "m1", ("Armed Services",)),
        ]
        self.assertEqual(visible_committees(snapshots, "m1", date(2026, 6, 1)), ("Finance",))
        rows = parse_committee_snapshot_rows([
            {"member_id": "m2", "committees": "Finance; Banking", "as_of_date": "2026-01-01"},
            {"member_id": "m4", "committees": "Rules", "as_of_date": "2026-13-99"},
        ], default_as_of=date(2026, 3, 1))
        self.assertEqual(rows[0].committees, ("Finance", "Banking"))
        self.assertEqual(visible_committees(rows, "m4", date(2026, 3, 2)), ("Rules",))
        xml_rows = parse_committee_snapshot_xml(
            "<Members><Member><member_id>m3</member_id><committee>Energy</committee></Member></Members>",
            date(2026, 2, 1),
        )
        self.assertEqual(visible_committees(xml_rows, "m3", date(2026, 2, 2)), ("Energy",))


if __name__ == "__main__":
    unittest.main()
