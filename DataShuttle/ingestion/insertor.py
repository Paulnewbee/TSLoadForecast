from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pandas as pd
from psycopg2 import sql
from psycopg2.extras import execute_values
from sqlalchemy import Engine


@dataclass(frozen=True)
class TableLoadConfig:
    schema: str
    table: str
    columns: tuple[str, ...]
    key_columns: tuple[str, ...]
    update_columns: tuple[str, ...] | None = None

    def resolved_update_columns(self) -> tuple[str, ...]:
        if self.update_columns is not None:
            return self.update_columns

        return tuple(
            column for column in self.columns if column not in self.key_columns
        )


class PostgresDataFrameLoader:
    def __init__(
        self,
        engine: Engine,
        batch_size: int = 5_000,
    ) -> None:
        self.engine = engine
        self.batch_size = batch_size

    def upsert(
        self,
        df: pd.DataFrame,
        config: TableLoadConfig,
    ) -> int:
        self._validate_dataframe(df, config)

        if df.empty:
            return 0

        records = list(
            df[list(config.columns)].itertuples(
                index=False,
                name=None,
            )
        )

        update_columns = config.resolved_update_columns()

        query = self._build_upsert_query(
            config=config,
            update_columns=update_columns,
        )

        with self.engine.begin() as connection:
            dbapi_connection = connection.connection

            with dbapi_connection.cursor() as cursor:
                execute_values(
                    cursor,
                    query.as_string(cursor),
                    records,
                    page_size=self.batch_size,
                )

        return len(records)

    @staticmethod
    def _validate_dataframe(
        df: pd.DataFrame,
        config: TableLoadConfig,
    ) -> None:
        missing = set(config.columns) - set(df.columns)

        if missing:
            raise ValueError(
                f"DataFrame is missing required columns: {sorted(missing)}"
            )

        missing_keys = set(config.key_columns) - set(config.columns)

        if missing_keys:
            raise ValueError(
                f"Key columns are not present in configured columns: "
                f"{sorted(missing_keys)}"
            )

        if df[list(config.key_columns)].isna().any().any():
            raise ValueError("Upsert key columns contain null values.")

    @staticmethod
    def _build_upsert_query(
        config: TableLoadConfig,
        update_columns: Sequence[str],
    ) -> sql.Composed:
        destination = sql.Identifier(
            config.schema,
            config.table,
        )

        column_list = sql.SQL(", ").join(
            sql.Identifier(column) for column in config.columns
        )

        conflict_columns = sql.SQL(", ").join(
            sql.Identifier(column) for column in config.key_columns
        )

        if update_columns:
            update_assignments = sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(
                    sql.Identifier(column),
                    sql.Identifier(column),
                )
                for column in update_columns
            )

            conflict_action = sql.SQL("DO UPDATE SET {}").format(update_assignments)
        else:
            conflict_action = sql.SQL("DO NOTHING")

        return sql.SQL(
            """
            INSERT INTO {} ({})
            VALUES %s
            ON CONFLICT ({})
            {}
            """
        ).format(
            destination,
            column_list,
            conflict_columns,
            conflict_action,
        )
