from datetime import date, datetime
from psycopg2.extras import execute_values
from DataShuttle.ingestion.insertor import PostgresDataFrameLoader, TableLoadConfig
from DataShuttle.ingestion.pipeline import IngestionContext, IngestionJob, LoadResult
from DataShuttle.clients.ercot_api import ErcotAPI
import pandas as pd
from sqlalchemy.engine import Engine

LOAD_ZONE_LOAD_TABLE = TableLoadConfig(
    schema="raw",
    table="ercot_load_zone_load",
    columns=(
        "operating_day",
        "hour_ending",
        "north",
        "south",
        "west",
        "houston",
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


class ErcotLoadZoneLoadJob(IngestionJob):
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
        return "load_zone_load"

    @property
    def source_object(self) -> str:
        return "np6-346-cd/act_sys_load_by_fzn"

    @property
    def target_schema(self) -> str:
        return "raw"

    @property
    def target_table(self) -> str:
        return "ercot_load_zone_load"

    def extract(
        self,
        context: IngestionContext,
    ) -> pd.DataFrame:
        return self.api.get_report(
            report_code="NP6-346-CD",
            report_name="act_sys_load_by_fzn",
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
            "north",
            "south",
            "west",
            "houston",
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
            raise ValueError("Duplicate ERCOT load-zone records found.")

    def load(
        self,
        df: pd.DataFrame,
        engine: Engine,
        context: IngestionContext,
    ) -> LoadResult:
        loader = PostgresDataFrameLoader(engine)

        loaded = loader.upsert(
            df=df,
            config=LOAD_ZONE_LOAD_TABLE,
        )

        return LoadResult(records_loaded=loaded)
