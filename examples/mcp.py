"""
This example shows how to use the Model Context Protocol (MCP) with Hype.
It creates a weather service that provides forecasts and alerts from
the [National Weather Service API](https://api.weather.gov).

Download `uv` to run this example: https://github.com/astral-sh/uv

```
uv run examples/mcp.py
```

Then enter JSON-RPC requests, one per line. For example:

```json
{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "get_forecast", "arguments": {"region": "37.7749,-122.4194"}}, "id": 1}
```
"""

# /// script
# dependencies = [
#   "httpx",
#   "rich",
#   "hype @ git+https://github.com/mattt/hype.git",
# ]
# ///

import asyncio
import json

import httpx
from rich.console import Console

import hype
from hype.mcp import create_mcp_stdio_handler

# Weather API configuration
NWS_API_BASE: str = "https://api.weather.gov"
HEADERS = {"User-Agent": "loopwork-weather/1.0", "Accept": "application/geo+json"}


@hype.up
def get_alerts(region: str) -> list[str] | None:
    """Get weather alerts for the specified region.

    Args:
        region: The region code to get alerts for (e.g. 'CA', 'NY')

    Returns:
        A list of formatted alert strings, or None if no alerts
    """
    with httpx.Client() as client:
        response = client.get(
            f"{NWS_API_BASE}/alerts/active/area/{region}", headers=HEADERS
        )
        response.raise_for_status()
        data = response.json()

        if not data["features"]:
            return None

        alerts = []
        for alert in data["features"]:
            props = alert["properties"]
            alerts.append(
                f"⚠️ {props['event']}\n"
                f"Severity: {props['severity']}\n"
                f"Areas: {props['areaDesc']}\n"
                f"Description: {props['description']}\n"
            )

        return alerts


@hype.up
def get_forecast(region: str) -> list[str]:
    """Get weather forecast for the specified region.

    Args:
        region: The lat,lon coordinates (e.g. '37.7749,-122.4194' for San Francisco)

    Returns:
        A list of formatted forecast periods
    """
    with httpx.Client() as client:
        # First get the forecast grid endpoint
        points_url = f"{NWS_API_BASE}/points/{region}"
        response = client.get(points_url, headers=HEADERS)
        response.raise_for_status()
        points_data = response.json()

        # Get the detailed forecast
        forecast_url = points_data["properties"]["forecast"]
        response = client.get(forecast_url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()

        periods = data["properties"]["periods"][:5]  # Next 5 forecast periods

        return [
            f"🌤️ {period['name']}\n"
            f"Temperature: {period['temperature']}°{period['temperatureUnit']}\n"
            f"Wind: {period['windSpeed']} {period['windDirection']}\n"
            f"{period['shortForecast']}\n"
            for period in periods
        ]


if __name__ == "__main__":
    console = Console()
    functions = [get_alerts, get_forecast]

    # Print available functions
    console.print("\n[bold]Available functions:[/bold]")
    for f in functions:
        console.print(f"\n[cyan]{f.name}[/cyan]")
        if f._wrapped.__doc__:
            console.print(f"  {f._wrapped.__doc__.strip()}")

    console.print("\n[bold]Enter JSON-RPC requests (one per line):[/bold]")
    console.print("Example:")
    example = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "get_forecast",
            "arguments": {"region": "37.7749,-122.4194"},
        },
        "id": 1,
    }
    console.print(json.dumps(example))
    console.print()

    try:
        # Start stdio handler
        handler = create_mcp_stdio_handler(functions)
        asyncio.run(anext(handler))
    except KeyboardInterrupt:
        console.print("\n[bold red]Shutting down...[/bold red]")
