"""Show basic system information and optionally monitor CPU usage."""

import argparse
from dataclasses import dataclass
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import platform
import shutil
import socket
import stat
import subprocess
import sys
import urllib.error
import urllib.request

try:
    import psutil
except ImportError:
    psutil = None


@dataclass
class ItemSize:
    name: str
    kind: str
    size: int
    partial: bool = False


def warn(message):
    print(f"Warning: {message}", file=sys.stderr)


def human_size(size):
    """Format byte counts using binary units; sorting must use the raw count."""
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(value) < 1024 or unit == "PiB":
            return f"{value:.2f} {unit}"
        value /= 1024


def directory_size(path, report=warn):
    """Count logical file sizes without following symbolic links."""
    size = 0
    partial = False

    def on_error(error):
        nonlocal partial
        partial = True
        report(f"Cannot read {error.filename or path}: {error}")

    for parent, directories, files in os.walk(path, followlinks=False, onerror=on_error):
        # os.walk already avoids descending into directory symlinks.
        for filename in files:
            item = Path(parent) / filename
            try:
                details = item.lstat()
                if stat.S_ISREG(details.st_mode):
                    size += details.st_size
            except OSError as error:
                on_error(error)
    return size, partial


def largest_items(path, count, report=warn):
    """Return up to count immediate children, including recursive directory sizes."""
    items = []
    try:
        with os.scandir(path) as children:
            for child in children:
                try:
                    if child.is_symlink():
                        continue
                    if child.is_file(follow_symlinks=False):
                        items.append(ItemSize(child.name, "file", child.stat(follow_symlinks=False).st_size))
                    elif child.is_dir(follow_symlinks=False):
                        size, partial = directory_size(child.path, report)
                        items.append(ItemSize(child.name, "directory", size, partial))
                except OSError as error:
                    report(f"Cannot inspect {child.path}: {error}")
    except OSError as error:
        report(f"Cannot list {path}: {error}")
    return sorted(items, key=lambda item: (-item.size, item.name.casefold()))[:count]


def run_json(command, timeout):
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8-sig",
        check=True, timeout=timeout,
    )
    return json.loads(result.stdout or "[]")


def default_routes(system, timeout, report=warn):
    """Read IPv4/IPv6 default routes from structured OS command output."""
    routes = []
    if system == "Windows":
        script = (
            "$ErrorActionPreference='Stop'; "
            "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
            "@(Get-NetRoute | Where-Object { "
            "$_.DestinationPrefix -eq '0.0.0.0/0' -or "
            "$_.DestinationPrefix -eq '::/0' } | "
            "Select-Object DestinationPrefix,NextHop,InterfaceAlias,InterfaceIndex,RouteMetric) "
            "| ConvertTo-Json -Compress"
        )
        commands = [(None, ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script])]
    elif system == "Linux":
        commands = [
            (family, ["ip", "-j", flag, "route", "show", "default"])
            for family, flag in (("IPv4", "-4"), ("IPv6", "-6"))
        ]
    else:
        report(f"Default-route discovery is not implemented for {system}.")
        return routes

    for family, command in commands:
        try:
            rows = run_json(command, timeout)
            if isinstance(rows, dict):
                rows = [rows]
            if rows is None:
                rows = []
            if not isinstance(rows, list):
                raise ValueError("expected a JSON list of routes")
            if system == "Linux":
                # An ECMP default route may contain several next hops.
                expanded = []
                for row in rows:
                    if isinstance(row, dict) and row.get("nexthops"):
                        for hop in row["nexthops"]:
                            expanded.append({**row, **hop})
                    else:
                        expanded.append(row)
                rows = expanded
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("invalid route entry")
                if system == "Windows":
                    prefix = row["DestinationPrefix"]
                    if prefix not in ("0.0.0.0/0", "::/0"):
                        raise ValueError("unexpected destination prefix")
                    route_family = "IPv4" if prefix == "0.0.0.0/0" else "IPv6"
                    gateway = row["NextHop"]
                    interface = row.get("InterfaceAlias") or f"index {row['InterfaceIndex']}"
                    metric = row.get("RouteMetric", "unknown")
                else:
                    route_family = family
                    gateway = row.get("gateway")
                    interface = row.get("dev", "unknown")
                    metric = row.get("metric", "unknown")
                if gateway:
                    address = ipaddress.ip_address(gateway)
                    gateway = "on-link" if address.is_unspecified else str(address)
                else:
                    gateway = "on-link"
                routes.append((route_family, gateway, interface, metric))
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
            report(f"Cannot read {family or 'Windows'} default routes: {error}")
    return routes


