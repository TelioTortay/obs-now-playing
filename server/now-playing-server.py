#!/usr/bin/env python3
"""
Now Playing Overlay Server
Cross-platform media control integration for OBS and streaming software
Supports Windows (WMC) and Linux (MPRIS)
"""

import asyncio
import json
import socket
import sys
import platform
import threading
import queue
from datetime import datetime
from pathlib import Path

# Detect OS
IS_WINDOWS = platform.system() == 'Windows'
IS_LINUX = platform.system() == 'Linux'

try:
    import websockets
    from aiohttp import web
except ImportError:
    print("Error: missing core modules")
    print("Install with: pip install websockets aiohttp")
    sys.exit(1)

try:
    from PySide6.QtWidgets import (
        QApplication, QWidget, QLabel, QProgressBar,
        QVBoxLayout, QHBoxLayout, QComboBox, QSystemTrayIcon,
        QMenu, QSizePolicy, QDialog, QPushButton, QSpinBox,
        QMessageBox, QFrame, QRadioButton, QButtonGroup,
    )
    from PySide6.QtCore import Qt, QTimer, QUrl
    from PySide6.QtGui import (
        QIcon, QPixmap, QPainter, QColor, QFont,
        QPen, QBrush, QAction,
    )
    from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
except ImportError:
    print("Error: PySide6 not installed")
    print("Install with: pip install PySide6")
    sys.exit(1)

# OS-specific imports
if IS_WINDOWS:
    try:
        from winsdk.windows.media.control import \
            GlobalSystemMediaTransportControlsSessionManager as MediaManager
        BACKEND = "Windows Media Control"
    except ImportError:
        print("Error: winsdk not installed (required on Windows)")
        print("Install with: pip install winsdk")
        sys.exit(1)

elif IS_LINUX:
    try:
        from pydbus import SessionBus
        BACKEND = "MPRIS (Linux)"
    except ImportError as e:
        print("Error: pydbus not properly installed (required on Linux)")
        print("\nInstall system dependencies first:")
        print("  Ubuntu/Debian: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0")
        print("  Arch:          sudo pacman -S python-gobject")
        print("  Fedora:        sudo dnf install python3-gobject")
        print("\nThen install pydbus:")
        print("  pip install pydbus")
        print(f"\nDetails: {e}")
        sys.exit(1)
else:
    print(f"Error: Unsupported OS: {platform.system()}")
    print("Supported: Windows, Linux")
    sys.exit(1)

# App icon path (root of the project, one level above this script)
APP_ICON_PATH = Path(__file__).parent.parent / 'NowPlayingIcon.ico'

# Ports
WS_PORT = 6534
HTTP_PORT = 6535

# Network binding: '127.0.0.1' (localhost) or '0.0.0.0' (all interfaces)
BIND_HOST = '127.0.0.1'
# Host used in cover URLs sent to clients (= LAN IP when binding to all interfaces)
COVER_HOST = '127.0.0.1'

# Connected WebSocket clients
clients = set()

# Flag for clean shutdown
running = True

# Track last title to avoid reloading cover
last_cover_title = ''
cover_timestamp = 0

# Cached Windows Media session manager (avoid re-creating COM objects every poll)
_cached_media_manager = None

# Current media info cache
current_media_info = None

# Selected player (None = auto)
selected_player = None

# Thread-safe queues for asyncio → Qt communication
media_queue: queue.Queue = queue.Queue(maxsize=5)
players_queue: queue.Queue = queue.Queue(maxsize=5)

# Folder for covers
if IS_WINDOWS:
    COVER_DIR = Path.home() / "AppData" / "Local" / "Temp" / "NowPlayingCovers"
else:
    COVER_DIR = Path.home() / ".cache" / "now-playing-overlay"

COVER_DIR.mkdir(parents=True, exist_ok=True)
CURRENT_COVER = COVER_DIR / "current.jpg"

# Config — next to the .exe when compiled, next to the script otherwise
if getattr(sys, 'frozen', False):
    CONFIG_FILE = Path(sys.executable).parent / 'config.json'
