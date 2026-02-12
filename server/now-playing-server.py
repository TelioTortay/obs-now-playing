#!/usr/bin/env python3
"""
Now Playing Overlay Server
Cross-platform media control integration for OBS and streaming software
Supports Windows (WMC) and Linux (MPRIS)
"""

import asyncio
import json
import signal
import sys
import platform
from datetime import datetime
from pathlib import Path

# Detect OS
IS_WINDOWS = platform.system() == 'Windows'
IS_LINUX = platform.system() == 'Linux'

try:
    import websockets
    from aiohttp import web
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text
    from rich import box
except ImportError:
    print("❌ Error: missing core modules")
    print("Install with: pip install websockets aiohttp rich")
    sys.exit(1)

# OS-specific imports
if IS_WINDOWS:
    try:
        from winsdk.windows.media.control import \
            GlobalSystemMediaTransportControlsSessionManager as MediaManager
        BACKEND = "Windows Media Control"
    except ImportError:
        print("❌ Error: winsdk not installed (required on Windows)")
        print("Install with: pip install winsdk")
        sys.exit(1)
        
elif IS_LINUX:
    try:
        from pydbus import SessionBus
        BACKEND = "MPRIS (Linux)"
    except ImportError as e:
        print("❌ Error: pydbus not properly installed (required on Linux)")
        print("\nInstall system dependencies first:")
        print("  Ubuntu/Debian: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0")
        print("  Arch:          sudo pacman -S python-gobject")
        print("  Fedora:        sudo dnf install python3-gobject")
        print("\nThen install pydbus:")
        print("  pip install pydbus")
        print(f"\nDetails: {e}")
        sys.exit(1)
else:
    print(f"❌ Error: Unsupported OS: {platform.system()}")
    print("Supported: Windows, Linux")
    sys.exit(1)

# Ports
WS_PORT = 6534
HTTP_PORT = 6535

# Connected clients
clients = set()

# Flag for clean shutdown
running = True

# Track last title to avoid reloading cover
last_cover_title = ''
cover_timestamp = 0

# Rich console for dashboard
console = Console()

# Last media info for display
current_media_info = None

# Folder for covers
if IS_WINDOWS:
    COVER_DIR = Path.home() / "AppData" / "Local" / "Temp" / "NowPlayingCovers"
else:
    COVER_DIR = Path.home() / ".cache" / "now-playing-overlay"

COVER_DIR.mkdir(parents=True, exist_ok=True)
CURRENT_COVER = COVER_DIR / "current.jpg"

# ============================================================================
# WINDOWS MEDIA CONTROL BACKEND
# ============================================================================

async def get_media_info_windows():
    """Get media info from Windows Media Control"""
    try:
        sessions = await MediaManager.request_async()
        current_session = sessions.get_current_session()
        
        if current_session is None:
            return None
        
        info = await current_session.try_get_media_properties_async()
        playback_info = current_session.get_playback_info()
        timeline = current_session.get_timeline_properties()
        
        # Playback state
        state = 'STOPPED'
        if playback_info.playback_status == 4:
            state = 'PLAYING'
        elif playback_info.playback_status == 3:
            state = 'PAUSED'
        
        # Duration and position
        duration_sec = 0
        position_sec = 0
        
        if timeline.end_time:
            duration_sec = int(timeline.end_time.total_seconds())
        if timeline.position:
            position_sec = int(timeline.position.total_seconds())
        
        # Handle cover
        global last_cover_title, cover_timestamp
        cover_url = ''
        current_title = info.title or ''
        
        if current_title and current_title != last_cover_title and info.thumbnail:
            try:
                stream = await info.thumbnail.open_read_async()
                if stream:
                    from winsdk.windows.storage.streams import DataReader
                    reader = DataReader(stream)
                    bytes_loaded = await reader.load_async(10 * 1024 * 1024)
                    
                    if bytes_loaded > 0:
                        image_array = bytearray(bytes_loaded)
                        reader.read_bytes(image_array)
                        
                        with open(CURRENT_COVER, 'wb') as f:
                            f.write(image_array)
                        
                        last_cover_title = current_title
                        cover_timestamp = int(datetime.now().timestamp())
                    
                    reader.close()
                    stream.close()
            except:
                pass
        
        if CURRENT_COVER.exists():
            cover_url = f"http://127.0.0.1:{HTTP_PORT}/cover.jpg?t={cover_timestamp}"
        
        return {
            'state': state,
            'player_name': current_session.source_app_user_model_id or '',
            'title': info.title or '',
            'artist': info.artist or '',
            'album': info.album_title or '',
            'cover_url': cover_url,
            'duration_seconds': duration_sec,
            'position_seconds': position_sec,
        }
    
    except Exception as e:
        return None

