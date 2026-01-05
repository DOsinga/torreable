#!/usr/bin/env -S uvx --quiet --from mcp --from aiohttp --from stem python
# /// script
# dependencies = [
#   "mcp",
#   "aiohttp",
#   "stem",
# ]
# ///
"""
Torreable - Publish static websites as Tor hidden services via MCP
"""

import asyncio
import shutil
import socket
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from aiohttp import web
from mcp.server.fastmcp import FastMCP

try:
    from stem.control import Controller
except ImportError:
    Controller = None

TORREABLE_DIR = Path.home() / ".torreable" / "sites"

INSTRUCTIONS = """
Torreable lets you publish static websites as Tor hidden services (.onion sites).

Requirements:
- Tor must be running with a control port (default: 9051)
- Install Tor: `brew install tor` (macOS) or `apt install tor` (Linux)
- Start Tor: `tor` or `brew services start tor`

Workflow:
1. create_site - Initialize a site from a directory
2. preview - View locally before publishing  
3. publish - Make it live on Tor network
4. unpublish - Take it offline (keeps .onion address for later)
5. destroy - Permanently delete site and address

Sites are only reachable while this server is running.
""".strip()

mcp = FastMCP("torreable", instructions=INSTRUCTIONS)


@dataclass
class Site:
    name: str
    directory: Path
    key_type: Optional[str] = None
    key_content: Optional[str] = None
    onion_address: Optional[str] = None
    local_port: Optional[int] = None
    http_runner: Optional[web.AppRunner] = field(default=None, repr=False)
    published: bool = False


class TorreableState:
    def __init__(self):
        self.sites: dict[str, Site] = {}
        self.controller: Optional[Controller] = None
        TORREABLE_DIR.mkdir(parents=True, exist_ok=True)
        self._load_sites()

    def _load_sites(self):
        for site_dir in TORREABLE_DIR.iterdir():
            if site_dir.is_dir():
                key_file = site_dir / "key"
                content_link = site_dir / "content"
                if content_link.exists():
                    key_type, key_content, onion = None, None, None
                    if key_file.exists():
                        parts = key_file.read_text().strip().split(":", 1)
                        if len(parts) == 2:
                            key_type, key_content = parts
                    hostname_file = site_dir / "hostname"
                    if hostname_file.exists():
                        onion = hostname_file.read_text().strip()
                    self.sites[site_dir.name] = Site(
                        name=site_dir.name,
                        directory=content_link.resolve(),
                        key_type=key_type,
                        key_content=key_content,
                        onion_address=onion,
                    )

    def _ensure_tor(self) -> Controller:
        if Controller is None:
            raise RuntimeError("stem library not installed: pip install stem")
        if self.controller is None:
            self.controller = Controller.from_port()
            self.controller.authenticate()
        return self.controller


state = TorreableState()


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


async def _start_http_server(directory: Path, port: int) -> web.AppRunner:
    app = web.Application()
    app.router.add_static("/", directory, show_index=True)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", port)
    await site.start()
    return runner


@mcp.tool()
async def create_site(name: str, directory: str) -> str:
    """Create a new site from a directory of static files.

    Args:
        name: Unique name for this site
        directory: Path to directory containing static files (index.html, etc.)
    """
    dir_path = Path(directory).resolve()
    if not dir_path.is_dir():
        return f"Error: {directory} is not a directory"

    warning = ""
    if not (dir_path / "index.html").exists():
        warning = f"\nWarning: No index.html found in {directory}"

    site_dir = TORREABLE_DIR / name
    site_dir.mkdir(exist_ok=True)

    content_link = site_dir / "content"
    if content_link.exists():
        content_link.unlink()
    content_link.symlink_to(dir_path)

    state.sites[name] = Site(name=name, directory=dir_path)
    return f"Created site '{name}' -> {dir_path}{warning}"


@mcp.tool()
async def preview(name: str) -> str:
    """Start local preview server for a site.

    Args:
        name: Site name
    """
    if name not in state.sites:
        return f"Error: Site '{name}' not found"

    site = state.sites[name]
    if site.local_port and site.http_runner:
        return f"Already previewing at http://localhost:{site.local_port}"

    port = _find_free_port()
    runner = await _start_http_server(site.directory, port)
    site.local_port = port
    site.http_runner = runner

    return f"Preview running at http://localhost:{port}"


@mcp.tool()
async def publish(name: str) -> str:
    """Publish a site to the Tor network.

    Args:
        name: Site name
    """
    if name not in state.sites:
        return f"Error: Site '{name}' not found"

    site = state.sites[name]
    if site.published:
        return f"Already published at http://{site.onion_address}"

    try:
        controller = state._ensure_tor()
    except Exception as e:
        return f"Error connecting to Tor: {e}\n\nMake sure Tor is running with control port enabled."

    if not site.local_port or not site.http_runner:
        port = _find_free_port()
        runner = await _start_http_server(site.directory, port)
        site.local_port = port
        site.http_runner = runner

    if site.key_type and site.key_content:
        response = await asyncio.to_thread(
            controller.create_ephemeral_hidden_service,
            {80: site.local_port},
            key_type=site.key_type,
            key_content=site.key_content,
            await_publication=True,
        )
    else:
        response = await asyncio.to_thread(
            controller.create_ephemeral_hidden_service,
            {80: site.local_port},
            await_publication=True,
        )
        site.key_type = response.private_key_type
        site.key_content = response.private_key
        key_file = TORREABLE_DIR / name / "key"
        key_file.write_text(f"{site.key_type}:{site.key_content}")

    site.onion_address = f"{response.service_id}.onion"
    site.published = True

    hostname_file = TORREABLE_DIR / name / "hostname"
    hostname_file.write_text(site.onion_address)

    return f"Published at http://{site.onion_address}"


@mcp.tool()
async def unpublish(name: str) -> str:
    """Take a site offline but keep its .onion address for later.

    Args:
        name: Site name
    """
    if name not in state.sites:
        return f"Error: Site '{name}' not found"

    site = state.sites[name]
    if not site.published:
        return f"Site '{name}' is not published"

    if state.controller and site.onion_address:
        service_id = site.onion_address.replace(".onion", "")
        state.controller.remove_ephemeral_hidden_service(service_id)

    if site.http_runner:
        await site.http_runner.cleanup()
        site.http_runner = None
        site.local_port = None

    site.published = False
    return f"Unpublished '{name}'. Address {site.onion_address} preserved for later."


@mcp.tool()
async def destroy(name: str) -> str:
    """Permanently delete a site and its .onion address.

    Args:
        name: Site name
    """
    if name not in state.sites:
        return f"Error: Site '{name}' not found"

    site = state.sites[name]
    if site.published:
        await unpublish(name)

    site_dir = TORREABLE_DIR / name
    if site_dir.exists():
        shutil.rmtree(site_dir)

    del state.sites[name]
    return f"Destroyed site '{name}' and its .onion address"


@mcp.tool()
async def list_sites() -> str:
    """List all sites and their status."""
    if not state.sites:
        return "No sites configured"

    lines = []
    for site in state.sites.values():
        status = "🟢 published" if site.published else "⚫ offline"
        addr = site.onion_address or "(no address yet)"
        lines.append(f"- {site.name}: {status} - {addr}")
    return "\n".join(lines)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