else:
    CONFIG_FILE = Path(__file__).parent / 'config.json'


def get_local_ip() -> str:
    """Returns the LAN IP of this machine (best-guess via a dummy UDP connect)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'selected_player': None, 'ws_port': 6534, 'http_port': 6535, 'bind_all': False}


def save_config(updates: dict):
    """Merges *updates* into the existing config file."""
    try:
        current = load_config()
        current.update(updates)
        CONFIG_FILE.write_text(json.dumps(current, indent=2), encoding='utf-8')
    except Exception:
        pass


# ============================================================================
# PLAYER DISCOVERY
# ============================================================================

async def _get_media_manager():
    """Return a cached MediaManager, creating it on first call or after error."""
    global _cached_media_manager
    if _cached_media_manager is None:
        _cached_media_manager = await MediaManager.request_async()
    return _cached_media_manager


def _invalidate_media_manager():
    """Reset the cache so the next call to _get_media_manager() creates a fresh one."""
    global _cached_media_manager
    _cached_media_manager = None


async def get_available_players_windows() -> list:
    """Returns [(display_name, app_id)] for all active WMC sessions."""
    try:
        sessions = await _get_media_manager()
        result = [('Automatic', None)]
        for session in sessions.get_sessions():
            app_id = session.source_app_user_model_id or ''
            # Clean display name: strip path separators, .exe, UWP package suffixes
            display = app_id.split('!')[-1].split('\\')[-1].split('/')[-1]
            display = display.replace('.exe', '').replace('.EXE', '')
            if not display:
                display = app_id.split('.')[-1]
            result.append((display.capitalize() if display else app_id, app_id))
        return result
    except Exception:
        _invalidate_media_manager()
        return [('Automatique', None)]


def get_available_players_linux() -> list:
    """Returns [(display_name, service_name)] for all MPRIS services."""
    try:
        bus = SessionBus()
        dbus = bus.get('.DBus')
        services = [s for s in dbus.ListNames() if 'mpris' in s.lower()]
        result = [('Automatic', None)]
        for service in services:
            try:
                display = service.split('.')[-1].capitalize()
                result.append((display, service))
            except Exception:
                pass
        return result
    except Exception:
        return [('Automatique', None)]


# ============================================================================
# WINDOWS MEDIA CONTROL BACKEND
# ============================================================================

async def get_media_info_windows(sel_player=None):
    """Get media info from Windows Media Control."""
    try:
        sessions = await _get_media_manager()

        target_session = None
        if sel_player:
            for session in sessions.get_sessions():
                if session.source_app_user_model_id == sel_player:
                    target_session = session
                    break

        if target_session is None:
            target_session = sessions.get_current_session()

        if target_session is None:
            return None

        info = await target_session.try_get_media_properties_async()
        playback_info = target_session.get_playback_info()
        timeline = target_session.get_timeline_properties()

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
            stream = None
            reader = None
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
            except Exception:
                pass
            finally:
                if reader:
                    try:
                        reader.close()
                    except Exception:
                        pass
                if stream:
                    try:
                        stream.close()
                    except Exception:
                        pass

        if CURRENT_COVER.exists():
            cover_url = f"http://{COVER_HOST}:{HTTP_PORT}/cover.jpg?t={cover_timestamp}"

        return {
            'state': state,
            'player_name': target_session.source_app_user_model_id or '',
            'title': info.title or '',
            'artist': info.artist or '',
            'album': info.album_title or '',
            'cover_url': cover_url,
            'duration_seconds': duration_sec,
            'position_seconds': position_sec,
        }

    except Exception:
        _invalidate_media_manager()
        return None


# ============================================================================
# MPRIS BACKEND (LINUX)
# ============================================================================

def get_media_info_linux(sel_player=None):
    """Get media info from MPRIS (Linux)."""
    try:
        bus = SessionBus()

        player = None
        service_name = ''

        if sel_player:
            try:
                candidate = bus.get(sel_player, '/org/mpris/MediaPlayer2')
                if candidate.PlaybackStatus in ['Playing', 'Paused']:
                    player = candidate
                    service_name = sel_player
            except Exception:
                pass

        if player is None:
            dbus = bus.get('.DBus')
            services = [s for s in dbus.ListNames() if 'mpris' in s.lower()]
            for service in services:
                try:
                    candidate = bus.get(service, '/org/mpris/MediaPlayer2')
                    if candidate.PlaybackStatus in ['Playing', 'Paused']:
                        player = candidate
                        service_name = service
                        break
                except Exception:
                    continue

        if not player:
            return None

        metadata = player.Metadata

        state_map = {'Playing': 'PLAYING', 'Paused': 'PAUSED', 'Stopped': 'STOPPED'}
        state = state_map.get(player.PlaybackStatus, 'STOPPED')

        duration_sec = int(metadata.get('mpris:length', 0) / 1000000)
        position_sec = int(player.Position / 1000000)

        global last_cover_title, cover_timestamp
        cover_url = ''
        current_title = metadata.get('xesam:title', '')
        art_url = metadata.get('mpris:artUrl', '')

        if art_url and current_title != last_cover_title:
            if art_url.startswith('file://'):
                import shutil
                try:
                    source = art_url.replace('file://', '')
                    shutil.copy2(source, CURRENT_COVER)
                    last_cover_title = current_title
                    cover_timestamp = int(datetime.now().timestamp())
                except Exception:
                    pass
            else:
                cover_url = art_url

        if CURRENT_COVER.exists() and not cover_url:
            cover_url = f"http://{COVER_HOST}:{HTTP_PORT}/cover.jpg?t={cover_timestamp}"

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

    except Exception:
        return None


# ============================================================================
# UNIFIED BACKEND
# ============================================================================

async def get_media_info():
    """Unified media info getter."""
    if IS_WINDOWS:
        raw_info = await get_media_info_windows(selected_player)
    else:
        raw_info = get_media_info_linux(selected_player)

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
            'timestamp': int(datetime.now().timestamp()),
        }

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
        'timestamp': int(datetime.now().timestamp()),
    }


async def get_and_cache_media_info():
    global current_media_info
    info = await get_media_info()
    if info:
        current_media_info = info
    return info


# ============================================================================
# HTTP SERVER
# ============================================================================

async def serve_cover(request):
    if CURRENT_COVER.exists():
        return web.FileResponse(CURRENT_COVER)
    return web.Response(status=404)


# ============================================================================
# WEBSOCKET SERVER
# ============================================================================

async def handle_client(websocket):
    clients.add(websocket)
    try:
        handshake = await websocket.recv()
        if handshake == 'RECIPIENT':
            media_info = await get_media_info()
            if media_info:
                await websocket.send(json.dumps(media_info))
        async for _ in websocket:
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)


# ============================================================================
# ASYNCIO SERVER LOOP (runs in background thread)
# ============================================================================

async def broadcast_loop():
    """Polls media info and pushes updates to the Qt queue and WebSocket clients."""
    player_refresh_counter = 0

    while running:
        try:
            media_info = await get_and_cache_media_info()

            # Push to Qt via queue (drop if full to avoid back-pressure)
            try:
                media_queue.put_nowait(media_info)
            except queue.Full:
                pass

            # Broadcast to WebSocket clients
            if clients and media_info:
                message = json.dumps(media_info)
                await asyncio.gather(
                    *[client.send(message) for client in clients],
                    return_exceptions=True,
                )

            # Refresh available players list every ~2 s (10 × 200 ms)
            player_refresh_counter += 1
            if player_refresh_counter >= 10:
                player_refresh_counter = 0
                if IS_WINDOWS:
                    players = await get_available_players_windows()
                else:
                    players = get_available_players_linux()
                try:
                    players_queue.put_nowait(players)
                except queue.Full:
                    pass

            await asyncio.sleep(0.2)

        except Exception:
            await asyncio.sleep(1)


async def server_main():
    # HTTP server
    app = web.Application()
    app.router.add_get('/cover.jpg', serve_cover)
    runner = web.AppRunner(app)
    await runner.setup()
    http_site = web.TCPSite(runner, BIND_HOST, HTTP_PORT)
    await http_site.start()

    # WebSocket server
    ws_server = await websockets.serve(handle_client, BIND_HOST, WS_PORT)

    # Push initial player list
    if IS_WINDOWS:
        players = await get_available_players_windows()
    else:
        players = get_available_players_linux()
    try:
        players_queue.put_nowait(players)
    except queue.Full:
        pass

    try:
        await broadcast_loop()
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        await runner.cleanup()


def run_server(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(server_main())


# ============================================================================
# GUI HELPERS
# ============================================================================

def load_app_icon() -> QIcon:
    """Loads the app icon with the following priority:
    1. (compiled + Windows) icon embedded in the .exe by PyInstaller
    2. NowPlayingIcon.ico next to the script (dev mode)
    3. Programmatic music-note circle (last resort)
    """
    if getattr(sys, 'frozen', False) and IS_WINDOWS:
        # Extract the icon that PyInstaller embedded in the executable
        from PySide6.QtWidgets import QFileIconProvider
        from PySide6.QtCore import QFileInfo
        icon = QFileIconProvider().icon(QFileInfo(sys.executable))
        if not icon.isNull():
            return icon
    if APP_ICON_PATH.exists():
        return QIcon(str(APP_ICON_PATH))
    # Fallback: draw a simple music-note circle
    size = 32
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = 2
    painter.setBrush(QBrush(QColor('#4a9eff')))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    font = QFont()
    font.setPixelSize(int(size * 0.52))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QPen(QColor('white')))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, '\u266b')
    painter.end()
    return QIcon(pixmap)


# ============================================================================
# SETTINGS DIALOG
# ============================================================================

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Settings')
        self.setWindowIcon(load_app_icon())
        self.setMinimumWidth(360)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # ── Title ──────────────────────────────────────────────────────
        title_lbl = QLabel('Server ports')
        title_lbl.setObjectName('dlg_title')
        layout.addWidget(title_lbl)

        # ── Separator ─────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName('dlg_sep')
        layout.addWidget(sep)

        # ── WS port ───────────────────────────────────────────────────
        ws_row = QHBoxLayout()
        ws_lbl = QLabel('WebSocket:')
        ws_lbl.setObjectName('dlg_lbl')
        ws_lbl.setFixedWidth(150)
        self.ws_spin = QSpinBox()
        self.ws_spin.setRange(1024, 65535)
        self.ws_spin.setValue(WS_PORT)
        ws_row.addWidget(ws_lbl)
        ws_row.addWidget(self.ws_spin, 1)
        layout.addLayout(ws_row)

        # ── HTTP port ─────────────────────────────────────────────────
        http_row = QHBoxLayout()
        http_lbl = QLabel('HTTP (covers):')
        http_lbl.setObjectName('dlg_lbl')
        http_lbl.setFixedWidth(150)
        self.http_spin = QSpinBox()
        self.http_spin.setRange(1024, 65535)
        self.http_spin.setValue(HTTP_PORT)
        http_row.addWidget(http_lbl)
        http_row.addWidget(self.http_spin, 1)
        layout.addLayout(http_row)

        # ── Separator ─────────────────────────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setObjectName('dlg_sep')
        layout.addWidget(sep2)

        # ── Network binding ───────────────────────────────────────────
        net_title = QLabel('Network')
        net_title.setObjectName('dlg_title')
        layout.addWidget(net_title)

        self._bind_group = QButtonGroup(self)

        self.radio_local = QRadioButton('Localhost only  (127.0.0.1)')
        self.radio_local.setObjectName('dlg_radio')
        self._bind_group.addButton(self.radio_local, 0)

        self.radio_lan = QRadioButton('Local network  (all interfaces)')
        self.radio_lan.setObjectName('dlg_radio')
        self._bind_group.addButton(self.radio_lan, 1)

        current_bind_all = config.get('bind_all', False) if CONFIG_FILE.exists() else False
        (self.radio_lan if current_bind_all else self.radio_local).setChecked(True)

        layout.addWidget(self.radio_local)
        layout.addWidget(self.radio_lan)

        net_info = QLabel(
            'In local network mode, the cover URL sent to clients\n'
            'uses the automatically detected LAN IP.'
        )
        net_info.setObjectName('dlg_info')
        layout.addWidget(net_info)

        # ── Info ──────────────────────────────────────────────────────
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setObjectName('dlg_sep')
        layout.addWidget(sep3)

        info_lbl = QLabel(
            'Changes will be applied\non the next application restart.'
        )
        info_lbl.setObjectName('dlg_info')
        info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_lbl)

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        cancel_btn = QPushButton('Cancel')
        cancel_btn.setObjectName('dlg_cancel')
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton('Save')
        save_btn.setObjectName('dlg_save')
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        self._apply_style()

    # ------------------------------------------------------------------
    def _save(self):
        bind_all = self.radio_lan.isChecked()
        save_config({
            'ws_port': self.ws_spin.value(),
            'http_port': self.http_spin.value(),
            'bind_all': bind_all,
        })
        if bind_all:
            lan_ip = get_local_ip()
            net_line = f'  Network     →  all interfaces (LAN IP: {lan_ip})'
        else:
            net_line = '  Network     →  localhost only (127.0.0.1)'
        QMessageBox.information(
            self,
            'Settings saved',
            f'Settings updated:\n'
            f'  WebSocket  →  port {self.ws_spin.value()}\n'
            f'  HTTP       →  port {self.http_spin.value()}\n'
            f'{net_line}\n\n'
            'Restart the application to apply changes.',
        )
        self.accept()

    # ------------------------------------------------------------------
    def _apply_style(self):
        self.setStyleSheet("""
            SettingsDialog {
                background-color: #1e1e2e;
            }
            QLabel {
                color: #cdd6f4;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
            }
            QLabel#dlg_title {
                font-size: 16px;
                font-weight: bold;
            }
            QLabel#dlg_info {
                font-size: 11px;
                color: #6c7086;
            }
            QFrame#dlg_sep {
                color: #313244;
            }
            QSpinBox {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 13px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 18px;
                background-color: #45475a;
                border: none;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #585b70;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 7px 18px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
            QPushButton#dlg_save {
                background-color: #89b4fa;
                color: #1e1e2e;
                border: none;
                font-weight: bold;
            }
            QPushButton#dlg_save:hover {
                background-color: #74c7ec;
            }
            QRadioButton {
                color: #cdd6f4;
                font-size: 13px;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid #45475a;
                background-color: #313244;
            }
            QRadioButton::indicator:checked {
                background-color: #89b4fa;
                border-color: #89b4fa;
            }
            QRadioButton::indicator:hover {
                border-color: #89b4fa;
            }
            QMessageBox {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
        """)


# ============================================================================
# MAIN WINDOW
# ============================================================================

class NowPlayingWindow(QWidget):
    def __init__(self, tray_ref=None):
        super().__init__()
        self.tray_ref = tray_ref
        self._tray_notified = False
        self._current_cover_url = ''
        self._updating_combo = False

        self.setWindowTitle('Now Playing Overlay')
        self.setMinimumWidth(520)
        self.setWindowIcon(load_app_icon())

        self._setup_ui()
        self._apply_style()

        self._nam = QNetworkAccessManager(self)
        self._nam.finished.connect(self._on_cover_loaded)

    # ------------------------------------------------------------------
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # ── Top row: cover + info ──────────────────────────────────────
        top_layout = QHBoxLayout()
        top_layout.setSpacing(20)

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(160, 160)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setObjectName('cover')
        self._set_default_cover()
        top_layout.addWidget(self.cover_label)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(6)
        info_layout.setContentsMargins(0, 4, 0, 4)

        self.state_label = QLabel('STOPPED')
        self.state_label.setObjectName('state')

        self.title_label = QLabel('\u2014')
        self.title_label.setObjectName('title')
        self.title_label.setWordWrap(True)

        self.artist_label = QLabel('\u2014')
        self.artist_label.setObjectName('artist')

        self.album_label = QLabel('')
        self.album_label.setObjectName('album')
        self.album_label.setVisible(False)

        info_layout.addWidget(self.state_label)
        info_layout.addSpacing(4)
        info_layout.addWidget(self.title_label)
        info_layout.addWidget(self.artist_label)
        info_layout.addWidget(self.album_label)
        info_layout.addStretch()

        top_layout.addLayout(info_layout, 1)
        main_layout.addLayout(top_layout)

        # ── Progress bar + time ────────────────────────────────────────
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        progress_layout.addWidget(self.progress_bar, 1)

        self.time_label = QLabel('0:00 / 0:00')
        self.time_label.setObjectName('time')
        progress_layout.addWidget(self.time_label)

        main_layout.addLayout(progress_layout)

        # ── Bottom row: source selector + server status ────────────────
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        source_lbl = QLabel('Source:')
        source_lbl.setObjectName('label')
        bottom_layout.addWidget(source_lbl)

        self.source_combo = QComboBox()
        self.source_combo.addItem('Automatic', None)
        self.source_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        bottom_layout.addWidget(self.source_combo, 1)

        self.status_label = QLabel('WS: 0 client')
        self.status_label.setObjectName('status')
        bottom_layout.addWidget(self.status_label)

        self.settings_btn = QPushButton('⚙')
        self.settings_btn.setObjectName('settings_btn')
        self.settings_btn.setFixedSize(30, 30)
        self.settings_btn.setToolTip('Settings')
        self.settings_btn.clicked.connect(self.open_settings)
        bottom_layout.addWidget(self.settings_btn)

        main_layout.addLayout(bottom_layout)

    # ------------------------------------------------------------------
    def _apply_style(self):
        self.setStyleSheet("""
            NowPlayingWindow {
                background-color: #1e1e2e;
            }
            QLabel {
                color: #cdd6f4;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel#title {
                font-size: 17px;
                font-weight: bold;
            }
            QLabel#artist {
                font-size: 14px;
                color: #89b4fa;
            }
            QLabel#album {
                font-size: 12px;
                color: #6c7086;
            }
            QLabel#state {
                font-size: 11px;
                font-weight: bold;
                color: #a6e3a1;
                letter-spacing: 1px;
            }
            QLabel#time {
                font-size: 11px;
                color: #6c7086;
            }
            QLabel#label {
                font-size: 12px;
                color: #6c7086;
            }
            QLabel#status {
                font-size: 11px;
                color: #6c7086;
            }
            QLabel#cover {
                background-color: #313244;
                border-radius: 12px;
            }
            QProgressBar {
                background-color: #313244;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #89b4fa;
                border-radius: 4px;
            }
            QComboBox {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 12px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #313244;
                color: #cdd6f4;
                selection-background-color: #45475a;
            }
            QPushButton#settings_btn {
                background-color: #313244;
                color: #6c7086;
                border: 1px solid #45475a;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton#settings_btn:hover {
                background-color: #45475a;
                color: #cdd6f4;
            }
        """)

    # ------------------------------------------------------------------
    def _set_default_cover(self):
        pixmap = QPixmap(160, 160)
        pixmap.fill(QColor('#313244'))
        painter = QPainter(pixmap)
        font = QFont()
        font.setPixelSize(64)
        painter.setFont(font)
        painter.setPen(QPen(QColor('#6c7086')))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, '\u266b')
        painter.end()
        self.cover_label.setPixmap(pixmap)

    # ------------------------------------------------------------------
    def update_media(self, media_info: dict):
        state = media_info.get('state', 'STOPPED')

        state_colors = {'PLAYING': '#a6e3a1', 'PAUSED': '#f9e2af', 'STOPPED': '#f38ba8'}
        state_icons = {'PLAYING': '\u25b6', 'PAUSED': '\u23f8', 'STOPPED': '\u23f9'}
        color = state_colors.get(state, '#cdd6f4')
        icon = state_icons.get(state, '')
        self.state_label.setText(f'{icon}  {state}')
        self.state_label.setStyleSheet(
            f'font-size: 10px; font-weight: bold; color: {color};'
        )

        self.title_label.setText(media_info.get('title') or '\u2014')
        self.artist_label.setText(media_info.get('artist') or '\u2014')
        album = media_info.get('album') or ''
        self.album_label.setText(album)
        self.album_label.setVisible(bool(album))

        percent = media_info.get('position_percent', 0)
        self.progress_bar.setValue(int(percent * 10))
        pos_str = media_info.get('position', '0:00')
        dur_str = media_info.get('duration', '0:00')
        self.time_label.setText(f'{pos_str} / {dur_str}')

        n = len(clients)
        self.status_label.setText(f'WS: {n} client{"s" if n > 1 else ""}')

        cover_url = media_info.get('cover_url', '')
        if cover_url and cover_url != self._current_cover_url:
            self._current_cover_url = cover_url
            self._nam.get(QNetworkRequest(QUrl(cover_url)))
        elif not cover_url:
            self._current_cover_url = ''
            self._set_default_cover()

    # ------------------------------------------------------------------
    def update_players(self, players: list):
        """Refreshes the source ComboBox; preserves current selection."""
        self._updating_combo = True

        # On first population (only "Automatic" present), apply saved config.
        # After that, preserve the user's current in-app choice.
        if self.source_combo.count() <= 1:
            target_data = selected_player
        else:
            target_data = self.source_combo.currentData()

        self.source_combo.clear()
        for display, app_id in players:
            self.source_combo.addItem(display, app_id)

        restored = False
        for i in range(self.source_combo.count()):
            if self.source_combo.itemData(i) == target_data:
                self.source_combo.setCurrentIndex(i)
                restored = True
                break
        if not restored:
            self.source_combo.setCurrentIndex(0)

        self._updating_combo = False

        if self.tray_ref:
            self.tray_ref.refresh_players_menu(players)

    # ------------------------------------------------------------------
    def set_selected_player(self, app_id):
        """Called from the tray menu to sync the combo."""
        self._updating_combo = True
        for i in range(self.source_combo.count()):
            if self.source_combo.itemData(i) == app_id:
                self.source_combo.setCurrentIndex(i)
                break
        self._updating_combo = False

    # ------------------------------------------------------------------
    def _on_source_changed(self, _):
        if self._updating_combo:
            return
        global selected_player
        selected_player = self.source_combo.currentData()
        save_config({'selected_player': selected_player})
        if self.tray_ref:
            self.tray_ref.update_source_check(selected_player)

    # ------------------------------------------------------------------
    def open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    # ------------------------------------------------------------------
    def _on_cover_loaded(self, reply):
        data = reply.readAll()
        if data:
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    160, 160,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                # Center-crop to exactly 160×160
                x = (pixmap.width() - 160) // 2
                y = (pixmap.height() - 160) // 2
                pixmap = pixmap.copy(x, y, 160, 160)

                # Rounded corners
                rounded = QPixmap(160, 160)
                rounded.fill(Qt.GlobalColor.transparent)
                p = QPainter(rounded)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setBrush(QBrush(pixmap))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(0, 0, 160, 160, 12, 12)
                p.end()

                self.cover_label.setPixmap(rounded)
        reply.deleteLater()

    # ------------------------------------------------------------------
    def closeEvent(self, event):
        event.ignore()
        self.hide()
        if not self._tray_notified and self.tray_ref:
            self._tray_notified = True
            self.tray_ref.showMessage(
                'Now Playing Overlay',
                "The application is still running in the system tray.\n"
                "Double-click the icon to reopen.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )


# ============================================================================
# SYSTEM TRAY
# ============================================================================

class TrayApp(QSystemTrayIcon):
    def __init__(self, window: NowPlayingWindow):
        super().__init__(load_app_icon(), window)
        self.window = window
        self._players: list = [('Automatic', None)]
        self._player_actions: list = []

        self._build_menu()
        self.activated.connect(self._on_activated)
        self.setToolTip('Now Playing Overlay')
        self.show()

    # ------------------------------------------------------------------
    def _build_menu(self):
        self._menu = QMenu()

        header = self._menu.addAction('\u266b Now Playing Overlay')
        header.setEnabled(False)
        self._menu.addSeparator()

        open_action = self._menu.addAction('Open')
        open_action.triggered.connect(self._show_window)
        self._menu.addSeparator()

        self._source_menu = self._menu.addMenu('Source')
        self._rebuild_source_menu()
        self._menu.addSeparator()

        settings_action = self._menu.addAction('Settings…')
        settings_action.triggered.connect(self._open_settings)
        self._menu.addSeparator()

        quit_action = self._menu.addAction('Quit')
        quit_action.triggered.connect(self._quit)

        self.setContextMenu(self._menu)

    # ------------------------------------------------------------------
    def _rebuild_source_menu(self):
        self._source_menu.clear()
        self._player_actions = []
        for display, app_id in self._players:
            action = QAction(display, self._source_menu)
            action.setCheckable(True)
            action.setChecked(app_id == selected_player)
            action.setData(app_id)
            action.triggered.connect(
                lambda _, aid=app_id: self._on_source_selected(aid)
            )
            self._source_menu.addAction(action)
            self._player_actions.append(action)

    # ------------------------------------------------------------------
    def refresh_players_menu(self, players: list):
        self._players = players
        self._rebuild_source_menu()

    def update_source_check(self, app_id):
        for action in self._player_actions:
            action.setChecked(action.data() == app_id)

    # ------------------------------------------------------------------
    def _on_source_selected(self, app_id):
        global selected_player
        selected_player = app_id
        save_config({'selected_player': selected_player})
        self.update_source_check(app_id)
        self.window.set_selected_player(app_id)

    def _open_settings(self):
        self._show_window()
        self.window.open_settings()

    def _show_window(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def _quit(self):
        global running
        running = False
        QApplication.instance().quit()


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    # Load saved config
    config = load_config()
    selected_player = config.get('selected_player')
    WS_PORT = config.get('ws_port', 6534)
    HTTP_PORT = config.get('http_port', 6535)
    if config.get('bind_all', False):
        BIND_HOST = '0.0.0.0'
        COVER_HOST = get_local_ip()
    else:
        BIND_HOST = '127.0.0.1'
        COVER_HOST = '127.0.0.1'

    # Start asyncio server in a background daemon thread
    server_loop = asyncio.new_event_loop()
    server_thread = threading.Thread(
        target=run_server, args=(server_loop,), daemon=True
    )
    server_thread.start()

    # Start Qt application
    app = QApplication(sys.argv)
    app.setApplicationName('Now Playing Overlay')
    app.setQuitOnLastWindowClosed(False)  # keep alive when window is closed

    # Build UI (tray needs a reference to window and vice-versa)
    window = NowPlayingWindow()
    tray = TrayApp(window)
    window.tray_ref = tray

    # Qt timers to drain the thread-safe queues
    def poll_media():
        try:
            while True:
                info = media_queue.get_nowait()
                window.update_media(info)
        except queue.Empty:
            pass

    def poll_players():
        try:
            while True:
                players = players_queue.get_nowait()
                window.update_players(players)
        except queue.Empty:
            pass

    media_timer = QTimer()
    media_timer.timeout.connect(poll_media)
    media_timer.start(100)

    players_timer = QTimer()
    players_timer.timeout.connect(poll_players)
    players_timer.start(500)

    window.show()
    sys.exit(app.exec())
