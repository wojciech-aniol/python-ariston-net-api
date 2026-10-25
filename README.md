[![Tests](https://github.com/wojciech-aniol/python-ariston-net-api/actions/workflows/tests.yml/badge.svg)](https://github.com/wojciech-aniol/python-ariston-net-api/actions/workflows/tests.yml)

# python-ariston-net-api
A maintained fork of [fustom/python-ariston-api](https://github.com/fustom/python-ariston-api)
for the [Ariston NET](https://github.com/wojciech-aniol/ariston-remotethermo-home-assistant-v3)
Home Assistant integration. The package is `ariston-net-api` and the module is `ariston_net_api`,
so it can live next to fustom's `ariston` package:
```python3
from ariston_net_api import Ariston
```

A Python module for controlling Ariston devices with cloud polling.
The following devices are currently supported:
- Ariston Alteas One 24
- Ariston Velis Evo
- Ariston Velis Lux
- Ariston Lydos Hybrid
- Ariston Genus One
- Ariston Nuos Split
- Ariston Thision S
- Chaffoteaux INOA S 24

## Installation
Use pip3 to install the latest version of this module.
```
pip3 install ariston-net-api
```

## The easy way (recommended for testing the module)
First, open Python 3 and import ariston module.
```
python3
```
```python3
import ariston_net_api as ariston
```
### Syncronous
Discover devices if you dont know your gateway id. You can skip this step.
```python3
raw_devices = ariston.discover("username", "password")
```
For example the gateway id for your first device.
```python3
raw_devices[0]["gw"]
```
Get your device
```python3
device = ariston.hello("username", "password", "gateway", is_metric, "location")
```
[Go use your device section](#use-your-device)
### Asyncronous
```python3
raw_devices = await ariston.async_discover("username", "password")
device = await ariston.async_hello(
    "username", "password", "gateway", is_metric, "location"
)
```
[Go use your device section](#use-your-device)
## The ariston class way (recommended for integrate the module)
First, open Python 3 and import Ariston class from this module.
```
python3
```
```python3
from ariston_net_api import Ariston
```
Create a new Ariston instance
```python3
ariston = Ariston()
```
Now let's try some functions

### Connect
The cloud requests are asynchronous, so if you call them from a synchronous function or not even from function, you should use asyncio.
```python3
import asyncio
```

Sync
```python3
asyncio.run(ariston.async_connect("username", "password"))
```
Async
```python3
await ariston.async_connect("username", "password")
```
- username: Your ariston cloud username.
- password: Your ariston cloud password.

### Discovery
Use this function to discover devices. You can skip this step if you already know the gateway id.

Sync
```python3
devices = asyncio.run(ariston.async_discover())
```
Async
```python3
devices = await ariston.async_discover()
```

## Say hello
Use this function to create the device object.

Sync
```python3
device = asyncio.run(ariston.async_hello("gateway", is_metric, "location"))
```
Async
```python3
device = await ariston.async_hello("gateway", is_metric, "location")
```
- gateway: You can find the value in the returned discover dictionary name 'gw'
- is_metric: Optional. True or False. True means metric, False means imperial. Only works with Galevo (Alteas One, Genus One, etc) system. Default is True.
- language_tag: Optional. Check https://en.wikipedia.org/wiki/IETF_language_tag Only works with Galevo (Alteas One, Genus One, etc) system. Default is "en-US".

## Use your device
### Get device features
Sync
```python3
device.get_features()
```
Async
```python3
await device.async_get_features()
```
### Get device data
Sync
```python3
device.update_state()
```
Async
```python3
await device.async_update_state()
```
### Get device energy
Sync
```python3
device.update_energy()
```
Async
```python3
await device.async_update_energy()
```
### Get heat produced
The API gives only the electricity a device used. The heat a heat pump produced is only on the
metering page of the web app, so this update logs in to the web app (same login and password)
every time. It works for GALEVO devices whose features have `hasMetering`; other devices send no
request.

Sync
```python3
device.update_metering()
```
Async
```python3
await device.async_update_metering()
```
Then read a total in kWh (`None` when the cloud has no such data):
```python3
from ariston_net_api.const import MeteringPeriod, MeteringSeries, MeteringTab

device.get_metering_total(
    MeteringTab.PRODUCED_ENERGY, MeteringSeries.HEATING, MeteringPeriod.CURRENT_DAY
)
```
- Tabs: `PRODUCED_ENERGY`, `CONSUMED_ELECTRICITY`. Series: `HEATING`, `DHW`, `COOLING`.
- Periods: `CURRENT_DAY` and `PREVIOUS_DAY` (2 h bins), `CURRENT_MONTH` and `PREVIOUS_MONTH`
  (days), `CURRENT_YEAR` and `PREVIOUS_YEAR` (months).
- Poll it rarely, for example once an hour: one update is three HTTP requests (login, its
  redirect, data) and about 72 KB, and the data comes in 2 h bins.
- The values are Ariston's estimates, not a heat meter.
- When `device.is_metering_intensive_logs_active` is true, the web app shows metering as off.
- This is the web app's page backend, not an API for apps, so it may change without notice.
