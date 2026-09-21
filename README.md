# Forecast API

A small, stateless Python service using FastAPI and Prophet. No database or frontend.
Successful forecasts return only a JSON array, ready for your frontend chart.

## Run

Requires Python 3.12 or newer; verified with Python 3.13.15.

```sh
git clone https://github.com/Ilhom-Utkirov/forecast-api.git
cd forecast-api
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 3066
```

- Health: http://localhost:3066/health
- Interactive API docs: http://localhost:3066/docs
- Forecast: `POST http://localhost:3066/forecast`

In Swagger, expand **POST /forecast** and choose a request from the **Examples** dropdown:

- **Three months after June 2026** supplies the numbers, horizon, and full date; forecasts July–September 2026.
- **Numbers only — use defaults** forecasts 3 months, treating the last value as the server's current month.

Click **Try it out**, edit the numbers if needed, then **Execute** to see the actual JSON response.
Restart an existing server after code changes to load the updated examples.

For background execution, replace the last command with:

```sh
nohup .venv/bin/uvicorn main:app --host 0.0.0.0 --port 3066 > server.log 2>&1 < /dev/null &
```

If the service is already running, go straight to the tester. A second instance cannot
use the same port. The background command writes to `server.log` and does not arrange
startup after a reboot.

## Try your own numbers (Python only)

With the service running, start the interactive tester:

```sh
python3 try_forecast.py
```

Enter monthly numbers separated by commas or spaces, the forecast length, and optionally
the last historical month (`YYYY-MM-DD`). Press Enter to use the displayed defaults.
This is the month of your final historical value: for June 2026, enter `2026-06-01`,
not just `6`. The tester explains the format and lets you retry invalid dates before posting.
An invalid `--end-date` on the command line exits with a readable error.

| Prompt | Example | Pressing Enter |
| --- | --- | --- |
| Numbers (oldest first) | `37507,35186,40227,36288,33774,50809,52968` | Uses the sample numbers |
| Forecast months | `3` | Uses 3 |
| Last historical month (`YYYY-MM-DD`) | `2026-06-01` for June 2026 | Uses the server's current month |

If the final historical value is for June 2026 and you request 3 months, the result
dates are July, August, and September 2026.

The script makes a real POST request and prints the HTTP status and formatted JSON result.
HTTP 200 means success; HTTP 422 means the input needs correction. The tester uses only
Python's standard library and also displays connection errors and non-JSON server responses.

Or supply everything in one command:

```sh
python3 try_forecast.py --numbers "37507,35186,40227,36288,33774,50809,52968" --months 5 --end-date 2026-07-01
```

To test a deployment, replace the example URL with your service's base URL:

```sh
python3 try_forecast.py --url https://forecast.example.com --numbers "37507,35186,40227,36288,33774,50809,52968" --months 3 --end-date 2026-06-01
```

The tester appends `/forecast`. `CHRONOS_BASE_URL` can supply the default URL; an explicit
`--url` takes precedence.

## Request

Send this JSON to `POST /forecast` with `Content-Type: application/json`:

```json
{
  "historical_data": [37507, 35186, 40227, 36288, 33774, 50809, 52968],
  "forecast_months": 5,
  "end_date": "2026-07-01"
}
```

Send consecutive monthly values in oldest-to-newest order.

| Field | Meaning |
| --- | --- |
| `historical_data` | Required array of 6–1200 finite numbers. Zero and negative values are allowed. |
| `forecast_months` | Integer, defaults to 3. Allowed range: 1 through `min(12, historical_data.length)`. |
| `end_date` | Optional full calendar date of the last historical month, `YYYY-MM-DD`. Omit it or send null for the server's current month. Any day is normalized to day 1. |

The example treats the seven values as January–July 2026 and forecasts August–December 2026.
Validation failures return HTTP 422 with a JSON `detail`; computation failures return HTTP 500 with a JSON `detail`.
In particular, `end_date: "6"` now identifies `end_date` and explains the `YYYY-MM-DD`
format. Numeric timestamps are rejected. Model error tracebacks stay in server logs.

