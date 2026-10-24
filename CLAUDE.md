# python-ariston-net-api

Python library for the Ariston NET cloud: package `ariston-net-api`, module `ariston_net_api`.
A maintained fork of fustom/python-ariston-api 0.19.9 for the Ariston NET Home Assistant
integration (`wojciech-aniol/ariston-remotethermo-home-assistant-v3`). Code in
`ariston_net_api/`, tests in `tests/`.

## Commands

- Set up once: `uv venv --python 3.14 .venv && uv pip install --python .venv/bin/python -e ".[test]"`
- Tests: `.venv/bin/python -m pytest -q`
- Lint and format: `.venv/bin/ruff check --fix . && .venv/bin/ruff format .`

Tests and lint pass before every commit. CI (`tests.yml`) runs both, pytest on Python 3.13 and 3.14.

## Map

- `__init__.py`: the `Ariston` class and `_get_device`, which picks the device class from the
  cloud device data (`sys`, `wheType`).
- `ariston_api.py`: HTTP requests and `ConnectionException`.
- Devices: `galevo_device.py`, `bsb_device.py`, `velis_*`, `evo_*`, `lux*`, `lydos*`,
  `nuos_split_device.py`. `const.py`: enums and cloud keys.
- `tests/conftest.py`: `api`, a fake API (`MagicMock` with `AsyncMock` methods). Tests give it
  cloud data, then check the device and the calls it made.

## Rules

- Keep the public names (classes, methods, properties, enums, constants): the integration
  imports them. A rename or removal needs the user's yes.
- Every fix comes with a test that fails without it.
- The version lives only in `pyproject.toml`.
- A release is a GitHub release with a tag without `v` (`0.20.1`), made with
  `gh release create`, only after the user's yes. It runs `publish.yml`, which uploads to PyPI
  by trusted publishing. Never tag by hand. After a release the integration bumps its pin.
- `origin` is this repo, `upstream` is fustom: never push there (its push URL is `DISABLED`).
- Code, comments, commits and README are in English. Commit subject: imperative, no prefix,
  under 60 characters; the body says why. `.git-blame-ignore-revs` lists format-only commits.
