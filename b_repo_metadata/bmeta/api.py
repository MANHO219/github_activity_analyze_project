"""GitHub REST 最小客户端：串行请求、有限重试、配额与错误分类。

B 阶段只需要 ``GET /repos/{owner}/{repo}``，因此这里不引入第三方 HTTP 库，
用标准库 ``urllib`` 实现，便于在组员机器上零依赖运行。

设计要点
--------
- token 只从环境变量读取（默认 ``GITHUB_TOKEN``），绝不写日志、不写进运行产物；
- 每个响应的 HTTP 状态、配额头、最终 URL 和耗时都保留，供失败分类与复核；
- 403/429 区分“匿名或 token 配额用尽”（抛 ``RateLimitExhausted``，整批暂停，
  剩余仓库记为 pending）与“次级限流”（按 ``Retry-After`` 等待后重试）；
- 5xx、网络错误、超时才重试；404/410/451 不重试，直接记录。
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

DEFAULT_BASE_URL = "https://api.github.com"
DEFAULT_USER_AGENT = "cs5488-b-repo-metadata/0.1"
DEFAULT_ACCEPT = "application/vnd.github+json"
RATE_LIMIT_HEADERS = (
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-used",
    "x-ratelimit-reset",
)

# transport(url, headers, timeout) -> (status, headers, body_bytes)
Transport = Callable[[str, Mapping[str, str], float], tuple[int, Mapping[str, str], bytes]]


class ApiCallError(RuntimeError):
    """重试后仍失败的调用（网络、5xx、无效 JSON 等）。"""


class RateLimitExhausted(RuntimeError):
    """配额已用尽：调用方应停止本批、保留已完成结果、稍后续跑。"""

    def __init__(self, reset_epoch: int | None, remaining: int | None, message: str) -> None:
        super().__init__(message)
        self.reset_epoch = reset_epoch
        self.remaining = remaining


@dataclass
class ApiResponse:
    http_status: int | None
    body: Any | None
    raw: bytes
    headers: dict[str, str]
    final_url: str
    attempts: int
    elapsed_ms: int
    error: str | None = None
    transport_error: bool = False

    @property
    def ok(self) -> bool:
        return self.http_status == 200 and self.body is not None and self.error is None

    @property
    def status_family(self) -> str:
        if self.transport_error:
            return "network_error"
        if self.http_status is None:
            return "unknown"
        if self.http_status == 200:
            return "ok" if self.error is None else "invalid_json"
        if self.http_status in (404, 410, 451):
            return "not_found"
        if self.http_status in (401, 403):
            return "forbidden"
        if self.http_status == 429:
            return "rate_limited"
        if 500 <= self.http_status < 600:
            return "server_error"
        return f"http_{self.http_status}"

    def to_log(self) -> dict[str, Any]:
        return {
            "http_status": self.http_status,
            "status_family": self.status_family,
            "attempts": self.attempts,
            "elapsed_ms": self.elapsed_ms,
            "final_url": self.final_url,
            "error": self.error,
            "rate_limit": {key: self.headers.get(key) for key in RATE_LIMIT_HEADERS},
        }


def _select_headers(headers: Mapping[str, str]) -> dict[str, str]:
    lowered = {str(key).lower(): str(value) for key, value in headers.items()}
    picked = {key: lowered[key] for key in RATE_LIMIT_HEADERS if key in lowered}
    for key in ("etag", "location", "retry-after", "x-github-request-id"):
        if key in lowered:
            picked[key] = lowered[key]
    return picked


def urllib_transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, Mapping[str, str], bytes]:
    """默认传输层：标准库请求，自动跟随 3xx 重定向。"""
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:  # 4xx/5xx 也带响应体与配额头
        body = error.read()
        return error.code, error.headers, body


class GitHubRepoClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        token_env: str = "GITHUB_TOKEN",
        base_url: str = DEFAULT_BASE_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        accept: str = DEFAULT_ACCEPT,
        timeout: float = 30.0,
        max_attempts: int = 3,
        backoff_seconds: tuple[float, ...] = (1.0, 2.0, 4.0),
        request_interval_seconds: float = 0.0,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.token = token if token is not None else os.environ.get(token_env, "")
        self.token_env = token_env
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.accept = accept
        self.timeout = timeout
        self.max_attempts = max(1, int(max_attempts))
        self.backoff_seconds = tuple(backoff_seconds) or (1.0,)
        self.request_interval_seconds = max(0.0, float(request_interval_seconds))
        self._transport = transport or urllib_transport
        self._sleep = sleep
        self._now = now
        self._last_request_at = 0.0
        self.calls = 0
        self.last_response: ApiResponse | None = None

    # -- 对外接口 -------------------------------------------------------
    @property
    def has_token(self) -> bool:
        return bool(self.token)

    def repo_url(self, full_name: str) -> str:
        owner, _, repo = (full_name or "").partition("/")
        if not owner or not repo:
            raise ValueError(f"repo name must be 'owner/repo', got {full_name!r}")
        return f"{self.base_url}/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(repo, safe='')}"

    def get_repo(self, full_name: str) -> ApiResponse:
        return self.request(self.repo_url(full_name))

    def request(self, url: str) -> ApiResponse:
        headers = {
            "Accept": self.accept,
            "User-Agent": self.user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        attempts = 0
        started = self._now()
        last_error: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            attempts = attempt
            self._throttle()
            try:
                status, raw_headers, body = self._transport(url, headers, self.timeout)
            except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as error:
                last_error = f"{type(error).__name__}: {error}"
                if attempt < self.max_attempts:
                    self._backoff(attempt)
                    continue
                self.calls += 1
                response = ApiResponse(
                    http_status=None,
                    body=None,
                    raw=b"",
                    headers={},
                    final_url=url,
                    attempts=attempts,
                    elapsed_ms=self._elapsed_ms(started),
                    error=last_error,
                    transport_error=True,
                )
                self.last_response = response
                return response

            self.calls += 1
            picked_headers = _select_headers(raw_headers)
            reset_epoch = _as_int(picked_headers.get("x-ratelimit-reset"))
            remaining = _as_int(picked_headers.get("x-ratelimit-remaining"))

            if status == 200:
                parsed, error_text = _parse_json(body)
                response = ApiResponse(
                    http_status=status,
                    body=parsed,
                    raw=body,
                    headers=picked_headers,
                    final_url=url,
                    attempts=attempts,
                    elapsed_ms=self._elapsed_ms(started),
                    error=error_text,
                )
                self.last_response = response
                return response

            if status in (403, 429):
                if remaining == 0:
                    message = (
                        "GitHub API 配额已用尽（HTTP %d, remaining=0）。"
                        "已完成的结果已写盘，稍后用同一命令续跑即可。" % status
                    )
                    raise RateLimitExhausted(reset_epoch, remaining, message)
                retry_after = _as_int(picked_headers.get("retry-after"))
                if attempt < self.max_attempts:
                    self._sleep(float(retry_after) if retry_after else self._backoff_value(attempt))
                    continue

            if 500 <= status < 600 and attempt < self.max_attempts:
                self._backoff(attempt)
                continue

            parsed, error_text = _parse_json(body)
            response = ApiResponse(
                http_status=status,
                body=parsed,
                raw=body,
                headers=picked_headers,
                final_url=url,
                attempts=attempts,
                elapsed_ms=self._elapsed_ms(started),
                error=error_text or last_error,
            )
            self.last_response = response
            return response

        # 理论上不可达：循环内每个分支都 return/raise。
        raise ApiCallError(f"request loop ended unexpectedly for {url}")

    # -- 内部工具 -------------------------------------------------------
    def _throttle(self) -> None:
        if self.request_interval_seconds <= 0:
            return
        wait = self.request_interval_seconds - (self._now() - self._last_request_at)
        if wait > 0:
            self._sleep(wait)
        self._last_request_at = self._now()

    def _backoff_value(self, attempt: int) -> float:
        index = min(attempt - 1, len(self.backoff_seconds) - 1)
        return float(self.backoff_seconds[index])

    def _backoff(self, attempt: int) -> None:
        self._sleep(self._backoff_value(attempt))

    def _elapsed_ms(self, started: float) -> int:
        return int(round((self._now() - started) * 1000))


def _parse_json(raw: bytes) -> tuple[Any | None, str | None]:
    if not raw:
        return None, "empty response body"
    try:
        return json.loads(raw.decode("utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, f"{type(error).__name__}: {error}"


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
