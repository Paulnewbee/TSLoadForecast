from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import Engine, text


@dataclass(frozen=True)
class IngestionContext:
    """
    Metadata describing one ingestion execution.
    """

    run_id: UUID
    source_name: str
    market_name: str | None

    dataset_name: str
    source_object: str | None

    target_database: str
    target_schema: str
    target_table: str

    requested_start: datetime | None
    requested_end: datetime | None

    started_at: datetime

    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadResult:
    """
    Result returned by a job's load operation.
    """

    records_loaded: int
    records_inserted: int | None = None
    records_updated: int | None = None
    records_rejected: int | None = None


class IngestionJob(ABC):
    """
    Interface implemented by every data ingestion job.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Source system, such as ERCOT_PUBLIC_API."""

    @property
    def market_name(self) -> str | None:
        """Optional market, such as ERCOT or PJM."""
        return None

    @property
    @abstractmethod
    def dataset_name(self) -> str:
        """Stable internal name for the dataset."""

    @property
    def source_object(self) -> str | None:
        """
        Source-specific report, endpoint, file, or table identifier.
        """
        return None

    @property
    @abstractmethod
    def target_schema(self) -> str:
        """Destination schema."""

    @property
    @abstractmethod
    def target_table(self) -> str:
        """Destination table."""

    @abstractmethod
    def extract(
        self,
        context: IngestionContext,
    ) -> Any:
        """
        Retrieve source data.

        The returned object may be a DataFrame, dictionary, list, file path,
        or another source-specific representation.
        """

    @abstractmethod
    def transform(
        self,
        extracted_data: Any,
        context: IngestionContext,
    ) -> pd.DataFrame:
        """
        Convert source data into the raw-table structure.
        """

    @abstractmethod
    def validate(
        self,
        df: pd.DataFrame,
        context: IngestionContext,
    ) -> None:
        """
        Raise an exception when validation fails.
        """

    @abstractmethod
    def load(
        self,
        df: pd.DataFrame,
        engine: Engine,
        context: IngestionContext,
    ) -> LoadResult:
        """
        Load the DataFrame into the destination.
        """


class IngestionPipelineError(RuntimeError):
    """Raised when an ingestion pipeline execution fails."""


class IngestionPipeline:
    """
    Generic ingestion runner for APIs, files, databases, and other sources.
    """

    def __init__(
        self,
        engine: Engine,
        database_name: str,
        metadata_schema: str = "raw",
        ingestion_table: str = "ingestion_runs",
    ) -> None:
        self.engine = engine
        self.database_name = database_name
        self.metadata_schema = metadata_schema
        self.ingestion_table = ingestion_table

    def run(
        self,
        job: IngestionJob,
        requested_start: datetime | None = None,
        requested_end: datetime | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> UUID:
        run_id = uuid4()
        started_at = datetime.now(timezone.utc)

        context = IngestionContext(
            run_id=run_id,
            source_name=job.source_name,
            market_name=job.market_name,
            dataset_name=job.dataset_name,
            source_object=job.source_object,
            target_database=self.database_name,
            target_schema=job.target_schema,
            target_table=job.target_table,
            requested_start=requested_start,
            requested_end=requested_end,
            started_at=started_at,
            parameters=dict(parameters or {}),
        )

        self._start_run(context)

        records_extracted: int | None = None

        try:
            extracted_data = job.extract(context)

            records_extracted = self._count_records(extracted_data)

            df = job.transform(
                extracted_data=extracted_data,
                context=context,
            )

            job.validate(
                df=df,
                context=context,
            )

            load_result = job.load(
                df=df,
                engine=self.engine,
                context=context,
            )

            self._complete_run(
                context=context,
                records_extracted=records_extracted,
                records_transformed=len(df),
                load_result=load_result,
            )

            return run_id

        except Exception as exc:
            self._fail_run(
                context=context,
                records_extracted=records_extracted,
                error_message=str(exc),
            )

            raise IngestionPipelineError(
                f"Ingestion run {run_id} failed for "
                f"{job.source_name}.{job.dataset_name}."
            ) from exc

    def _start_run(
        self,
        context: IngestionContext,
    ) -> None:
        query = text(
            f"""
            INSERT INTO {self.metadata_schema}.{self.ingestion_table} (
                ingestion_run_id,
                source_name,
                market_name,
                dataset_name,
                source_object,
                target_database,
                target_schema,
                target_table,
                requested_start,
                requested_end,
                request_parameters,
                started_at,
                status
            )
            VALUES (
                :ingestion_run_id,
                :source_name,
                :market_name,
                :dataset_name,
                :source_object,
                :target_database,
                :target_schema,
                :target_table,
                :requested_start,
                :requested_end,
                CAST(:request_parameters AS JSONB),
                :started_at,
                :status
            )
            """
        )

        import json

        values = {
            "ingestion_run_id": context.run_id,
            "source_name": context.source_name,
            "market_name": context.market_name,
            "dataset_name": context.dataset_name,
            "source_object": context.source_object,
            "target_database": context.target_database,
            "target_schema": context.target_schema,
            "target_table": context.target_table,
            "requested_start": context.requested_start,
            "requested_end": context.requested_end,
            "request_parameters": json.dumps(context.parameters),
            "started_at": context.started_at,
            "status": "STARTED",
        }

        with self.engine.begin() as connection:
            connection.execute(query, values)

    def _complete_run(
        self,
        context: IngestionContext,
        records_extracted: int | None,
        records_transformed: int,
        load_result: LoadResult,
    ) -> None:
        query = text(
            f"""
            UPDATE {self.metadata_schema}.{self.ingestion_table}
            SET
                completed_at = :completed_at,
                records_extracted = :records_extracted,
                records_transformed = :records_transformed,
                records_loaded = :records_loaded,
                records_inserted = :records_inserted,
                records_updated = :records_updated,
                records_rejected = :records_rejected,
                status = :status,
                error_message = NULL
            WHERE ingestion_run_id = :ingestion_run_id
            """
        )

        with self.engine.begin() as connection:
            connection.execute(
                query,
                {
                    "completed_at": datetime.now(timezone.utc),
                    "records_extracted": records_extracted,
                    "records_transformed": records_transformed,
                    "records_loaded": load_result.records_loaded,
                    "records_inserted": load_result.records_inserted,
                    "records_updated": load_result.records_updated,
                    "records_rejected": load_result.records_rejected,
                    "status": "SUCCESS",
                    "ingestion_run_id": context.run_id,
                },
            )

    def _fail_run(
        self,
        context: IngestionContext,
        records_extracted: int | None,
        error_message: str,
    ) -> None:
        query = text(
            f"""
            UPDATE {self.metadata_schema}.{self.ingestion_table}
            SET
                completed_at = :completed_at,
                records_extracted = :records_extracted,
                status = :status,
                error_message = :error_message
            WHERE ingestion_run_id = :ingestion_run_id
            """
        )

        with self.engine.begin() as connection:
            connection.execute(
                query,
                {
                    "completed_at": datetime.now(timezone.utc),
                    "records_extracted": records_extracted,
                    "status": "FAILED",
                    "error_message": error_message[:5000],
                    "ingestion_run_id": context.run_id,
                },
            )

    @staticmethod
    def _count_records(data: Any) -> int | None:
        """
        Estimate source record count without assuming a particular source type.
        """

        if isinstance(data, pd.DataFrame):
            return len(data)

        if isinstance(data, (list, tuple)):
            return len(data)

        if isinstance(data, dict):
            rows = data.get("data")

            if isinstance(rows, list):
                return len(rows)

        return None
