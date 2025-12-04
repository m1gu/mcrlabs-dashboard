"""Thin client wrapper for QBench API calls."""
from __future__ import annotations

import base64
import hmac
import json
import logging
import time
from hashlib import sha256
from typing import Any, Dict, Iterable, Optional

import httpx

LOGGER = logging.getLogger(__name__)

_DEFAULT_TOKEN_LIFETIME_SECONDS = 3600
_TOKEN_REFRESH_MARGIN_SECONDS = 60.0


class QBenchClient:
    """Handles authenticated requests against QBench."""

    def __init__(
        self,
        *,
        base_url: str,
        client_id: str,
        client_secret: str,
        token_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_base = base_url.rstrip("/")
        if not client_id or not client_secret:
            raise ValueError("QBench client_id and client_secret are required")
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._timeout = timeout
        self._token_expires_at: float | None = None
        self._token_refresh_margin = _TOKEN_REFRESH_MARGIN_SECONDS
        self._client = httpx.Client(
            base_url=self._api_base,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        self._authenticate()

    def __enter__(self) -> "QBenchClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""

        self._client.close()

    def fetch_sample(self, sample_id: str, include_tests: bool = False) -> Optional[Dict[str, Any]]:
        """Retrieve a sample, optionally including its tests."""

        params = {"include": "tests"} if include_tests else None
        response = self._request("GET", f"/qbench/api/v1/sample/{sample_id}", params=params)
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        response.raise_for_status()
        return response.json()

    def fetch_customer(self, customer_id: int | str) -> Optional[Dict[str, Any]]:
        """Retrieve a customer by ID."""

        response = self._request("GET", f"/qbench/api/v1/customer/{customer_id}")
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        response.raise_for_status()
        return response.json()

    def fetch_batch(self, batch_id: int | str, *, include_raw_worksheet_data: bool = False) -> Optional[Dict[str, Any]]:
        """Retrieve a batch by ID."""

        params = {"include_raw_worksheet_data": "true"} if include_raw_worksheet_data else None
        response = self._request("GET", f"/qbench/api/v1/batch/{batch_id}", params=params)
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        response.raise_for_status()
        return response.json()

    def fetch_order(self, order_id: int | str) -> Optional[Dict[str, Any]]:
        """Retrieve an order by ID."""

        response = self._request("GET", f"/qbench/api/v1/order/{order_id}")
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        response.raise_for_status()
        return response.json()

    def update_test_worksheet(
        self,
        test_id: str | int,
        *,
        data: Optional[Dict[str, Any]] = None,
        worksheet_processed: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Update worksheet fields for a given test."""

        if data is None and worksheet_processed is None:
            raise ValueError("At least one of data or worksheet_processed must be provided")

        payload: Dict[str, Any] = {}
        if data:
            payload["data"] = data
        if worksheet_processed is not None:
            payload["worksheet_processed"] = worksheet_processed

        response = self._request(
            "PATCH",
            f"/qbench/api/v1/test/{test_id}/worksheet",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def fetch_test(self, test_id: str | int, include_raw_worksheet_data: bool = False) -> Optional[Dict[str, Any]]:
        """Retrieve a test by ID, optionally with raw worksheet data."""

        params = {"include_raw_worksheet_data": "true"} if include_raw_worksheet_data else None
        response = self._request("GET", f"/qbench/api/v1/test/{test_id}", params=params)
        if response.status_code == httpx.codes.BAD_REQUEST and include_raw_worksheet_data:
            LOGGER.warning(
                "Retrying fetch_test(%s) with legacy parameter include_raw_worsksheet_data due to 400 BAD REQUEST",
                test_id,
            )
            legacy_params = {"include_raw_worsksheet_data": "true"}
            response = self._request("GET", f"/qbench/api/v1/test/{test_id}", params=legacy_params)
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        response.raise_for_status()
        return response.json()

    def _request(
        self,
        method: str,
        url: str,
        *,
        max_retries: int = 5,
        backoff_factor: float = 2.0,
        **kwargs,
    ) -> httpx.Response:
        """Send an HTTP request with retry logic for authentication and rate limiting."""

        attempt = 0
        delay = 1.0
        reauth_attempts = 0
        while True:
            self._ensure_token_valid()
            response = self._client.request(method, url, **kwargs)
            if response.status_code == httpx.codes.UNAUTHORIZED:
                self._authenticate()
                response = self._client.request(method, url, **kwargs)
                reauth_attempts += 1
                if reauth_attempts > max_retries:
                    LOGGER.error("Exceeded max authentication retries for %s %s after 401 UNAUTHORIZED", method, url)
                    return response
                if response.status_code == httpx.codes.UNAUTHORIZED:
                    continue
            elif response.status_code == httpx.codes.BAD_REQUEST:
                retry_due_to_auth = False
                auth_error_reason = None
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                error_desc = (payload or {}).get("error_description", "")
                if (
                    (payload or {}).get("error") == "invalid_request"
                    and "Invalid Authorization header format" in error_desc
                ):
                    retry_due_to_auth = True
                    auth_error_reason = "invalid_request"
                elif (payload or {}).get("error") == "invalid_grant":
                    retry_due_to_auth = True
                    auth_error_reason = "invalid_grant"
                if retry_due_to_auth:
                    if reauth_attempts >= max_retries:
                        LOGGER.error(
                            "Exceeded max authentication retries for %s %s after 400 %s",
                            method,
                            url,
                            auth_error_reason or "authentication_error",
                        )
                        return response
                    LOGGER.warning(
                        "Re-authenticating due to expired/invalid token (400 %s) for %s %s",
                        auth_error_reason or "authentication_error",
                        method,
                        url,
                    )
                    self._authenticate()
                    reauth_attempts += 1
                    time.sleep(1.0)
                    continue
            if response.status_code != httpx.codes.TOO_MANY_REQUESTS:
                return response

            # Handle 429 Too Many Requests
            attempt += 1
            if attempt > max_retries:
                LOGGER.error("Exceeded max retries for %s %s after rate limiting", method, url)
                return response
            retry_after = response.headers.get("Retry-After")
            try:
                sleep_seconds = float(retry_after) if retry_after else delay
            except ValueError:
                sleep_seconds = delay
            LOGGER.warning(
                "Rate limited by QBench (429). Sleeping for %.2f seconds before retrying (attempt %s/%s).",
                sleep_seconds,
                attempt,
                max_retries,
            )
            time.sleep(sleep_seconds)
            delay *= backoff_factor

    def list_customers(self, *, page_num: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """Retrieve a paginated list of customers."""

        params = {"page_num": page_num, "page_size": page_size}
        response = self._request("GET", "/qbench/api/v1/customer", params=params)
        response.raise_for_status()
        return response.json()

    def list_orders(
        self,
        *,
        page_num: int = 1,
        page_size: int = 50,
        customer_ids: Optional[Iterable[int]] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve a paginated list of orders."""

        params: list[tuple[str, Any]] = [
            ("page_num", page_num),
            ("page_size", page_size),
        ]
        if customer_ids:
            for customer_id in customer_ids:
                params.append(("customer_ids", customer_id))
        if sort_by:
            params.append(("sort_by", sort_by))
        if sort_order:
            params.append(("sort_order", sort_order))

        response = self._request("GET", "/qbench/api/v1/order", params=params)
        response.raise_for_status()
        return response.json()

    def list_batches(
        self,
        *,
        page_num: int = 1,
        page_size: int = 50,
        include_raw_worksheet_data: bool = False,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve a paginated list of batches."""

        params: dict[str, Any] = {
            "page_num": page_num,
            "page_size": page_size,
        }
        if include_raw_worksheet_data:
            params["include_raw_worksheet_data"] = "true"
        if sort_by:
            params["sort_by"] = sort_by
        if sort_order:
            params["sort_order"] = sort_order

        response = self._request("GET", "/qbench/api/v1/batch", params=params)
        response.raise_for_status()
        return response.json()

    def list_samples(
        self,
        *,
        page_num: int = 1,
        page_size: int = 50,
        customer_ids: Optional[Iterable[int]] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        order_id_contains: Optional[str] = None,
        sample_id_contains: Optional[str] = None,
        additional_fields_encoded: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve a paginated list of samples."""

        params: list[tuple[str, Any]] = [
            ("page_num", page_num),
            ("page_size", page_size),
        ]
        if customer_ids:
            for customer_id in customer_ids:
                params.append(("customer_ids", customer_id))
        if sort_by:
            params.append(("sort_by", sort_by))
        if sort_order:
            params.append(("sort_order", sort_order))
        if order_id_contains:
            params.append(("order_id_contains", order_id_contains))
        if sample_id_contains:
            params.append(("sample_id_contains", sample_id_contains))
        if additional_fields_encoded:
            params.append(("additional_fields_encoded", additional_fields_encoded))

        response = self._request("GET", "/qbench/api/v1/sample", params=params)
        response.raise_for_status()
        return response.json()

    def list_tests(
        self,
        *,
        page_num: int = 1,
        page_size: int = 50,
        customer_ids: Optional[Iterable[int]] = None,
        assay_ids: Optional[Iterable[int]] = None,
        panel_ids: Optional[Iterable[int]] = None,
        tech_ids: Optional[Iterable[int]] = None,
        test_tags: Optional[Iterable[str]] = None,
        sample_tags: Optional[Iterable[str]] = None,
        order_tags: Optional[Iterable[str]] = None,
        order_ids: Optional[Iterable[int]] = None,
        sample_ids: Optional[Iterable[int]] = None,
        source_ids: Optional[Iterable[int]] = None,
        location_ids: Optional[Iterable[int]] = None,
        statuses: Optional[Iterable[str]] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        include_raw_worksheet_data: bool = False,
        **extra_filters: Any,
    ) -> Dict[str, Any]:
        """Retrieve a paginated list of tests."""

        params: list[tuple[str, Any]] = [
            ("page_num", page_num),
            ("page_size", page_size),
        ]
        for name, values in [
            ("customer_ids", customer_ids),
            ("assay_ids", assay_ids),
            ("panel_ids", panel_ids),
            ("tech_ids", tech_ids),
            ("test_tags", test_tags),
            ("sample_tags", sample_tags),
            ("order_tags", order_tags),
            ("order_ids", order_ids),
            ("sample_ids", sample_ids),
            ("source_ids", source_ids),
            ("location_ids", location_ids),
            ("statuses", statuses),
        ]:
            if values:
                for value in values:
                    params.append((name, value))
        if sort_by:
            params.append(("sort_by", sort_by))
        if sort_order:
            params.append(("sort_order", sort_order))
        if include_raw_worksheet_data:
            params.append(("include_raw_worksheet_data", "true"))
        for key, value in extra_filters.items():
            if value is not None:
                params.append((key, value))

        response = self._request("GET", "/qbench/api/v1/test", params=params)
        if response.status_code == httpx.codes.BAD_REQUEST and include_raw_worksheet_data:
            LOGGER.warning(
                "Retrying list_tests page %s with legacy parameter include_raw_worsksheet_data due to 400 BAD REQUEST",
                page_num,
            )
            legacy_params = [
                ("include_raw_worsksheet_data", value) if key == "include_raw_worksheet_data" else (key, value)
                for key, value in params
            ]
            response = self._request("GET", "/qbench/api/v1/test", params=legacy_params)
        response.raise_for_status()
        return response.json()

    def _authenticate(self) -> None:
        """Obtain an access token using the JWT bearer grant flow."""

        token_endpoint = self._resolve_token_endpoint()
        assertion = _build_jwt_assertion(self._client_id, self._client_secret)
        payload = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }

        response = httpx.post(
            token_endpoint,
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=self._timeout,
        )
        if response.status_code >= 400:
            LOGGER.error(
                "Failed to obtain token from %s: %s", token_endpoint, response.text
            )
        response.raise_for_status()
        token_payload = response.json()
        access_token = token_payload.get("access_token")
        if not access_token:
            raise RuntimeError("QBench token response did not include an access token")
        token_type = token_payload.get("token_type", "Bearer")
        self._client.headers["Authorization"] = f"{token_type} {access_token}"
        self._token_expires_at = self._calculate_token_expiry(token_payload)

    def _resolve_token_endpoint(self) -> str:
        if self._token_url:
            return self._token_url

        base = self._api_base.rstrip("/")
        if base.endswith("/api"):
            host = base[: -len("/api")]
        else:
            host = base
        return f"{host}/oauth/token"

    def _ensure_token_valid(self) -> None:
        """Refresh the token if it is about to expire."""

        if self._token_expires_at is None:
            return
        if time.time() < self._token_expires_at - self._token_refresh_margin:
            return
        LOGGER.info("Refreshing QBench access token due to upcoming expiration")
        self._authenticate()

    def _calculate_token_expiry(self, token_payload: dict[str, Any]) -> float:
        """Determine when the current access token expires."""

        raw_expires_in = token_payload.get("expires_in")
        now = time.time()
        expires_in: float | None = None
        if isinstance(raw_expires_in, (int, float)):
            expires_in = float(raw_expires_in)
        elif isinstance(raw_expires_in, str):
            try:
                expires_in = float(raw_expires_in)
            except ValueError:
                expires_in = None
        if expires_in is None or expires_in <= 0:
            LOGGER.debug(
                "Token response missing usable expires_in; defaulting to %s seconds",
                _DEFAULT_TOKEN_LIFETIME_SECONDS,
            )
            expires_in = _DEFAULT_TOKEN_LIFETIME_SECONDS
        return now + expires_in


def _build_jwt_assertion(client_id: str, client_secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": client_id,
        "iat": now,
        "exp": now + 3600,
    }

    header_segment = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_segment = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = b".".join([header_segment, payload_segment])
    signature = hmac.new(client_secret.encode("utf-8"), signing_input, sha256).digest()
    signature_segment = _base64url_encode(signature)
    return b".".join([header_segment, payload_segment, signature_segment]).decode("ascii")


def _base64url_encode(value: bytes) -> bytes:
    return base64.urlsafe_b64encode(value).rstrip(b"=")
