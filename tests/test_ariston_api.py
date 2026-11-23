"""Tests for the cloud requests of AristonAPI, with a fake cloud."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Self
from unittest.mock import AsyncMock

import pytest

from ariston_net_api import ariston_api
from ariston_net_api.ariston_api import AristonAPI, ConnectionException
from ariston_net_api.const import ARISTON_WEB_COOKIE, ARISTON_WEB_USER_AGENT


@dataclass
class Answer:
    """An answer of the fake cloud."""

    status: int
    body: bytes = b"[]"
    cookies: tuple[str, ...] = ()


class FakeCloud:
    """Gives the next answer to each sync or async request and counts them."""

    def __init__(self) -> None:
        self.answers: list[Answer] = []
        self.calls = 0
        # JSON bodies of the API requests.
        self.bodies: list[Any] = []
        # Requests of the web sessions: url, json, all headers and redirects.
        self.web_requests: list[dict[str, Any]] = []

    def next_answer(self) -> Answer:
        self.calls += 1
        return self.answers.pop(0)

    def request(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        self.bodies.append(kwargs.get("json"))
        return sync_response(self.next_answer())

    def session(self, **kwargs: Any) -> FakeSession:
        return FakeSession(self, kwargs.get("headers", {}))

    def sync_session(self) -> FakeSyncSession:
        return FakeSyncSession(self)


def sync_response(answer: Answer) -> SimpleNamespace:
    """A fake requests.Response."""
    return SimpleNamespace(
        ok=answer.status < 400,
        status_code=answer.status,
        content=answer.body,
        json=lambda: json.loads(answer.body),
    )


class FakeSyncSession:
    """A fake requests.Session with a cookie jar."""

    def __init__(self, cloud: FakeCloud) -> None:
        self.cloud = cloud
        self.headers: dict[str, str] = {}
        self.cookies: set[str] = set()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def post(
        self,
        url: str,
        json: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        allow_redirects: bool = True,
    ) -> SimpleNamespace:
        self.cloud.web_requests.append(
            {
                "url": url,
                "json": json,
                "headers": self.headers | (headers or {}),
                "allow_redirects": allow_redirects,
            }
        )
        answer = self.cloud.next_answer()
        self.cookies.update(answer.cookies)
        return sync_response(answer)


class FakeSession:
    """A fake aiohttp.ClientSession with a cookie jar."""

    def __init__(self, cloud: FakeCloud, headers: dict[str, str]) -> None:
        self.cloud = cloud
        self.headers = headers
        self.cookie_jar: list[SimpleNamespace] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def request(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        # Let other requests start, like a real network wait.
        await asyncio.sleep(0)
        self.cloud.bodies.append(kwargs.get("json"))
        return self.response(self.cloud.next_answer())

    @asynccontextmanager
    async def post(
        self,
        url: str,
        json: Any = None,
        headers: dict[str, str] | None = None,
        allow_redirects: bool = True,
    ) -> AsyncIterator[SimpleNamespace]:
        self.cloud.web_requests.append(
            {
                "url": url,
                "json": json,
                "headers": self.headers | (headers or {}),
                "allow_redirects": allow_redirects,
            }
        )
        await asyncio.sleep(0)
        answer = self.cloud.next_answer()
        self.cookie_jar.extend(SimpleNamespace(key=name) for name in answer.cookies)
        yield self.response(answer)

    @staticmethod
    def response(answer: Answer) -> SimpleNamespace:
        return SimpleNamespace(
            ok=answer.status < 400,
            status=answer.status,
            content=SimpleNamespace(read=AsyncMock(return_value=answer.body)),
            content_length=len(answer.body),
            json=AsyncMock(side_effect=lambda: json.loads(answer.body)),
            read=AsyncMock(return_value=answer.body),
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
    monkeypatch.setattr(ariston_api, "_blocked_until", {})
    monkeypatch.setattr(ariston_api, "_data_item_parts", {})
    monkeypatch.setattr(ariston_api.requests, "request", cloud.request)
    monkeypatch.setattr(ariston_api.requests, "Session", cloud.sync_session)
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


async def test_429_blocks_the_account_not_others(
    cloud: FakeCloud, clock: FakeClock, is_async: bool
) -> None:
    """A new API object of the same account is blocked, another account is not."""
    cloud.answers = [Answer(429), Answer(200), Answer(200)]
    with pytest.raises(ConnectionException):
        await get_devices(AristonAPI("user", "password"), is_async)

    assert await get_devices(AristonAPI("other", "password"), is_async) == []
    assert (
        await get_devices(AristonAPI("user", "password", "http://other/"), is_async)
        == []
    )
    with pytest.raises(ConnectionException):
        await get_devices(AristonAPI("user", "new password"), is_async)
    assert cloud.calls == 3


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


@pytest.mark.parametrize("status", [408, 500, 503])
async def test_server_error_and_timeout_are_retried_once(
    cloud: FakeCloud, clock: FakeClock, is_async: bool, status: int
) -> None:
    """A server error or a request timeout is sent again once after 5 s."""
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


GATEWAY = "GW0000000001"
FEATURES = {"hasMetering": True, "zones": [{"num": 1}]}
METERING_DATA = {
    "oldestMonth": "January 2025",
    "isIntensiveLogsActive": False,
    "asKwhRaw": {"histogramData": []},
}
WEB_LOGIN = Answer(200, b"<html>home</html>", (ARISTON_WEB_COOKIE,))
METERING = Answer(200, json.dumps({"ok": True, "data": METERING_DATA}).encode())


async def get_metering_data(api: AristonAPI, is_async: bool) -> dict[str, Any]:
    """Get the web metering data with the sync or the async path."""
    if is_async:
        return await api.async_get_metering_data(GATEWAY, FEATURES, True)
    return api.get_metering_data(GATEWAY, FEATURES, True)


async def test_metering_logs_in_to_the_web_app(
    cloud: FakeCloud, is_async: bool
) -> None:
    """One cookie session logs in, then asks the data of the gateway."""
    cloud.answers = [WEB_LOGIN, METERING]
    api = AristonAPI("user", "password", "https://cloud.test/api/v2/")

    assert await get_metering_data(api, is_async) == METERING_DATA

    assert cloud.web_requests == [
        {
            "url": "https://cloud.test/R2/Account/Login?returnUrl=%2FR2%2FHome",
            "json": {
                "email": "user",
                "password": "password",
                "rememberMe": False,
                "language": "English_Us",
            },
            "headers": {"User-Agent": ARISTON_WEB_USER_AGENT},
            "allow_redirects": False,
        },
        {
            "url": f"https://cloud.test/R2/PlantMetering/GetData/{GATEWAY}",
            "json": {"features": FEATURES, "hasCooling": True},
            "headers": {
                "User-Agent": ARISTON_WEB_USER_AGENT,
                "X-Requested-With": "XMLHttpRequest",
            },
            "allow_redirects": False,
        },
    ]


@pytest.mark.parametrize(
    ("answers", "args", "calls"),
    [
        ([Answer(200, b"<html>login</html>")], ("Web login failed",), 1),
        (
            [WEB_LOGIN, Answer(200, b"<html><title>LOGIN</title></html>")],
            ("Metering answer is not JSON",),
            2,
        ),
        (
            [WEB_LOGIN, Answer(200, b'{"ok": false, "message": "No access"}')],
            ("Metering failed", "No access"),
            2,
        ),
    ],
    ids=["login without cookie", "login page", "not ok"],
)
async def test_metering_refused(
    cloud: FakeCloud,
    is_async: bool,
    answers: list[Answer],
    args: tuple[str, ...],
    calls: int,
) -> None:
    """A refused login or data request raises."""
    cloud.answers = list(answers)

    with pytest.raises(ConnectionException) as error:
        await get_metering_data(AristonAPI("user", "password"), is_async)

    assert error.value.args == args
    assert cloud.calls == calls


async def test_metering_http_error_is_not_retried(
    cloud: FakeCloud, clock: FakeClock, is_async: bool
) -> None:
    """A web error raises its status at once."""
    cloud.answers = [Answer(500), WEB_LOGIN]

    with pytest.raises(ConnectionException) as error:
        await get_metering_data(AristonAPI("user", "password"), is_async)

    assert error.value.args == (500,)
    assert cloud.calls == 1
    assert clock.sleeps == []


async def test_metering_429_blocks_the_account(
    cloud: FakeCloud, clock: FakeClock, is_async: bool
) -> None:
    """A web 429 blocks API requests too, and the other way round."""
    body = b"Requests are blocked for 66 seconds"
    cloud.answers = [WEB_LOGIN, Answer(429, body), Answer(429)]
    api = AristonAPI("user", "password")

    with pytest.raises(ConnectionException) as error:
        await get_metering_data(api, is_async)
    assert error.value.args == (429, "blocked for 66 seconds")
    with pytest.raises(ConnectionException) as error:
        await get_devices(api, is_async)
    assert error.value.args == (429, "blocked locally for 66 s")
    assert cloud.calls == 2

    clock.now += 66
    with pytest.raises(ConnectionException):
        await get_devices(api, is_async)
    with pytest.raises(ConnectionException) as error:
        await get_metering_data(api, is_async)
    assert error.value.args == (429, "blocked locally for 60 s")
    assert cloud.calls == 3


async def test_metering_429_page_is_not_logged(
    cloud: FakeCloud,
    clock: FakeClock,
    is_async: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A web 429 page can hold personal data, so it is never logged or raised."""
    cloud.answers = [WEB_LOGIN, Answer(429, b"<html>John Doe</html>")]

    with pytest.raises(ConnectionException) as error:
        await get_metering_data(AristonAPI("user", "password"), is_async)

    assert error.value.args == (429, "")
    assert "John Doe" not in caplog.text
    clock.now += 59
    with pytest.raises(ConnectionException) as error:
        await get_devices(AristonAPI("user", "password"), is_async)
    assert error.value.args == (429, "blocked locally for 1 s")


