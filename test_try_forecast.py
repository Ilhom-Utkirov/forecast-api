"""Regression checks for the Python tester; no server or extra packages needed."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import try_forecast


class TesterTest(unittest.TestCase):
    def run_tester(self, args=(), answers=(), response_body=b"[]", status=200, error=None):
        response = io.BytesIO(response_body)
        response.status = status
        output, errors = io.StringIO(), io.StringIO()
        with (
            patch("sys.argv", ["try_forecast.py", *args]),
            patch("builtins.input", side_effect=answers),
            patch("try_forecast.urlopen", return_value=response, side_effect=error) as post,
            redirect_stdout(output), redirect_stderr(errors),
        ):
            result = try_forecast.main()
        return result, output.getvalue(), errors.getvalue(), post

    def test_invalid_interactive_date_retries_before_posting(self):
        result, output, _, post = self.run_tester(answers=["", "3", "6", "2026-06-01"])
        self.assertEqual(result, 0)
        self.assertIn("2026-06-01 means June 2026", output)
        self.assertIn("Invalid date:", output)
        self.assertIn("HTTP 200", output)
        post.assert_called_once()
        payload = json.loads(post.call_args.args[0].data)
        self.assertEqual(payload["end_date"], "2026-06-01")
        self.assertEqual(payload["historical_data"][-1], 52968)

    def test_blank_date_uses_server_default(self):
        result, _, _, post = self.run_tester(answers=["", "", ""])
        self.assertEqual(result, 0)
        payload = json.loads(post.call_args.args[0].data)
        self.assertNotIn("end_date", payload)
        self.assertEqual(payload["forecast_months"], 3)

    def test_cli_date_errors_never_post(self):
        for end_date in ("6", "0", "2026-02-30", "20260601"):
            with self.subTest(end_date=end_date), patch("try_forecast.urlopen") as post:
                with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()) as errors:
                    with patch("sys.argv", ["try_forecast.py", "--numbers", try_forecast.SAMPLE, "--end-date", end_date]):
                        try_forecast.main()
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("YYYY-MM-DD", errors.getvalue())
                post.assert_not_called()

    def test_custom_url_and_number_separators(self):
        result, _, _, post = self.run_tester(args=[
            "--numbers", "10, 20 30,40 50,60", "--months", "2",
            "--url", "https://forecast.example.com/api/", "--end-date", "2026-06-01",
        ])
        self.assertEqual(result, 0)
        request = post.call_args.args[0]
        self.assertEqual(request.full_url, "https://forecast.example.com/api/forecast")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data)["historical_data"], [10, 20, 30, 40, 50, 60])

    def test_json_validation_error_is_displayed(self):
        error = HTTPError(try_forecast.BASE_URL, 422, "Invalid input", {}, io.BytesIO(b'{"detail":"Too few months"}'))
        result, output, _, _ = self.run_tester(args=["--numbers", "1,2"], error=error)
        self.assertEqual(result, 1)
        self.assertIn("HTTP 422", output)
        self.assertIn("Too few months", output)

    def test_unreachable_service_has_helpful_message(self):
        result, _, errors, _ = self.run_tester(args=["--numbers", try_forecast.SAMPLE], error=URLError("Connection refused"))
        self.assertEqual(result, 1)
        self.assertIn("Check that Forecast API is reachable", errors)

    def test_non_json_response_has_helpful_message(self):
        result, output, errors, _ = self.run_tester(args=["--numbers", try_forecast.SAMPLE], response_body=b"Bad gateway", status=502)
        self.assertEqual(result, 1)
        self.assertIn("Bad gateway", output)
        self.assertIn("Expected JSON", errors)


if __name__ == "__main__":
    unittest.main()