# ============================================================================
# MPRIS BACKEND (LINUX)
# ============================================================================

def get_media_info_linux():
    """Get media info from MPRIS (Linux)"""
    try:
        bus = SessionBus()
        
        # Get DBus interface to list services
        dbus = bus.get('.DBus')
        services = [s for s in dbus.ListNames() if 'mpris' in s.lower()]
        
        # Try each MPRIS player until we find one that's playing
        player = None
        service_name = ''
        
        for service in services:
            try:
                candidate = bus.get(service, '/org/mpris/MediaPlayer2')
                # Check if playing or paused
                if candidate.PlaybackStatus in ['Playing', 'Paused']:
                    player = candidate
                    service_name = service
                    break
            except Exception:
                # Skip broken MPRIS implementations (like Chromium)
                continue
        
        if not player:
            return None
        
        metadata = player.Metadata
        
        # State
        state_map = {
            'Playing': 'PLAYING',
            'Paused': 'PAUSED',
            'Stopped': 'STOPPED'
        }
        state = state_map.get(player.PlaybackStatus, 'STOPPED')
        
        # Duration and position (in microseconds)
        duration_sec = int(metadata.get('mpris:length', 0) / 1000000)
        position_sec = int(player.Position / 1000000)
        
        # Cover URL
        global last_cover_title, cover_timestamp
        cover_url = ''
        current_title = metadata.get('xesam:title', '')
        art_url = metadata.get('mpris:artUrl', '')
        
        # MPRIS provides URL directly, no need to download
        if art_url and current_title != last_cover_title:
            # Handle file:// URLs or http:// URLs
            if art_url.startswith('file://'):
                import shutil
                try:
                    source = art_url.replace('file://', '')
                    shutil.copy2(source, CURRENT_COVER)
                    last_cover_title = current_title
                    cover_timestamp = int(datetime.now().timestamp())
                except:
                    pass
            else:
                # HTTP URL - use directly
                cover_url = art_url
        
        if CURRENT_COVER.exists() and not cover_url:
            cover_url = f"http://127.0.0.1:{HTTP_PORT}/cover.jpg?t={cover_timestamp}"
        
        # Artists (list to string)
        artists = metadata.get('xesam:artist', [])
        artist = ', '.join(artists) if isinstance(artists, list) else str(artists)
        
        return {
            'state': state,
            'player_name': service_name.split('.')[-1],
            'title': current_title,
            'artist': artist,
            'album': metadata.get('xesam:album', ''),
            'cover_url': cover_url,
            'duration_seconds': duration_sec,
            'position_seconds': position_sec,
        }
    
    except Exception as e:
        return None

# ============================================================================
# UNIFIED BACKEND
# ============================================================================

async def get_media_info():
    """Unified media info getter (auto-detects OS)"""
    if IS_WINDOWS:
        raw_info = await get_media_info_windows()
    else:
        raw_info = get_media_info_linux()
    
    if not raw_info:
        return {
            'state': 'STOPPED',
            'player_name': '',
            'title': '',
            'artist': '',
            'album': '',
            'cover_url': '',
            'duration': '0:00',
            'duration_seconds': 0,
            'position': '0:00',
            'position_seconds': 0,
            'position_percent': 0,
            'volume': 100,
            'rating': 0,
            'repeat_mode': 'NONE',
            'shuffle_active': False,
            'timestamp': int(datetime.now().timestamp())
        }
    
    # Format time
    def format_time(seconds):
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}:{secs:02d}"
    
    duration_sec = raw_info['duration_seconds']
    position_sec = raw_info['position_seconds']
    
    return {
        'state': raw_info['state'],
        'player_name': raw_info['player_name'],
        'title': raw_info['title'],
        'artist': raw_info['artist'],
        'album': raw_info['album'],
        'cover_url': raw_info['cover_url'],
        'duration': format_time(duration_sec),
        'duration_seconds': duration_sec,
        'position': format_time(position_sec),
        'position_seconds': position_sec,
        'position_percent': (position_sec / duration_sec * 100) if duration_sec > 0 else 0,
        'volume': 100,
        'rating': 0,
        'repeat_mode': 'NONE',
        'shuffle_active': False,
        'timestamp': int(datetime.now().timestamp())
    }

async def get_and_cache_media_info():
    """Get and cache media info"""
    global current_media_info
    info = await get_media_info()
    if info:
        current_media_info = info
    return info