PROPERTY_FEATURES = {"zones": [{"num": 1}]}
PROPERTY_ITEMS = AristonAPI.get_items(PROPERTY_FEATURES)


def items_answer(items: list[dict[str, Any]]) -> Answer:
    """A data items answer with a value for each asked item."""
    answer = {"items": [{"id": item["id"], "value": 1} for item in items]}
    return Answer(200, json.dumps(answer).encode())


def item_ids(properties: dict[str, Any]) -> list[str]:
    return [item["id"] for item in properties["items"]]


def asked_sizes(cloud: FakeCloud) -> list[int]:
    return [len(body["items"]) for body in cloud.bodies]


async def get_properties(api: AristonAPI, is_async: bool) -> dict[str, Any]:
    """Read the data items of a GALEVO gateway."""
    if is_async:
        return await api.async_get_properties(GATEWAY, PROPERTY_FEATURES, "en-US", "si")
    return api.get_properties(GATEWAY, PROPERTY_FEATURES, "en-US", "si")


def split_items(count: int) -> list[list[dict[str, Any]]]:
    return ariston_api._split(PROPERTY_ITEMS, count)


async def test_properties_without_error_send_one_request(
    cloud: FakeCloud, clock: FakeClock, is_async: bool
) -> None:
    """A read without an error sends only the full request."""
    cloud.answers = [items_answer(PROPERTY_ITEMS)]

    properties = await get_properties(AristonAPI("user", "password"), is_async)

    assert cloud.calls == 1
    assert asked_sizes(cloud) == [len(PROPERTY_ITEMS)]
    assert item_ids(properties) == [item["id"] for item in PROPERTY_ITEMS]


