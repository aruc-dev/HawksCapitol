from __future__ import annotations

from datetime import date
import unittest

from ingestion.dedupe import dedupe_transactions
from ingestion.normalizer import normalize_records, parse_amount_range
from ingestion.reconciler import reconcile_transactions
from sources.committee_memberships import CommitteeSnapshot, visible_committees
from sources.house_clerk import parse_house_index
from sources.senate_efd import parse_senate_ptr_html
from sources.ticker_resolver import TickerResolver


class SourcesAndIngestionTests(unittest.TestCase):
    def test_house_index_filters_periodic_transaction_reports(self) -> None:
        xml = """
        <FinancialDisclosureReports>
          <Report><DocID>100</DocID><FilingType>P</FilingType><Name>Demo Senator</Name><FilingDate>2026-06-01</FilingDate></Report>
          <Report><DocID>101</DocID><FilingType>A</FilingType><Name>Other</Name><FilingDate>2026-06-01</FilingDate></Report>
        </FinancialDisclosureReports>
        """
        filings = parse_house_index(xml, 2026)
        self.assertEqual(len(filings), 1)
        self.assertEqual(filings[0].doc_id, "100")

    def test_senate_html_parser_maps_rows(self) -> None:
        html = "<table><tr><th>Transaction Date</th><th>Ticker</th></tr><tr><td>2026-05-01</td><td>AAPL</td></tr></table>"
        rows = parse_senate_ptr_html(html)
        self.assertEqual(rows[0]["transaction_date"], "2026-05-01")
        self.assertEqual(rows[0]["ticker"], "AAPL")

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

    def test_committee_snapshots_are_point_in_time(self) -> None:
        snapshots = [
            CommitteeSnapshot(date(2026, 1, 1), "m1", ("Finance",)),
            CommitteeSnapshot(date(2026, 7, 1), "m1", ("Armed Services",)),
        ]
        self.assertEqual(visible_committees(snapshots, "m1", date(2026, 6, 1)), ("Finance",))


if __name__ == "__main__":
    unittest.main()