async def serve_cover(request):
    """Serves the cover via HTTP"""
    if CURRENT_COVER.exists():
        return web.FileResponse(CURRENT_COVER)
    else:
        return web.Response(status=404)

def generate_dashboard():
    """Generates CLI dashboard"""
    global current_media_info
    
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=6)
    )
    
    # Header
    header_text = Text("♫ NOW PLAYING OVERLAY", style="bold magenta", justify="center")
    layout["header"].update(Panel(header_text, border_style="magenta"))
    
    # Body
    if current_media_info and current_media_info['state'] == 'PLAYING':
        info = current_media_info
        
        table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        table.add_column("Field", style="cyan", width=15)
        table.add_column("Value", style="white")
        
        state_emoji = "▶️" if info['state'] == 'PLAYING' else "⏸️" if info['state'] == 'PAUSED' else "⏹️"
        table.add_row("State", f"{state_emoji} {info['state']}")
        
        title = info['title'] or '-'
        artist = info['artist'] or '-'
        table.add_row("Title", f"[bold yellow]{title}[/bold yellow]")
        table.add_row("Artist", f"[bold green]{artist}[/bold green]")
        
        if info['album']:
            table.add_row("Album", info['album'])
        
        position = info['position']
        duration = info['duration']
        percent = info['position_percent']
        
        bar_width = 40
        filled = int(bar_width * percent / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        table.add_row("Progress", f"{position} / {duration}")
        table.add_row("", f"[cyan]{bar}[/cyan] {percent:.1f}%")
        
        cover_status = "✓ Available" if info['cover_url'] else "✗ Not available"
        table.add_row("Artwork", cover_status)
        
        layout["body"].update(Panel(table, title="[bold]🎵 Now Playing[/bold]", border_style="cyan"))
    
    elif current_media_info and current_media_info['state'] == 'PAUSED':
        paused_text = Text("⏸️  PAUSED", style="bold yellow", justify="center")
        layout["body"].update(Panel(paused_text, border_style="yellow"))
    
    else:
        stopped_text = Text("⏹️  NO PLAYBACK", style="bold red", justify="center")
        layout["body"].update(Panel(stopped_text, border_style="red"))
    
    # Footer
    stats_table = Table(show_header=False, box=None, padding=(0, 2))
    stats_table.add_column(style="dim")
    stats_table.add_column(style="dim")
    
    stats_table.add_row("Platform", f"{platform.system()} ({BACKEND})")
    stats_table.add_row("WebSocket", f"ws://127.0.0.1:{WS_PORT}")
    stats_table.add_row("HTTP (covers)", f"http://127.0.0.1:{HTTP_PORT}")
    stats_table.add_row("Connected clients", f"{len(clients)}")
    
    layout["footer"].update(Panel(stats_table, title="[dim]Server[/dim]", border_style="dim"))
    
    return layout

async def broadcast_updates(live):
    """Sends updates to all clients"""
    while running:
        try:
            if clients:
                media_info = await get_and_cache_media_info()
                if media_info:
                    message = json.dumps(media_info)
                    await asyncio.gather(
                        *[client.send(message) for client in clients],
                        return_exceptions=True
                    )
            else:
                await get_and_cache_media_info()
            
            live.update(generate_dashboard())
            await asyncio.sleep(0.2)
        
        except Exception as e:
            await asyncio.sleep(1)

async def handle_client(websocket):
    """Handles client connection"""
    clients.add(websocket)
    
    try:
        handshake = await websocket.recv()
        if handshake == 'RECIPIENT':
            media_info = await get_media_info()
            if media_info:
                await websocket.send(json.dumps(media_info))
        
        async for message in websocket:
            pass
    
    except websockets.exceptions.ConnectionClosed:
        pass
    
    finally:
        clients.remove(websocket)

async def main():
    global running
    
    console.clear()
    
    # HTTP server
    app = web.Application()
    app.router.add_get('/cover.jpg', serve_cover)
    runner = web.AppRunner(app)
    await runner.setup()
    http_site = web.TCPSite(runner, '127.0.0.1', HTTP_PORT)
    await http_site.start()
    
    # WebSocket server
    ws_server = await websockets.serve(handle_client, "127.0.0.1", WS_PORT)
    
    # Dashboard
    with Live(generate_dashboard(), console=console, refresh_per_second=5) as live:
        broadcast_task = asyncio.create_task(broadcast_updates(live))
        
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            pass
        
        running = False
        broadcast_task.cancel()
        ws_server.close()
        await ws_server.wait_closed()
        await runner.cleanup()

def signal_handler(sig, frame):
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)