async def test_properties_500_asks_in_halves(
    cloud: FakeCloud, clock: FakeClock, is_async: bool
) -> None:
    """After a 500 the halves are asked and merged, and kept for later reads."""
    first, second = split_items(2)
    cloud.answers = [Answer(500), Answer(500), items_answer(first)]
    cloud.answers.append(items_answer(second))
    api = AristonAPI("user", "password")

    properties = await get_properties(api, is_async)

    assert item_ids(properties) == [item["id"] for item in PROPERTY_ITEMS]
    assert asked_sizes(cloud)[2:] == [len(first), len(second)]
    assert cloud.calls == 4

    cloud.bodies.clear()
    cloud.answers = [items_answer(first), items_answer(second)]
    clock.now += 3599

    await get_properties(api, is_async)

    assert asked_sizes(cloud) == [len(first), len(second)]

    cloud.bodies.clear()
    cloud.answers = [items_answer(PROPERTY_ITEMS)]
    clock.now += 1

    await get_properties(api, is_async)

    assert asked_sizes(cloud) == [len(PROPERTY_ITEMS)]


async def test_properties_part_500_is_split_again(
    cloud: FakeCloud, clock: FakeClock, is_async: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed half is split again, within 4 part requests and no retries."""
    first, second = split_items(2)
    second_a, second_b = ariston_api._split(second, 2)
    cloud.answers = [Answer(500), Answer(500), items_answer(first), Answer(500)]
    cloud.answers += [items_answer(second_a), Answer(500), Answer(200)]

    properties = await get_properties(AristonAPI("user", "password"), is_async)

    assert item_ids(properties) == [item["id"] for item in first + second_a]
    assert asked_sizes(cloud)[2:] == [len(first), len(second)] + [
        len(second_a),
        len(second_b),
    ]
    assert cloud.calls == 6
    assert clock.sleeps == [5]
    assert f"{len(second_b)} of {len(PROPERTY_ITEMS)} data items failed" in caplog.text
    assert ariston_api._data_item_parts[(ariston_api.ARISTON_API_URL, GATEWAY)][0] == 4


async def test_properties_all_parts_fail(
    cloud: FakeCloud, clock: FakeClock, is_async: bool
) -> None:
    """When no part answers, the first error is raised and nothing is kept."""
    cloud.answers = [Answer(500)] * 6 + [items_answer(PROPERTY_ITEMS)]
    api = AristonAPI("user", "password")

    with pytest.raises(ConnectionException) as error:
        await get_properties(api, is_async)

    assert error.value.args == (500,)
    assert cloud.calls == 6
    assert ariston_api._data_item_parts == {}

    await get_properties(api, is_async)

    assert asked_sizes(cloud)[-1] == len(PROPERTY_ITEMS)


@pytest.mark.parametrize("status", [401, 403, 502])
async def test_properties_other_error_is_not_split(
    cloud: FakeCloud, clock: FakeClock, is_async: bool, status: int
) -> None:
    """Only a 500 starts the part requests."""
    cloud.answers = [Answer(status)] * 2 + [Answer(200)]

    with pytest.raises(ConnectionException) as error:
        await get_properties(AristonAPI("user", "password"), is_async)

    assert error.value.args == (status,)
    assert cloud.calls == (1 if status < 500 else 2)


@pytest.mark.parametrize("status", [401, 429])
async def test_properties_part_refused_raises(
    cloud: FakeCloud, clock: FakeClock, is_async: bool, status: int
) -> None:
    """A part answered with 4xx raises at once."""
    cloud.answers = [Answer(500), Answer(500), Answer(status), Answer(200)]

    with pytest.raises(ConnectionException) as error:
        await get_properties(AristonAPI("user", "password"), is_async)

    assert error.value.args[0] == status
    assert cloud.calls == 3
