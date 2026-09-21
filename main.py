"""Monthly Prophet forecasts as a small, stateless JSON API."""

import logging
import os
from datetime import date
from typing import Annotated

import pandas as pd
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prophet import Prophet
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator, model_validator

logger = logging.getLogger(__name__)

app = FastAPI(title="Forecast API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

HistoricalValue = Annotated[float, Field(strict=True, allow_inf_nan=False)]

FORECAST_EXAMPLES = {
    "with_date": {
        "summary": "Three months after June 2026",
        "description": "Seven historical values ending in June 2026; forecasts July–September 2026.",
        "value": {
            "historical_data": [37507, 35186, 40227, 36288, 33774, 50809, 52968],
            "forecast_months": 3,
            "end_date": "2026-06-01",
        },
    },
    "defaults": {
        "summary": "Numbers only — use defaults",
        "description": "Forecasts 3 months, treating the final value as the server's current month.",
        "value": {
            "historical_data": [37507, 35186, 40227, 36288, 33774, 50809, 52968],
        },
    },
}


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    historical_data: list[HistoricalValue] = Field(min_length=6, max_length=1200)
    forecast_months: int = Field(default=3, strict=True, ge=1, le=12)
    end_date: date | None = Field(
        default=None,
        description="Last historical month (YYYY-MM-DD). Defaults to the current month. "
        "The day is normalized to the first of that month.",
        examples=["2026-06-01"],
    )

    @field_validator("end_date", mode="before")
    @classmethod
    def check_end_date(cls, value):
        if value is None or type(value) is date:
            return value
        if isinstance(value, str):
            try:
                if date.fromisoformat(value).isoformat() == value:
                    return value
            except ValueError:
                pass
        raise ValueError(
            "end_date must be a full YYYY-MM-DD date, e.g. 2026-06-01 for June 2026; "
            "omit it to use the current month"
        )

    @model_validator(mode="after")
    def check_horizon(self):
        if self.forecast_months > len(self.historical_data):
            raise ValueError("forecast_months cannot exceed the number of historical months")
        return self


class ForecastPoint(BaseModel):
    date: str
    predicted_value: FiniteFloat
    lower_bound: FiniteFloat
    upper_bound: FiniteFloat


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Omit raw input/context so even rejected NaN/Infinity values produce valid JSON.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {key: error[key] for key in ("loc", "msg", "type")}
                for error in exc.errors()
            ]
        },
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/forecast", response_model=list[ForecastPoint])
def forecast(payload: Annotated[ForecastRequest, Body(openapi_examples=FORECAST_EXAMPLES)]):
    """Forecast consecutive monthly values supplied in oldest-to-newest order."""
    end = (payload.end_date or date.today()).replace(day=1)
    try:
        history_dates = pd.date_range(
            end=end, periods=len(payload.historical_data), freq="MS"
        ).as_unit("ns")
        future_dates = pd.date_range(
            start=history_dates[-1], periods=payload.forecast_months + 1, freq="MS"
        ).as_unit("ns")[1:]
    except (ValueError, OverflowError) as exc:
        raise HTTPException(status_code=422, detail="Requested dates are outside the supported date range") from exc

    try:
        model = Prophet(
            yearly_seasonality=False,
            weekly_seasonality=False,
            daily_seasonality=False,
            interval_width=0.8,
        )
        model.fit(pd.DataFrame({"ds": history_dates, "y": payload.historical_data}))
        predictions = model.predict(pd.DataFrame({"ds": future_dates}))
        return [
            ForecastPoint(
                date=row.ds.strftime("%Y-%m-%d"),
                predicted_value=round(float(row.yhat), 2),
                lower_bound=round(float(row.yhat_lower), 2),
                upper_bound=round(float(row.yhat_upper), 2),
            )
            for row in predictions.itertuples(index=False)
        ]
    except Exception as exc:
        logger.exception("Forecast failed")
        raise HTTPException(status_code=500, detail="Unable to compute a forecast for this data") from exc
