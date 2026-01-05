# Torreable

Publish static websites as Tor hidden services (.onion sites) via MCP.

## Requirements

- Python 3.10+
- Tor running with control port enabled

### Installing Tor

**macOS:**
```bash
brew install tor
brew services start tor
```

**Linux:**
```bash
apt install tor
systemctl start tor
```

Make sure Tor has a control port. Add to `/etc/tor/torrc` or `~/.torrc`:
```
ControlPort 9051
```

## Installation

### Click the button to install:

[![Install in Goose](https://block.github.io/goose/img/extension-install-dark.svg)](https://block.github.io/goose/extension?cmd=uvx&arg=torreable&id=torreable&name=Torreable&description=Publish%20static%20websites%20as%20Tor%20hidden%20services%20via%20MCP)

### Or install manually:

Go to `Advanced settings` -> `Extensions` -> `Add custom extension`. Name to your liking, use type `STDIO`, and set the `command` to `uvx torreable`. Click "Add Extension".

## Tools

| Tool | Description |
|------|-------------|
| `create_site(name, directory)` | Register a static site |
| `preview(name)` | Local preview at localhost |
| `publish(name)` | Publish to Tor network |
| `unpublish(name)` | Take offline, keep address |
| `destroy(name)` | Delete site and address |
| `list_sites()` | Show all sites and status |

## How it works

1. Sites are stored in `~/.torreable/sites/`
2. Each site keeps its Tor private key, so the .onion address persists
3. Publishing starts a local HTTP server and creates an ephemeral Tor hidden service
4. Sites are only reachable while torreable is running

## Example

```
> create_site("myblog", "/path/to/blog/dist")
Created site 'myblog' -> /path/to/blog/dist

> preview("myblog")
Preview running at http://localhost:52431

> publish("myblog")
Published at http://abc123...xyz.onion

> unpublish("myblog")
Unpublished 'myblog'. Address abc123...xyz.onion preserved for later.
```