## Response for your frontend

A successful response is a JSON array with these fields in each item:

| Field | Meaning |
| --- | --- |
| `date` | Forecast month, `YYYY-MM-01` |
| `predicted_value` | Predicted number |
| `lower_bound` | Lower uncertainty bound |
| `upper_bound` | Upper uncertainty bound |

Use `date` on the chart's x-axis, `predicted_value` on the y-axis, and the bounds for an
uncertainty band. The service and test tools are Python.

CORS defaults to permitting any frontend origin without credentials. Set `CORS_ORIGINS`
to a comma-separated list of frontend origins to restrict it. The service listens on all
interfaces. If the browser runs on another machine, use the API server's hostname/IP in
place of `localhost`.

Each response contains exactly the requested number of future months. Values are rounded
to two decimal places. The model uses a trend with yearly, weekly, and daily seasonality
disabled, matching the supplied sample. Bounds use Prophet's 80% uncertainty interval;
they are sampled and can vary between requests. Predictions are not clamped to zero.
No fitting metrics or plots are returned.

Implementation references: [Prophet Python API](https://facebook.github.io/prophet/docs/quick_start.html)
and [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/).

## Automated tests

Tester regression checks need no server or third-party packages:

```sh
python3 -m unittest -v test_try_forecast.py
```

Run all tests with the service running on port 3066:

```sh
python3 -m unittest -v test_api.py test_try_forecast.py
```

The 15 tests cover real forecasts, date format and year rollover, history/horizon limits,
zero and negative values, invalid input, CORS, prompt retries, blank dates, deployment URLs,
and readable request failures. Tester tests mock HTTP; API tests send real requests.

For a deployment, set its URL and an allowed frontend origin:

```sh
CHRONOS_BASE_URL=https://forecast.example.com CHRONOS_TEST_ORIGIN=https://frontend.example.com python3 -m unittest -v test_api.py
```

The default-date check compares against the test machine's calendar month. Use the same
timezone as the server when running it near a month boundary.

## Deployment

For a Python host, install `requirements.txt` in a virtual environment and have your
process manager run this command from the project directory:

```sh
CORS_ORIGINS=https://frontend.example.com .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 3066 --workers 1
```

Configure the process manager to restart on failure and start after reboot. The service
needs no persistent data volume. `/health` checks that the API responds; a real `/forecast`
request also verifies the model runtime.

`CORS_ORIGINS` accepts origins including their scheme and port, for example
`http://localhost:5173,https://frontend.example.com`. It defaults to `*` for local testing.

An optional Dockerfile packages the same Python service with a non-root user and a health
check. With Docker running:

```sh
docker build -t forecast-api:local .
docker run -d --name forecast-api --restart unless-stopped -p 127.0.0.1:3066:3066 -e CORS_ORIGINS=https://frontend.example.com forecast-api:local
docker logs forecast-api
```

The published container port is bound to the host's loopback interface for use with a
reverse proxy. To test a container while local port 3066 is occupied, use
`-p 127.0.0.1:3067:3066` and pass `--url http://127.0.0.1:3067` to the Python tester.
Docker's restart policy handles process exits; an unhealthy health-check status alone
does not restart the container.

### Readiness checked on 2026-09-21

- A fresh Python 3.13.15 environment installed from `requirements.txt` using cached packages,
  with no dependency conflicts.
- A fresh service instance passed all 15 tests, OpenAPI inspection, and checks that a
  configured frontend origin is allowed while an unlisted origin is rejected by CORS.
- The Docker build has **not been verified**: Docker is installed here but its engine is stopped.
- Public deployment still needs HTTPS and access control/rate limits at the hosting layer.
  This service has no authentication or request rate limiter; CORS is not access control.
  Concurrent forecast capacity has not been load-tested.

The Python runtime is verified locally for a small internal deployment. Container/platform
validation and ingress configuration remain before a public production deployment.

Deployment reference: [FastAPI deployment documentation](https://fastapi.tiangolo.com/deployment/docker/).
