"""Enter monthly numbers, POST them to Forecast API, and print the JSON result."""

import argparse
import json
import os
import sys
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:3066"
SAMPLE = "37507,35186,40227,36288,33774,50809,52968"


def validate_end_date(value):
    if not value:
        return value
    try:
        if date.fromisoformat(value).isoformat() == value:
            return value
    except ValueError:
        pass
    raise ValueError(
        "Enter a valid full date: YYYY-MM-DD, e.g. 2026-06-01 for June 2026. "
        "A month number such as 6 is not enough. Leave blank for the current month."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--numbers", help="Comma- or space-separated monthly numbers.")
    parser.add_argument("--months", type=int, help="Months to forecast (default: 3).")
    parser.add_argument("--end-date", help="Month of the final value: YYYY-MM-DD, e.g. 2026-06-01 for June 2026.")
    parser.add_argument(
        "--url", default=os.getenv("CHRONOS_BASE_URL", BASE_URL),
        help="Service base URL (default: CHRONOS_BASE_URL or http://127.0.0.1:3066).",
    )
    args = parser.parse_args()
    url = args.url.rstrip("/") + "/forecast"

    try:
        if args.numbers is None:
            print("Enter at least 6 monthly values, oldest first. Enter accepts defaults.")
            args.numbers = input(f"Numbers [{SAMPLE}]: ").strip() or SAMPLE
            if args.months is None:
                args.months = int(input("Forecast months [3]: ").strip() or "3")
            if args.end_date is None:
                print("Last historical month means the month of your FINAL number.")
                print("Example: 2026-06-01 means June 2026. Press Enter for the current month.")
                while True:
                    entered_date = input("Last historical month (YYYY-MM-DD) [current month]: ").strip()
                    try:
                        args.end_date = validate_end_date(entered_date)
                        break
                    except ValueError as exc:
                        print(f"Invalid date: {exc}")

        payload = {
            "historical_data": [float(n) for n in args.numbers.replace(",", " ").split()],
            "forecast_months": args.months if args.months is not None else 3,
        }
        if args.end_date:
            payload["end_date"] = validate_end_date(args.end_date)
        body = json.dumps(payload, allow_nan=False).encode()
    except (ValueError, EOFError) as exc:
        parser.error(f"Invalid input: {exc}")

    print(f"\nPOST {url}\n{body.decode()}\n", flush=True)
    request = Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        response = urlopen(request, timeout=60)
    except HTTPError as exc:
        response = exc  # Show the API's JSON validation error as well.
    except (URLError, TimeoutError) as exc:
        print(f"Request failed: {exc}. Check that Forecast API is reachable at {args.url}.", file=sys.stderr)
        return 1

    with response:
        print(f"HTTP {response.status}")
        response_body = response.read().decode("utf-8", errors="replace")
        try:
            result = json.loads(response_body)
        except json.JSONDecodeError:
            print(response_body)
            print("Expected JSON from the forecast API. Check the URL and server logs.", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2))
        return 0 if response.status == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
