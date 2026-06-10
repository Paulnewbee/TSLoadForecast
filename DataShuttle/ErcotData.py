import pandas as pd
import requests
import re
from typing import Any, List, Optional, Union
from datetime import datetime


class ErcotShuttle:
    LIST_ENDPOINT = "https://www.ercot.com/misapp/servlets/IceDocListJsonWS"
    DOWNLOAD_ENDPOINT = (
        "https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId="
    )

    def __init__(
        self,
        start_date: Union[str, datetime],
        end_date: Union[str, datetime],
        report_type: Union[int, str],
    ):
        self.start_date = self._parse_date(start_date)
        self.end_date = self._parse_date(end_date)
        self.report_type = int(report_type)

        if self.end_date < self.start_date:
            raise ValueError("end_date must be the same as or after start_date")

    @staticmethod
    def _parse_date(value: Union[str, datetime]) -> datetime:
        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y", "%m/%d/%y"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue

        raise ValueError(f"Unable to parse date from {value!r}")

    def _build_list_url(self) -> str:
        return f"{self.LIST_ENDPOINT}?reportTypeId={self.report_type}"

    def _build_doc_url(self, doc_id: Any) -> str:
        return f"{self.DOWNLOAD_ENDPOINT}{doc_id}"

    def fetch_files_list(self, url: Optional[str] = None) -> pd.DataFrame:
        target_url = url or self._build_list_url()
        response = requests.get(target_url)
        response.raise_for_status()

        payload = response.json()
        documents = payload.get("ListDocsByRptTypeRes", {}).get("DocumentList", [])

        extracted_data = []
        for doc in documents:
            document = doc.get("Document", {})
            extracted_data.append(
                {
                    "DocID": document.get("DocID"),
                    "ReportName": document.get("ReportName"),
                    "FriendlyName": document.get("FriendlyName"),
                    "DocDate": document.get("DocDate") or document.get("Date"),
                }
            )

        df_urls = pd.DataFrame(extracted_data)
        if df_urls.empty:
            return df_urls

        # Prefer CSV over XML when a report exists in multiple formats.
        if "FriendlyName" in df_urls.columns:

            def _split_base_fmt(s: Any):
                if not isinstance(s, str):
                    return (s, "")
                parts = s.rsplit("_", 1)
                if len(parts) == 2:
                    return parts[0], parts[1].lower()
                return s, ""

            bases_and_fmts = df_urls["FriendlyName"].map(_split_base_fmt).tolist()
            df_urls[["_base", "_fmt"]] = pd.DataFrame(
                bases_and_fmts, index=df_urls.index
            )

            keep_indexes = []
            for base, group in df_urls.groupby("_base"):
                if (group["_fmt"] == "csv").any():
                    keep = group[group["_fmt"] == "csv"]
                else:
                    keep = group.iloc[[0]]
                keep_indexes.extend(keep.index.tolist())

            df_urls = df_urls.loc[keep_indexes].reset_index(drop=True)
            df_urls = df_urls.drop(columns=["_base", "_fmt"])

        df_urls["DocUrl"] = df_urls["DocID"].apply(self._build_doc_url)
        df_urls["DocDate"] = df_urls["DocDate"].apply(self._parse_optional_date)
        return self._filter_by_date_range(df_urls)

    def _parse_optional_date(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return self._parse_date(value)
            except ValueError:
                return self._extract_date_from_string(value)
        return None

    def _extract_date_from_string(self, text: str) -> Optional[datetime]:
        patterns = [
            r"\b(\d{4}-\d{2}-\d{2})\b",
            r"\b(\d{8})\b",
            r"\b(\d{2}/\d{2}/\d{4})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return self._parse_date(match.group(1))
                except ValueError:
                    continue
        return None

    def _filter_by_date_range(self, df: pd.DataFrame) -> pd.DataFrame:
        if "DocDate" in df.columns and df["DocDate"].notna().any():
            return df[
                (df["DocDate"] >= self.start_date) & (df["DocDate"] <= self.end_date)
            ]

        return df[df["FriendlyName"].apply(self._friendly_name_within_range)]

    def _friendly_name_within_range(self, friendly_name: Any) -> bool:
        if not isinstance(friendly_name, str):
            return False
        extracted_date = self._extract_date_from_string(friendly_name)
        return (
            extracted_date is not None
            and self.start_date <= extracted_date <= self.end_date
        )

    def download_document(self, doc_id: Any) -> bytes:
        response = requests.get(self._build_doc_url(doc_id))
        response.raise_for_status()
        return response.content


def get_files_list(url: str) -> pd.DataFrame:
    shuttle = ErcotShuttle("2026-05-01", "2026-06-01", 14836)
    shuttle.fetch_files_list(url)
