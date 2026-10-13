# Pyproject

A small Python command-line tool for inspecting system information, local network interfaces, default routes, disk space, directory sizes, and CPU activity.

## Status

**Working prototype.** The original script has been reorganized into functions with validated command-line options, error handling, and offline regression tests. It remains a local diagnostic and learning project, not a production monitoring agent.

The automated checks cover filesystem behavior and simulated Windows/Linux responses. They do **not** establish end-to-end compatibility with every operating system, VPN, or network configuration. No external network requests were made during this validation.

## Features

- Operating-system and hostname information.
- IPv4/IPv6 addresses for each local interface, including its up/down state.
- IPv4/IPv6 default routes and their interfaces, including multiple default routes.
  - Windows: PowerShell `Get-NetRoute` serialized to JSON, independent of the language used by `ipconfig`.
  - Linux: `ip -j -4/-6 route show default`, including multiple next hops.
- Public IP lookup through `https://ifconfig.me/ip`, with response validation and a configurable timeout. Use `--skip-public-ip` to disable the external request.
- Distinct total, used, and free disk-space labels for the filesystem containing the selected directory.
- Up to the requested number of largest immediate files/directories, sorted by their byte counts. Directory sizes include nested regular files.
- Meaningful CPU samples at a configurable interval, either once or continuously.

Unavailable network information, route-command failures, and inaccessible files produce warnings instead of stopping the remaining checks. Partially readable directory sizes are explicitly marked. Units use **KiB/MiB/GiB** rather than labeling binary values as decimal GB.

## Requirements

- Python **3.9 or newer**.
- `psutil`, declared in [requirements.txt](requirements.txt).
- For default routes: Windows with PowerShell and the `Get-NetRoute` cmdlet, or Linux with `iproute2` and JSON-capable `ip`.
- Internet access only if the public-IP lookup is enabled.

Other operating systems can run the generic checks where `psutil` supports them, but default-route discovery is currently implemented only for Windows and Linux. Missing route commands generate a warning.

## Installation

From the repository directory:

```bash
python -m venv .venv
```

Activate the environment using your platform's command:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux
source .venv/bin/activate
```

Then install the dependency:

```bash
python -m pip install -r requirements.txt
```

## Usage

Show help:

```bash
python main.py --help
```

Inspect the current directory and take one CPU sample without an external IP lookup:

```bash
python main.py --once --skip-public-ip
```

Inspect a selected directory and show its ten largest entries:

```bash
python main.py --path "/home/martin/Documents" --top 10 --once
```

```powershell
python main.py --path "C:\Users\Martin\Documents" --top 10 --once
```

Print the system snapshot, then sample CPU usage every five seconds until **Ctrl+C**:

```bash
python main.py --interval 5 --timeout 3
```

| Option | Behavior | Default |
| --- | --- | --- |
| `-h`, `--help` | Print usage and exit | — |
| `--path PATH` | Directory to inspect; disk usage refers to its filesystem | Current directory |
| `--top N` | Maximum number of largest immediate files/directories; positive integer | `5` |
| `--interval SECONDS` | Positive CPU sampling interval; applies to `--once` too | `1` |
| `--once` | Take one CPU sample, then exit | Continuous CPU monitoring |
| `--skip-public-ip` | Do not contact the external public-IP service | Lookup enabled |
| `--timeout SECONDS` | Positive timeout for the IP request and each route command | `5` |

System, network, disk, and directory information is collected **once at startup**; only CPU usage is repeated. The first CPU sample waits for the requested interval. Ctrl+C stops the CPU loop cleanly.

## Scope and limitations

- Directory sizes are logical file sizes, not allocated disk blocks. Symbolic links and special files are skipped; hard-linked files may be counted more than once. Scanning a large directory tree can take time, and files can change during a scan.
- The tool does not elevate privileges. Unreadable or disappearing entries are skipped with warnings; reported totals may therefore be incomplete.
- Linux route discovery examines the main routing table. Policy-routing tables and destination-specific route selection are outside the scope. Windows displays route metrics, not the combined route-plus-interface cost.
- The public-IP result is the address observed by that HTTPS service for this request. It does not prove VPN coverage, anonymity, or the absence of leaks. The service receives the request and its source IP; `--skip-public-ip` avoids this lookup.
- Timeouts prevent indefinitely blocked route commands and stalled network operations; the HTTP timeout is a socket timeout, not an overall wall-clock deadline.
- Missing optional information is reported as a warning while the tool continues. Invalid arguments, a missing `psutil` dependency, or a CPU collection failure result in a nonzero exit status.

## Validation

```bash
python -m py_compile main.py
python -m unittest discover -s tests -v
```

The standard-library test suite covers empty/small directories, file-versus-directory sizes, numeric sorting, symbolic links, filesystem errors, binary units, Windows/Linux route parsing, multiple interfaces/next hops, route failures, HTTP timeouts and invalid responses, argument validation, and one-shot output.

Tests mock `psutil`, external HTTP calls, and OS route commands. They can run without installing `psutil`, but running the actual tool requires it. Live Windows execution, real network lookups, and real CPU collection have not been validated in the implementation environment.
