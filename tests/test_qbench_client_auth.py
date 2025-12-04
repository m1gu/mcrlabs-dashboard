from collections import deque

import httpx

from downloader_qbench_data.clients.qbench import QBenchClient


class TimeController:
    """Utility to control time.time() values during tests."""

    def __init__(self, start: float = 0.0) -> None:
        self.current = start

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


def _install_common_patches(monkeypatch, controller: TimeController, token_sequence: list[dict], api_handler):
    """Patch httpx client/token calls and time helpers for deterministic tests."""

    from downloader_qbench_data.clients import qbench as qbench_module

    monkeypatch.setattr(qbench_module.time, "time", controller)
    monkeypatch.setattr(qbench_module.time, "sleep", lambda *_: None)

    token_calls: list[dict] = []

    def fake_post(url, data=None, headers=None, timeout=None):
        call_index = len(token_calls)
        payload = token_sequence[call_index] if call_index < len(token_sequence) else token_sequence[-1]
        token_calls.append({"url": url, "data": data})
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json=payload,
        )

    monkeypatch.setattr(qbench_module.httpx, "post", fake_post)

    transport = httpx.MockTransport(api_handler)
    real_client_class = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs.setdefault("transport", transport)
        return real_client_class(*args, **kwargs)

    monkeypatch.setattr(qbench_module.httpx, "Client", client_factory)

    return token_calls


def test_proactive_token_refresh(monkeypatch):
    controller = TimeController(1000.0)
    api_requests: list[httpx.Request] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        api_requests.append(request)
        return httpx.Response(200, request=request, json={"data": [], "total_pages": 1})

    token_payloads = [
        {"access_token": "token-1", "token_type": "Bearer", "expires_in": 120},
        {"access_token": "token-2", "token_type": "Bearer", "expires_in": 120},
    ]
    token_calls = _install_common_patches(monkeypatch, controller, token_payloads, api_handler)

    with QBenchClient(
        base_url="https://example.com",
        client_id="client",
        client_secret="secret",
    ) as client:
        client.list_tests(page_num=1)
        assert len(token_calls) == 1
        assert api_requests[-1].headers["authorization"] == "Bearer token-1"

        controller.advance(70.0)  # Move past the refresh margin (60s) with expires_in=120s
        client.list_tests(page_num=1)

    assert len(token_calls) == 2
    assert len(api_requests) == 2
    assert api_requests[-1].headers["authorization"] == "Bearer token-2"


def test_handles_invalid_grant_retry(monkeypatch):
    controller = TimeController(2000.0)
    api_requests: list[httpx.Request] = []
    response_queue = deque(
        [
        httpx.Response(
            400,
            request=httpx.Request("GET", "https://example.com/qbench/api/v1/test"),
            json={
                "error": "invalid_grant",
                "error_description": "Access token has expired.",
            },
        ),
        httpx.Response(
            200,
            request=httpx.Request("GET", "https://example.com/qbench/api/v1/test"),
            json={"data": [], "total_pages": 1},
        ),
        ]
    )
    final_response = response_queue[-1]

    def api_handler(request: httpx.Request) -> httpx.Response:
        api_requests.append(request)
        # Return the next response, repeating the last one if exhausted
        response = response_queue.popleft() if response_queue else final_response
        # Attach the incoming request so httpx doesn't complain
        return httpx.Response(
            status_code=response.status_code,
            json=response.json(),
            request=request,
            headers=response.headers,
        )

    token_payloads = [
        {"access_token": "token-1", "token_type": "Bearer", "expires_in": 3600},
        {"access_token": "token-2", "token_type": "Bearer", "expires_in": 3600},
    ]
    token_calls = _install_common_patches(monkeypatch, controller, token_payloads, api_handler)

    with QBenchClient(
        base_url="https://example.com",
        client_id="client",
        client_secret="secret",
    ) as client:
        result = client.list_tests(page_num=1)

    assert result == {"data": [], "total_pages": 1}
    assert len(api_requests) == 2  # initial attempt + retry after refresh
    assert len(token_calls) == 2  # initial authentication + refresh due to invalid_grant
