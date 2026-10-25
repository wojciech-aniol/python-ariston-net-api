"""Tests for the cloud requests of AristonAPI, with a fake cloud."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Self
from unittest.mock import AsyncMock

import pytest

from ariston_net_api import ariston_api
from ariston_net_api.ariston_api import AristonAPI, ConnectionException


@dataclass
class Answer:
    """An answer of the fake cloud."""

    status: int
    body: bytes = b"[]"


class FakeCloud:
    """Gives the next answer to each sync or async request and counts them."""

    def __init__(self) -> None:
        self.answers: list[Answer] = []
        self.calls = 0

    def next_answer(self) -> Answer:
        self.calls += 1
        return self.answers.pop(0)

    def request(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        answer = self.next_answer()
        return SimpleNamespace(
            ok=answer.status < 400,
            status_code=answer.status,
            content=answer.body,
            json=lambda: json.loads(answer.body),
        )

    def session(self, **kwargs: Any) -> FakeSession:
        return FakeSession(self)


class FakeSession:
    """A fake aiohttp.ClientSession."""

    def __init__(self, cloud: FakeCloud) -> None:
        self.cloud = cloud

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def request(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        # Let other requests start, like a real network wait.
        await asyncio.sleep(0)
        answer = self.cloud.next_answer()
        return SimpleNamespace(
            ok=answer.status < 400,
            status=answer.status,
            content=SimpleNamespace(read=AsyncMock(return_value=answer.body)),
            content_length=len(answer.body),
            json=AsyncMock(side_effect=lambda: json.loads(answer.body)),
        )


class FakeClock:
    """A monotonic clock that only moves when a test or a sleep moves it."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    async def async_sleep(self, seconds: float) -> None:
        self.sleep(seconds)


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def is_async(request: pytest.FixtureRequest) -> bool:
    """Run the test with the sync and the async requests."""
    return request.param


@pytest.fixture
def cloud(monkeypatch: pytest.MonkeyPatch) -> FakeCloud:
    """Replace the network of both request paths with a fake cloud."""
    cloud = FakeCloud()
    monkeypatch.setattr(ariston_api.requests, "request", cloud.request)
    monkeypatch.setattr(ariston_api.aiohttp, "ClientSession", cloud.session)
    return cloud


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """Replace the time and the sleeps of the API module with a fake clock."""
    clock = FakeClock()
    monkeypatch.setattr(
        ariston_api,
        "time",
        SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep),
    )
    monkeypatch.setattr(
        ariston_api, "asyncio", SimpleNamespace(sleep=clock.async_sleep)
    )
    return clock


async def get_devices(api: AristonAPI, is_async: bool) -> list[Any]:
    """Send one GET request with the sync or the async path."""
    if is_async:
        return await api.async_get_devices()
    return api.get_devices()


@pytest.mark.parametrize(
    ("body", "seconds"),
    [
        (b"Requests are blocked for 66 seconds", 66),
        (b'{"message": "REQUESTS ARE BLOCKED FOR 1 SECOND"}', 1),
        (b"Too many requests", 60),
        (b"", 60),
    ],
)
async def test_429_blocks_requests_for_the_time_in_the_answer(
    cloud: FakeCloud, clock: FakeClock, is_async: bool, body: bytes, seconds: int
) -> None:
    """After a 429 no request goes out until the block ends, 60 s by default."""
    cloud.answers = [Answer(429, body), Answer(200)]
    api = AristonAPI("user", "password")

    with pytest.raises(ConnectionException) as error:
        await get_devices(api, is_async)
    assert error.value.args == (429, body.decode())

    clock.now += seconds - 0.5
    with pytest.raises(ConnectionException) as error:
        await get_devices(api, is_async)
    assert error.value.args == (429, "blocked locally for 1 s")
    assert cloud.calls == 1

    clock.now += 0.5
    assert await get_devices(api, is_async) == []
    assert cloud.calls == 2


async def test_429_blocks_only_its_own_api_object(
    cloud: FakeCloud, clock: FakeClock, is_async: bool
) -> None:
    """Another account is not blocked."""
    cloud.answers = [Answer(429), Answer(200), Answer(200)]
    blocked = AristonAPI("user", "password")
    with pytest.raises(ConnectionException):
        await get_devices(blocked, is_async)

    assert await get_devices(AristonAPI("other", "password"), is_async) == []
    with pytest.raises(ConnectionException):
        await get_devices(blocked, is_async)
    assert cloud.calls == 2


async def test_later_429_does_not_shorten_the_block(
    cloud: FakeCloud, clock: FakeClock
) -> None:
    """Two requests at once: the second, shorter 429 keeps the first block."""
    cloud.answers = [Answer(429, b"Blocked for 300 seconds"), Answer(429)]
    api = AristonAPI("user", "password")
    await asyncio.gather(
        api.async_get_devices(), api.async_get_devices(), return_exceptions=True
    )

    clock.now += 100
    with pytest.raises(ConnectionException) as error:
        await api.async_get_devices()
    assert error.value.args == (429, "blocked locally for 200 s")
    assert cloud.calls == 2


async def test_unknown_429_answer_is_logged(
    cloud: FakeCloud, clock: FakeClock, is_async: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """An answer without the block time is logged, to learn its text."""
    cloud.answers = [Answer(429, b"Too many requests")]

    with pytest.raises(ConnectionException):
        await get_devices(AristonAPI("user", "password"), is_async)

    assert caplog.record_tuples == [
        (
            "ariston_net_api.ariston_api",
            logging.WARNING,
            "Unknown 429 answer, blocking requests for 60 s: Too many requests",
        )
    ]


async def test_login_inside_the_block_is_not_sent(
    cloud: FakeCloud, clock: FakeClock, is_async: bool
) -> None:
    """A login raises the local 429 as its cause, which callers read."""
    cloud.answers = [Answer(429), Answer(200, b'{"token": "x"}')]
    api = AristonAPI("user", "password")
    with pytest.raises(ConnectionException):
        await get_devices(api, is_async)

    with pytest.raises(ConnectionException) as error:
        if is_async:
            await api.async_connect()
        else:
            api.connect()

    assert error.value.args == ()
    assert error.value.__cause__.args[0] == 429
    assert cloud.calls == 1


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_4xx_is_not_retried(
    cloud: FakeCloud, clock: FakeClock, is_async: bool, status: int
) -> None:
    """A refused request raises at once, without a second request."""
    cloud.answers = [Answer(status), Answer(200)]

    with pytest.raises(ConnectionException) as error:
        await get_devices(AristonAPI("user", "password"), is_async)

    assert error.value.args == (status,)
    assert cloud.calls == 1
    assert clock.sleeps == []


@pytest.mark.parametrize("status", [500, 503])
async def test_5xx_is_retried_once(
    cloud: FakeCloud, clock: FakeClock, is_async: bool, status: int
) -> None:
    """A server error is sent again once after 5 s."""
    cloud.answers = [Answer(status), Answer(status), Answer(200)]

    with pytest.raises(ConnectionException) as error:
        await get_devices(AristonAPI("user", "password"), is_async)

    assert error.value.args == (status,)
    assert cloud.calls == 2
    assert clock.sleeps == [5]


async def test_5xx_retry_returns_the_second_answer(
    cloud: FakeCloud, clock: FakeClock, is_async: bool
) -> None:
    """A retry that works gives its answer."""
    cloud.answers = [Answer(500), Answer(200, b'[{"gw": "GW1"}]')]

    devices = await get_devices(AristonAPI("user", "password"), is_async)

    assert devices == [{"gw": "GW1"}]
    assert cloud.calls == 2
    assert clock.sleeps == [5]
