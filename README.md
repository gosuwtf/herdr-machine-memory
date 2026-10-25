# machine-memory

A [Herdr](https://herdr.dev) plugin that shows memory usage in the tab bar for
the machine running Herdr and for every machine it's **currently connected to**:

```
laptop: 54% · workbox: 50% · mini: 55%
```

A machine shows up while a Herdr client on this host has a live SSH bridge to
it (a saved machine in the sidebar, or a `herdr --remote` attach). When the
connection drops, the machine disappears from the bar. Remote memory is read
through the OpenSSH control socket Herdr already opened, so nothing new
authenticates and the remote needs no Python or plugin. A connected machine
whose probe fails shows `unavailable`, never a stale number.

Dependency-free Python 3.9+, Linux and macOS.

## Install

Install it on every machine you run a Herdr client from:

```bash
herdr plugin install gosuwtf/herdr-machine-memory
herdr plugin action invoke machine-memory.setup   # or restart the Herdr server
```

`setup` (also run by the plugin's startup hook) writes a small `status`
launcher into the plugin config dir, which stays put across plugin updates.
Point the tab bar at it in `~/.config/herdr/config.toml`:

```toml
[ui]
tab_bar_right = [
  { type = "command", command = "\"$(\"${HERDR_BIN_PATH:-herdr}\" plugin config-dir machine-memory)/status\"", interval_seconds = 10, timeout_seconds = 6 },
]
```

Then `herdr server reload-config`.

Herdr resolves tab-bar commands on the server, so a machine you `--remote`
attach to shows its own view (usually just itself) unless it also has
connections of its own.

## Labels

Names default to the saved machine label (or the SSH host) and the local
hostname. To shorten them, create `labels.json` in
`$(herdr plugin config-dir machine-memory)`:

```json
{ "laptop": "lap", "workbox": "wb" }
```

## What the number means

Used physical memory as a rounded percentage of total. Linux uses
`MemTotal - MemAvailable`. macOS approximates used memory as total minus free,
inactive, and speculative pages; this is not memory pressure and may differ
from Activity Monitor. Swap is excluded. Herdr hides the right-side status
when tabs need the space.

## Development

```bash
git clone https://github.com/gosuwtf/herdr-machine-memory
herdr plugin link "$PWD/herdr-machine-memory"
python3 -m unittest discover -s herdr-machine-memory -v
```

Connection detection reads Herdr's own `ssh ... -S <ControlPath> -T <target>`
bridge processes from `ps`, so it depends on Herdr's managed SSH config
(`remote.manage_ssh_config = true`, the default).
