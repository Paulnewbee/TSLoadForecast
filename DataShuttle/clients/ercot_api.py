from __future__ import annotations

import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

import pandas as pd
import requests


class ErcotAPIError(RuntimeError):
    """Raised when an ERCOT API request fails."""


class ErcotAPI:
    """
    Generic client for the ERCOT Public Data API.

    Parameters
    ----------
    username:
        ERCOT API Explorer username/email.
    password:
        ERCOT API Explorer password.
    subscription_key:
        ERCOT Public API subscription key.
    timeout:
        HTTP request timeout in seconds.
    max_retries:
        Maximum retry attempts for temporary failures.
    """

    BASE_URL = "https://api.ercot.com/api/public-reports"

    AUTH_URL = (
        "https://ercotb2c.b2clogin.com/"
        "ercotb2c.onmicrosoft.com/"
        "B2C_1_PUBAPI-ROPC-FLOW/oauth2/v2.0/token"
    )

    CLIENT_ID = "fec253ea-0d06-4272-a5e6-b478baeecd70"

    def __init__(
        self,
        username: str,
        password: str,
        subscription_key: str,
        timeout: int = 60,
        max_retries: int = 5,
    ) -> None:
        self.username = username
        self.password = password
        self.subscription_key = subscription_key
        self.timeout = timeout
        self.max_retries = max_retries

        self.session = requests.Session()

        self._id_token: str | None = None
        self._token_expires_at: datetime | None = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self, force: bool = False) -> str:
        """
        Obtain a new ERCOT ID token.

        A cached token is reused until shortly before it expires.
        """

        if not force and self._token_is_valid():
            return self._id_token  # type: ignore[return-value]

        payload = {
            "username": self.username,
            "password": self.password,
            "grant_type": "password",
            "scope": f"openid {self.CLIENT_ID} offline_access",
            "client_id": self.CLIENT_ID,
            "response_type": "id_token",
        }

        try:
            response = self.session.post(
                self.AUTH_URL,
                data=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            details = self._response_details(exc)
            raise ErcotAPIError(f"ERCOT authentication failed. {details}") from exc

        auth_data = response.json()
        id_token = auth_data.get("id_token")

        if not id_token:
            raise ErcotAPIError(
                "ERCOT authentication succeeded, but no id_token "
                f"was returned. Response: {auth_data}"
            )

        expires_in = int(auth_data.get("expires_in", 3600))

        self._id_token = id_token
        self._token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=expires_in
        )

        return id_token

    def _token_is_valid(self) -> bool:
        """Return True when the cached token is still usable."""

        if self._id_token is None or self._token_expires_at is None:
            return False

        # Renew five minutes before expiration.
        renewal_buffer = timedelta(minutes=5)

        return datetime.now(timezone.utc) < self._token_expires_at - renewal_buffer

    def _headers(self) -> dict[str, str]:
        token = self.authenticate()

        return {
            "Authorization": f"Bearer {token}",
            "Ocp-Apim-Subscription-Key": self.subscription_key,
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # General API requests
    # ------------------------------------------------------------------

    def request_json(
        self,
        path: str = "",
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make a GET request to an ERCOT Public Data API path.

        Examples
        --------
        path=""
            Gets the list of public reports.

        path="np6-345-cd/act_sys_load_by_wzn"
            Gets a specific report artifact.
        """

        clean_path = path.strip("/")
        url = self.BASE_URL

        if clean_path:
            url = f"{url}/{clean_path}"

        request_params = self._remove_empty_values(params or {})

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    headers=self._headers(),
                    params=request_params,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if attempt >= self.max_retries:
                    raise ErcotAPIError(
                        f"ERCOT request failed for {url}: {exc}"
                    ) from exc

                self._sleep_before_retry(attempt)
                continue

            # Token may have expired or been rejected.
            if response.status_code == 401 and attempt < self.max_retries:
                self.authenticate(force=True)
                continue

            # ERCOT rate limit or temporary server error.
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt >= self.max_retries:
                    raise ErcotAPIError(self._format_http_error(response))

                retry_after = response.headers.get("Retry-After")

                if retry_after and retry_after.isdigit():
                    time.sleep(int(retry_after))
                else:
                    self._sleep_before_retry(attempt)

                continue

            if not response.ok:
                raise ErcotAPIError(self._format_http_error(response))

            try:
                return response.json()
            except ValueError as exc:
                raise ErcotAPIError(
                    f"ERCOT returned a non-JSON response from {url}: "
                    f"{response.text[:500]}"
                ) from exc

        raise ErcotAPIError("ERCOT request failed unexpectedly.")

    # ------------------------------------------------------------------
    # Report retrieval
    # ------------------------------------------------------------------

    def get_report(
        self,
        report_code: str,
        report_name: str,
        start_date: str | date | datetime | None = None,
        end_date: str | date | datetime | None = None,
        start_param: str | None = None,
        end_param: str | None = None,
        params: dict[str, Any] | None = None,
        page_size: int = 1000,
        get_all_pages: bool = True,
        sort: str | None = None,
        direction: str = "ASC",
    ) -> pd.DataFrame:
        """
        Download an ERCOT report into a pandas DataFrame.

        Parameters
        ----------
        report_code:
            ERCOT report/product code, such as "np6-345-cd".

        report_name:
            Artifact endpoint, such as "act_sys_load_by_wzn".

        start_date, end_date:
            Optional date or datetime values.

        start_param, end_param:
            Exact query parameter names used by the report.

            Example:
                start_param="operatingDayFrom"
                end_param="operatingDayTo"

            These must be supplied when start_date/end_date are used because
            ERCOT reports do not all use the same date parameter names.

        params:
            Any additional report-specific filters.

        page_size:
            Number of records requested per page.

        get_all_pages:
            When True, retrieve all available pages.

        sort:
            Optional ERCOT field used for sorting.

        direction:
            "ASC" or "DESC".
        """

        if start_date is not None and not start_param:
            raise ValueError("start_param is required when start_date is provided.")

        if end_date is not None and not end_param:
            raise ValueError("end_param is required when end_date is provided.")

        query_params = dict(params or {})

        if start_date is not None:
            query_params[start_param] = self._format_date_value(start_date)

        if end_date is not None:
            query_params[end_param] = self._format_date_value(end_date)

        if sort is not None:
            query_params["sort"] = sort
            query_params["dir"] = direction.upper()

        path = f"{report_code.lower()}/{report_name}"

        if not get_all_pages:
            query_params.setdefault("page", 1)
            query_params.setdefault("size", page_size)

            response_data = self.request_json(
                path=path,
                params=query_params,
            )

            return self._extract_dataframe(response_data)

        return self._get_all_pages(
            path=path,
            params=query_params,
            page_size=page_size,
        )

    def _get_all_pages(
        self,
        path: str,
        params: dict[str, Any],
        page_size: int,
    ) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        page_number = 1

        while True:
            page_params = dict(params)
            page_params["page"] = page_number
            page_params["size"] = page_size

            response_data = self.request_json(
                path=path,
                params=page_params,
            )

            frame = self._extract_dataframe(response_data)

            if frame.empty:
                break

            frames.append(frame)

            total_pages = self._get_total_pages(response_data)

            if total_pages is not None:
                if page_number >= total_pages:
                    break
            elif len(frame) < page_size:
                break

            page_number += 1
            time.sleep(2.05)

        if not frames:
            return pd.DataFrame()

        return pd.concat(
            frames,
            ignore_index=True,
        )

    # ------------------------------------------------------------------
    # Report discovery
    # ------------------------------------------------------------------

    def list_products(
        self,
        params: dict[str, Any] | None = None,
        get_all_pages: bool = True,
        page_size: int = 1000,
    ) -> pd.DataFrame:
        """
        Retrieve ERCOT's list of available public-report products.
        """

        if not get_all_pages:
            data = self.request_json(
                params={
                    **(params or {}),
                    "page": 1,
                    "size": page_size,
                }
            )
            return self._extract_dataframe(data)

        return self._get_all_pages(
            path="",
            params=params or {},
            page_size=page_size,
        )

    def find_products(
        self,
        search_text: str,
    ) -> pd.DataFrame:
        """
        Search ERCOT product metadata by code, name, or description.
        """

        products = self.list_products()

        if products.empty:
            return products

        text_columns = [
            column
            for column in ["emilId", "name", "description"]
            if column in products.columns
        ]

        if not text_columns:
            return products.iloc[0:0]

        mask = pd.Series(False, index=products.index)

        for column in text_columns:
            mask |= (
                products[column]
                .fillna("")
                .astype(str)
                .str.contains(search_text, case=False, regex=False)
            )

        return products.loc[mask].reset_index(drop=True)

    # ------------------------------------------------------------------
    # JSON parsing helpers
    # ------------------------------------------------------------------

    @classmethod
    def _extract_dataframe(
        cls,
        response_data: dict[str, Any],
    ) -> pd.DataFrame:
        """
        Extract report data from known ERCOT response formats.
        """

        # Current ERCOT report format:
        # fields = [{"name": ...}, ...]
        # data = [[...], [...]]
        fields = response_data.get("fields")
        rows = response_data.get("data")

        if isinstance(fields, list) and isinstance(rows, list):
            column_names = [
                field["name"]
                for field in fields
                if isinstance(field, dict) and "name" in field
            ]

            if not rows:
                return pd.DataFrame(columns=column_names)

            if not column_names:
                raise ValueError("ERCOT response contains rows but no field names.")

            return pd.DataFrame(
                rows,
                columns=column_names,
            )

        # Optional fallback for HAL-style APIs.
        embedded = response_data.get("_embedded", {})

        if isinstance(embedded, dict):
            for value in embedded.values():
                if isinstance(value, list):
                    return pd.DataFrame(value)

        # Other possible generic response formats.
        for key in ("results", "records", "items"):
            value = response_data.get(key)

            if isinstance(value, list):
                return pd.DataFrame(value)

        return pd.DataFrame()

    @staticmethod
    def _get_total_pages(
        response_data: dict[str, Any],
    ) -> int | None:
        """
        Get the total number of pages from an ERCOT response.
        """

        meta = response_data.get("_meta", {})

        if not isinstance(meta, dict):
            return None

        total_pages = meta.get("totalPages")

        if total_pages is None:
            return None

        return int(total_pages)

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_date_value(
        value: str | date | datetime,
    ) -> str:
        """
        Format dates without unnecessarily removing datetime information.
        """

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, date):
            return value.isoformat()

        return str(value)

    @staticmethod
    def _remove_empty_values(
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Remove None values while preserving 0 and False."""

        return {key: value for key, value in params.items() if value is not None}

    @staticmethod
    def _sleep_before_retry(attempt: int) -> None:
        """Exponential backoff capped at 30 seconds."""

        delay = min(2**attempt, 30)
        time.sleep(delay)

    @staticmethod
    def _format_http_error(
        response: requests.Response,
    ) -> str:
        try:
            details: Any = response.json()
        except ValueError:
            details = response.text[:1000]

        return (
            f"ERCOT API returned HTTP {response.status_code} "
            f"for {response.url}. Response: {details}"
        )

    @staticmethod
    def _response_details(
        exc: requests.RequestException,
    ) -> str:
        response = exc.response

        if response is None:
            return str(exc)

        return ErcotAPI._format_http_error(response)

    def get_report_page(
        self,
        report_code: str,
        report_name: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = f"{report_code.lower()}/{report_name}"

        return self.request_json(
            path=path,
            params=params,
        )

    def list_products_basic(self) -> pd.DataFrame:
        """
        Return ERCOT products using a standardized basic structure.
        """

        products = self.list_products()

        output_columns = [
            "product_code",
            "product_name",
            "description",
            "report_name",
            "api_endpoint",
            "active",
            "last_discovered_at",
        ]

        if products.empty:
            return pd.DataFrame(columns=output_columns)

        candidates = {
            "product_code": [
                "emilId",
                "reportEMIL",
                "productCode",
                "product_code",
            ],
            "product_name": [
                "name",
                "displayName",
                "productName",
                "product_name",
            ],
            "description": [
                "description",
                "productDescription",
            ],
            "report_name": [
                "reportName",
                "report_name",
                "endpointName",
            ],
            "api_endpoint": [
                "endpoint",
                "apiEndpoint",
                "url",
                "href",
            ],
            "active": [
                "active",
                "isActive",
                "enabled",
            ],
        }

        basic = pd.DataFrame(index=products.index)

        for target_column, possible_sources in candidates.items():
            source_column = next(
                (column for column in possible_sources if column in products.columns),
                None,
            )

            if source_column is None:
                basic[target_column] = None
            else:
                basic[target_column] = products[source_column]

        basic["last_discovered_at"] = datetime.now(timezone.utc)

        return (
            basic[output_columns]
            .drop_duplicates(
                subset=[
                    "product_code",
                    "report_name",
                    "api_endpoint",
                ]
            )
            .reset_index(drop=True)
        )
