# Pyproject

A Python command-line learning project for inspecting basic system information, disk usage, directory sizes, and CPU activity.

## Current status

This repository contains the original standalone script, [main.py](main.py). It is a prototype with known portability and error-handling limitations, not a complete cross-platform monitoring application.

The source passes a Python syntax check. Runtime behavior has not been validated as part of this documentation review.

## What the script does

- Prints operating-system details and a hostname-resolved local IPv4 address.
- Attempts to display the default gateway using OS-specific shell commands.
- Requests the public IP address from `https://ifconfig.me/`; the result is currently stored but not printed.
- Reports total, used, and free space for the hard-coded `C:` drive.
- Walks entries in the current working directory, calculates directory sizes, and attempts to print the five largest entries.
- Prints CPU usage repeatedly, with a 10-second sampling interval in the monitoring loop.

The script uses the directory from which you launch it as the scan location.

## Requirements

- Python 3.
- The third-party `psutil` package.
- A Windows environment for the current hard-coded disk path.
- Internet access for the public-IP request.
- The OS networking commands referenced in the script (`ipconfig` on Windows; `ip`, `grep`, and `awk` in the Linux branch).

There is currently no dependency manifest or declared minimum Python version.

## Usage

Install the dependency, then launch the script:

```bash
python -m pip install psutil
python main.py
```

Stop CPU monitoring with **Ctrl+C**. There are no command-line flags or built-in help options.

## Known limitations

- **Linux support is incomplete:** the disk path is fixed to `C:`, and the gateway filter looks for `default gateway`, which does not match the usual `ip route` output.
- **Small directories can cause a crash:** the display loop always indexes five results, even when fewer entries exist.
- **File and directory handling are mixed:** ordinary files are passed to a directory-walking function and can appear with a zero size.
- **Gateway detection is fragile:** the Windows branch depends on English output and matching the first two octets of the local IP.
- **Network failures are unhandled:** the public-IP request has no explicit timeout or exception handling; hostname resolution can also fail or select an unexpected address.
- **Filesystem errors are unhandled:** permissions or files changing during traversal can interrupt the script.
- **Output needs cleanup:** all three disk measurements use the same label, and the values are calculated in GiB while labeled GB.
- The first CPU sample is taken without a sampling interval; subsequent samples use 10 seconds.
- IPv4 octets are converted with `eval()`, although ordinary numeric parsing would be sufficient.

## Potential improvements

- Separate collection, formatting, and the monitoring loop into functions.
- Add OS-aware disk selection and reliable interface/default-route discovery.
- Add options for scan path, result count, CPU interval, and one-shot output.
- Validate addresses with `ipaddress` and remove unnecessary `eval()`.
- Handle files and directories separately, sort numeric sizes directly, and safely slice the top results.
- Add timeouts, readable error messages, dependency metadata, and focused tests.

These are proposed improvements, not implemented features.
