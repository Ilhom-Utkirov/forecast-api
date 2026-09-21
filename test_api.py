"""Integration checks against the running service; no test dependencies required."""

import json
import math
import os
import unittest
from datetime import date
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = os.getenv("CHRONOS_BASE_URL", "http://127.0.0.1:3066").rstrip("/")
TEST_ORIGIN = os.getenv("CHRONOS_TEST_ORIGIN", "http://localhost:5173")
SAMPLE = [37507, 35186, 40227, 36288, 33774, 50809, 52968]


def call(endpoint, payload=None, method=None, headers=None):
    request = Request(
        BASE_URL + endpoint,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        response = urlopen(request, timeout=60)
    except HTTPError as exc:
        response = exc
    with response:
        body = response.read().decode()
        return response.status, response.headers, body


class ForecastAPITest(unittest.TestCase):
    def test_health(self):
        status, _, body = call("/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"status": "ok"})

    def test_sample_forecast_and_cors(self):
        status, headers, body = call(
            "/forecast",
            {"historical_data": SAMPLE, "forecast_months": 5, "end_date": "2026-07-15"},
            headers={"Origin": TEST_ORIGIN},
        )
        self.assertEqual(status, 200, body)
        self.assertIn(headers["Access-Control-Allow-Origin"], ("*", TEST_ORIGIN))
        self.assertIn("application/json", headers["Content-Type"])
        points = json.loads(body)
        self.assertEqual([p["date"] for p in points], [f"2026-{m:02d}-01" for m in range(8, 13)])
        for point in points:
            self.assertEqual(set(point), {"date", "predicted_value", "lower_bound", "upper_bound"})
            for key in ("predicted_value", "lower_bound", "upper_bound"):
                self.assertTrue(math.isfinite(point[key]))
            self.assertLessEqual(point["lower_bound"], point["upper_bound"])

    def test_zero_history_and_year_rollover(self):
        status, _, body = call("/forecast", {
            "historical_data": [0] * 6, "forecast_months": 2, "end_date": "2025-12-01",
        })
        self.assertEqual(status, 200, body)
        points = json.loads(body)
        self.assertEqual([p["date"] for p in points], ["2026-01-01", "2026-02-01"])
        self.assertTrue(all(p["predicted_value"] == 0 for p in points))

    def test_defaults(self):
        today = date.today()
        status, _, body = call("/forecast", {"historical_data": SAMPLE})
        self.assertEqual(status, 200, body)
        points = json.loads(body)
        self.assertEqual(len(points), 3)
        next_month = date(today.year + today.month // 12, today.month % 12 + 1, 1)
        self.assertEqual(points[0]["date"], next_month.isoformat())

    def test_invalid_requests_return_json(self):
        invalid = [
            {},
            {"historical_data": SAMPLE[:5]},
            {"historical_data": [1] * 1201},
            *[{"historical_data": SAMPLE, "forecast_months": n} for n in (0, 8, 13, 1.5, True, "3")],
            *[{"historical_data": SAMPLE[:6] + [v]} for v in (None, "bad", "123", True, float("nan"), float("inf"))],
            {"historical_data": SAMPLE, "end_date": "bad-date"},
            {"historical_data": SAMPLE, "end_date": "9999-12-01"},
            {"historical_data": SAMPLE, "unexpected": 1},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                status, _, body = call("/forecast", payload)
                self.assertEqual(status, 422, body)
                self.assertIn("detail", json.loads(body))

    def test_dates_require_full_calendar_date(self):
        for end_date in ("6", "0", 0, "20260601", "2026-02-30", "2026-06-01T00:00:00"):
            with self.subTest(end_date=end_date):
                status, _, body = call("/forecast", {"historical_data": SAMPLE, "end_date": end_date})
                self.assertEqual(status, 422, body)
                error = json.loads(body)["detail"][0]
                self.assertEqual(error["loc"], ["body", "end_date"])
                self.assertIn("YYYY-MM-DD", error["msg"])

    def test_maximum_forecast_horizon(self):
        status, _, body = call("/forecast", {
            "historical_data": [-10] * 12, "forecast_months": 12, "end_date": "2025-12-01",
        })
        self.assertEqual(status, 200, body)
        points = json.loads(body)
        self.assertEqual([p["date"] for p in points], [f"2026-{m:02d}-01" for m in range(1, 13)])
        self.assertTrue(all(p["predicted_value"] == -10 for p in points))

    def test_browser_preflight(self):
        status, headers, _ = call("/forecast", method="OPTIONS", headers={
            "Origin": TEST_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        self.assertEqual(status, 200)
        self.assertIn(headers["Access-Control-Allow-Origin"], ("*", TEST_ORIGIN))
        self.assertIn("POST", headers["Access-Control-Allow-Methods"])


if __name__ == "__main__":
    unittest.main()
