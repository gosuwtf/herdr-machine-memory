#!/usr/bin/env python3
"""Herdr tab-bar memory indicator for this machine and its connected peers.

A peer counts as connected while a Herdr client on this machine holds a live
SSH bridge to it. Its memory is read through that bridge's OpenSSH control
socket, so no new SSH authentication happens and disconnected peers are hidden.
"""
import concurrent.futures
import glob
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

PLUGIN_ID = "machine-memory"
LAUNCHER_NAME = "status"
LABELS_NAME = "labels.json"
BRIDGE_MARKER = "herdr-remote-output-ready"

# Fixed read-only probe, with no interpolation of config into shell commands.
REMOTE_PROBE = ('case "$(uname -s)" in '
                'Linux) cat /proc/meminfo;; '
                'Darwin) sysctl -n hw.memsize; vm_stat;; '
                '*) exit 1;; esac')

# Written into the plugin config dir, whose path is stable across installs.
# It resolves the plugin root on every run, so `herdr plugin install` updates
# take effect without rewriting it.
LAUNCHER = f"""#!/bin/sh
# Written by the {PLUGIN_ID} Herdr plugin. Safe to delete; the plugin's
# startup hook or `setup` action recreates it.
herdr=${{HERDR_BIN_PATH:-herdr}}
root=$("$herdr" plugin list --plugin {PLUGIN_ID} --json | python3 -c \\
  'import json, sys; print(json.load(sys.stdin)["result"]["plugins"][0]["plugin_root"])') || exit 1
MACHINE_MEMORY_CONFIG_DIR=$(dirname "$0") exec python3 "$root/memory.py"
"""


def run(argv, timeout=2):
    return subprocess.run(argv, check=True, capture_output=True, text=True,
                          timeout=timeout, stdin=subprocess.DEVNULL).stdout


def herdr_bin():
    return os.environ.get("HERDR_BIN_PATH") or "herdr"


def linux_memory(text):
    values = {key: int(value) * 1024 for key, value in
              re.findall(r"^(\w+):\s+(\d+)\s+kB", text, re.MULTILINE)}
    total = values["MemTotal"]
    return total - values["MemAvailable"], total


def mac_memory(stats, total):
    page_size = int(re.search(r"page size of (\d+) bytes", stats).group(1))
    pages = {key: int(value) for key, value in
             re.findall(r"^([^:\n]+):\s+(\d+)\.", stats, re.MULTILINE)}
    reclaimable = sum(pages[key] for key in
                      ("Pages free", "Pages inactive", "Pages speculative"))
    return max(0, total - reclaimable * page_size), total


def local_memory():
    if platform.system() == "Darwin":
        return mac_memory(run(["/usr/bin/vm_stat"]),
                          int(run(["/usr/sbin/sysctl", "-n", "hw.memsize"])))
    return linux_memory(Path("/proc/meminfo").read_text())


def parse_bridges(ps_output):
    """Return (target, ControlPath pattern) for each Herdr SSH bridge process."""
    bridges = []
    for line in ps_output.splitlines():
        argv = line.split()
        if not argv or Path(argv[0]).name != "ssh" or BRIDGE_MARKER not in line:
            continue
        try:
            bridges.append((argv[argv.index("-T") + 1], argv[argv.index("-S") + 1]))
        except (ValueError, IndexError):
            continue
    return bridges


def control_sockets(pattern):
    # Herdr passes `<private prefix>-%C`; ssh expands the token, so match the
    # prefix instead of recomputing OpenSSH's connection hash.
    prefix = pattern.split("%", 1)[0]
    return [path for path in sorted(glob.glob(glob.escape(prefix) + "*"))
            if Path(path).is_socket()]


def live_socket(target, pattern):
    for path in control_sockets(pattern):
        try:
            run(["ssh", "-S", path, "-O", "check", "--", target])
            return path
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def connected_peers():
    """Map each connected SSH target to a live control socket for it."""
    peers = {}
    for target, pattern in parse_bridges(run(["ps", "-axww", "-o", "args="])):
        if target not in peers:
            path = live_socket(target, pattern)
            if path:
                peers[target] = path
    return peers


def remote_memory(target, socket):
    output = run(["ssh", "-S", socket, "-o", "ControlMaster=no",
                  "-o", "BatchMode=yes", "-T", "--", target, REMOTE_PROBE],
                 timeout=4)
    if output.startswith("MemTotal:"):
        return linux_memory(output)
    total, stats = output.split("\n", 1)
    return mac_memory(stats, int(total))


def saved_machines():
    """Saved Herdr machine labels by SSH target, in sidebar order."""
    try:
        machines = json.loads(run([herdr_bin(), "machine", "list", "--json"]))
        return {machine["target"]: machine["label"] for machine in machines}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return {}


def load_labels():
    config_dir = os.environ.get("MACHINE_MEMORY_CONFIG_DIR")
    try:
        return json.loads((Path(config_dir) / LABELS_NAME).read_text())
    except (TypeError, OSError, ValueError):
        return {}


def indicator(label, probe):
    try:
        used, total = probe()
        if not 0 <= used <= total or total <= 0:
            raise ValueError("invalid memory counters")
        return f"{label}: {used / total:.0%}"
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, AttributeError):
        return f"{label}: unavailable"


def status_line():
    labels = load_labels()
    saved = saved_machines()
    try:
        peers = connected_peers()
    except (OSError, subprocess.SubprocessError):
        peers = {}
    order = list(saved)
    targets = sorted(peers, key=lambda t: (order.index(t) if t in order else len(order), t))

    hostname = platform.node().split(".")[0]
    probes = [(labels.get(hostname, hostname), local_memory)]
    for target in targets:
        name = saved.get(target) or target.rsplit("@", 1)[-1]
        probes.append((labels.get(name, name),
                       lambda t=target: remote_memory(t, peers[t])))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        return " · ".join(executor.map(lambda p: indicator(*p), probes))


def write_launcher():
    path = Path(os.environ["HERDR_PLUGIN_CONFIG_DIR"]) / LAUNCHER_NAME
    path.write_text(LAUNCHER)
    path.chmod(0o755)
    print(path)


def main():
    if sys.argv[1:] == ["setup"]:
        write_launcher()
    else:
        print(status_line())


if __name__ == "__main__":
    main()
