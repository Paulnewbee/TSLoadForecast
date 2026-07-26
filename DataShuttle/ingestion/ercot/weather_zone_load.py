from datetime import date, datetime
from psycopg2.extras import execute_values
from DataShuttle.ingestion.pipeline import IngestionContext, IngestionJob, LoadResult
from DataShuttle.ingestion.insertor import PostgresDataFrameLoader, TableLoadConfig
from DataShuttle.clients.ercot_api import ErcotAPI
import pandas as pd
from sqlalchemy.engine import Engine


WEATHER_ZONE_LOAD_TABLE = TableLoadConfig(
    schema="raw",
    table="ercot_weather_zone_load",
    columns=(
        "operating_day",
        "hour_ending",
        "coast",
        "east",
        "far_west",
        "north",
        "north_c",
        "southern",
        "south_c",
        "west",
        "total",
        "dst_flag",
        "ingestion_run_id",
        "extracted_at",
    ),
    key_columns=(
        "operating_day",
        "hour_ending",
        "dst_flag",
    ),
)


class ErcotWeatherZoneLoadJob(IngestionJob):
    def __init__(
        self,
        api: ErcotAPI,
        start_date: str | date | datetime,
        end_date: str | date | datetime,
    ) -> None:
        self.api = api
        self.start_date = start_date
        self.end_date = end_date

    @property
    def source_name(self) -> str:
        return "ERCOT_PUBLIC_API"

    @property
    def market_name(self) -> str:
        return "ERCOT"

    @property
    def dataset_name(self) -> str:
        return "weather_zone_load"

    @property
    def source_object(self) -> str:
        return "NP6-345-CD/act_sys_load_by_wzn"

    @property
    def target_schema(self) -> str:
        return "raw"

    @property
    def target_table(self) -> str:
        return "ercot_weather_zone_load"

    def extract(
        self,
        context: IngestionContext,
    ) -> pd.DataFrame:
        return self.api.get_report(
            report_code="NP6-345-CD",
            report_name="act_sys_load_by_wzn",
            start_date=self.start_date,
            end_date=self.end_date,
            start_param="operatingDayFrom",
            end_param="operatingDayTo",
            sort="operatingDay",
            direction="ASC",
        )

    def transform(
        self,
        extracted_data: pd.DataFrame,
        context: IngestionContext,
    ) -> pd.DataFrame:
        rename_map = {
            "operatingDay": "operating_day",
            "hourEnding": "hour_ending",
            "farWest": "far_west",
            "northC": "north_c",
            "southC": "south_c",
            "DSTFlag": "dst_flag",
        }

        df = extracted_data.rename(columns=rename_map).copy()

        df["operating_day"] = pd.to_datetime(
            df["operating_day"],
            errors="raise",
        ).dt.date

        df["ingestion_run_id"] = context.run_id
        df["extracted_at"] = context.started_at

        return df

    def validate(
        self,
        df: pd.DataFrame,
        context: IngestionContext,
    ) -> None:
        required = {
            "operating_day",
            "hour_ending",
            "coast",
            "east",
            "far_west",
            "north",
            "north_c",
            "southern",
            "south_c",
            "west",
            "total",
            "dst_flag",
            "ingestion_run_id",
            "extracted_at",
        }

        missing = required - set(df.columns)

        if missing:
            raise ValueError(f"Missing ERCOT fields: {sorted(missing)}")

        if df.empty:
            raise ValueError("ERCOT returned no rows.")

        duplicate_mask = df.duplicated(
            subset=[
                "operating_day",
                "hour_ending",
                "dst_flag",
            ],
            keep=False,
        )

        if duplicate_mask.any():
            raise ValueError("Duplicate ERCOT weather-zone records found.")

    def load(
        self,
        df: pd.DataFrame,
        engine: Engine,
        context: IngestionContext,
    ) -> LoadResult:
        loader = PostgresDataFrameLoader(engine)
        loaded = loader.upsert(
            df=df,
            config=WEATHER_ZONE_LOAD_TABLE,
        )

        return LoadResult(records_loaded=loaded)
