import unittest

from page_usage_service import PageUsageService


class PageUsageServiceTests(unittest.TestCase):
    def test_record_checks_schema_and_inserts_anonymous_device_event(self):
        sql_calls = []
        inserts = []
        service = PageUsageService(
            fetch_all=lambda *_args: [],
            execute_one=lambda sql, params: inserts.append((sql, params)),
            execute_sql=lambda sql, *_args: sql_calls.append(sql),
        )

        service.record({
            "page_id": "statistics",
            "client_id": "browser-1",
            "device_class": "mobile",
            "viewport_width": 390,
            "viewport_height": 844,
            "standalone": True,
            "user_agent": "test-agent",
        })

        self.assertEqual(len(sql_calls), 1)
        self.assertTrue(sql_calls[0].startswith("select "))
        self.assertIn("from hc.page_usage_event limit 0", sql_calls[0])
        self.assertEqual(inserts[0][1][:3], ("statistics", "browser-1", "mobile"))

    def test_summary_limits_range_and_returns_grouped_rows(self):
        queries = []
        expected = [{"page_id": "home", "device_class": "desktop", "views": 4, "devices": 1}]
        service = PageUsageService(
            fetch_all=lambda sql, params: queries.append((sql, params)) or expected,
            execute_one=lambda *_args: None,
            execute_sql=lambda *_args: None,
        )

        payload = service.summary(999)

        self.assertEqual(payload, {"ok": True, "days": 365, "rows": expected})
        self.assertEqual(queries[0][1], (365,))


if __name__ == "__main__":
    unittest.main()