def interface_addresses(report=warn):
    """Report all assigned addresses instead of guessing one from the hostname."""
    try:
        addresses = psutil.net_if_addrs()
        statuses = psutil.net_if_stats()
    except (OSError, psutil.Error) as error:
        report(f"Cannot read network interfaces: {error}")
        return []
    rows = []
    for name, assigned in addresses.items():
        status = statuses.get(name)
        state = "up" if status and status.isup else "down" if status else "unknown"
        for address in assigned:
            if address.family in (socket.AF_INET, socket.AF_INET6):
                family = "IPv4" if address.family == socket.AF_INET else "IPv6"
                rows.append((name, state, family, address.address))
    return rows


def public_ip(timeout, report=warn):
    """Query a public HTTPS service with a timeout and validate its response."""
    request = urllib.request.Request(
        "https://ifconfig.me/ip", headers={"User-Agent": "Pyproject-system-info/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            # Bound the response: a valid IPv4/IPv6 address needs far fewer bytes.
            value = response.read(128).decode("utf-8").strip()
        return str(ipaddress.ip_address(value))
    except (OSError, urllib.error.URLError, http.client.HTTPException, ValueError, UnicodeError) as error:
        report(f"Public IP unavailable: {error}")
        return None


def positive_integer(value):
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def positive_seconds(value):
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive number of seconds") from error
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number of seconds")
    return number


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--path", type=Path, default=Path.cwd(), help="directory to inspect (default: current directory)")
    result.add_argument("--top", type=positive_integer, default=5, help="maximum number of largest entries (default: 5)")
    result.add_argument("--interval", type=positive_seconds, default=1.0, help="CPU sampling interval in seconds (default: 1)")
    result.add_argument("--once", action="store_true", help="take one CPU sample, then exit")
    result.add_argument("--skip-public-ip", action="store_true", help="skip the external HTTPS request")
    result.add_argument("--timeout", type=positive_seconds, default=5.0, help="public-IP and route-command timeout in seconds (default: 5)")
    return result


def main(argv=None):
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    if psutil is None:
        argument_parser.error("psutil is required; install it with: python -m pip install -r requirements.txt")
    try:
        path = args.path.expanduser().resolve()
        if not path.is_dir():
            argument_parser.error(f"not an accessible directory: {path}")
    except (OSError, ValueError) as error:
        argument_parser.error(f"cannot access --path: {error}")

    print(f"Operating system: {platform.platform()}")
    print(f"Hostname: {socket.gethostname()}")
    print("Local interface addresses:")
    interfaces = interface_addresses()
    for name, state, family, address in interfaces:
        print(f"  {name} ({state}) {family}: {address}")
    if not interfaces:
        print("  No addresses available.")

    print("Default routes (main table on Linux; metrics are route metrics):")
    routes = default_routes(platform.system(), args.timeout)
    for family, gateway, interface, metric in routes:
        print(f"  {family}: {gateway} via {interface}, metric {metric}")
    if not routes:
        print("  No default routes available.")

    if args.skip_public_ip:
        print("Public IP: skipped")
    else:
        print(f"Public IP: {public_ip(args.timeout) or 'unavailable'}")

    print(f"Filesystem containing: {path}")
    try:
        usage = shutil.disk_usage(path)
        print(f"  Total: {human_size(usage.total)}")
        print(f"  Used:  {human_size(usage.used)}")
        print(f"  Free:  {human_size(usage.free)}")
    except OSError as error:
        warn(f"Disk usage unavailable: {error}")

    print(f"Largest entries in {path} (up to {args.top}):")
    items = largest_items(path, args.top)
    for item in items:
        partial = " [partial: unreadable entries skipped]" if item.partial else ""
        print(f"  {item.kind}: {item.name} — {human_size(item.size)}{partial}")
    if not items:
        print("  No regular files or directories available.")

    if not args.once:
        print("CPU monitoring: press Ctrl+C to stop.")
    try:
        while True:
            print(f"CPU usage ({args.interval:g}s sample): {psutil.cpu_percent(interval=args.interval):.1f}%", flush=True)
            if args.once:
                break
    except KeyboardInterrupt:
        print("\nCPU monitoring stopped.")
    except (OSError, psutil.Error) as error:
        warn(f"CPU usage unavailable: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
