#!/usr/bin/env python3
"""
Custom Now Playing Server
Lit Windows Media Control et expose les données via WebSocket
Serveur HTTP pour les pochettes d'album
"""

import asyncio
import json
import signal
import sys
from datetime import datetime
from pathlib import Path
import shutil

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
    print("❌ Erreur: modules manquants")
    print("Installez avec: pip install websockets aiohttp rich")
    sys.exit(1)

try:
    from winsdk.windows.media.control import \
        GlobalSystemMediaTransportControlsSessionManager as MediaManager
except ImportError:
    print("❌ Erreur: winsdk non installé")
    print("Installez avec: pip install winsdk")
    sys.exit(1)

# Ports
WS_PORT = 6534
HTTP_PORT = 6535

# Clients connectés
clients = set()

# Flag pour arrêt propre
running = True

# Tracker du dernier titre pour éviter de recharger la cover
last_cover_title = ''
cover_timestamp = 0

# Console rich pour le dashboard
console = Console()

# Dernières infos média pour l'affichage
current_media_info = None

# Dossier pour les covers
COVER_DIR = Path.home() / "AppData" / "Local" / "Temp" / "NowPlayingCovers"
COVER_DIR.mkdir(parents=True, exist_ok=True)
CURRENT_COVER = COVER_DIR / "current.jpg"

async def get_media_info():
    """Récupère les infos depuis Windows Media Control"""
    global current_media_info
    
    try:
        sessions = await MediaManager.request_async()
        current_session = sessions.get_current_session()
        
        if current_session is None:
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
        
        # Récupérer les infos
        info = await current_session.try_get_media_properties_async()
        playback_info = current_session.get_playback_info()
        timeline = current_session.get_timeline_properties()
        
        # État de lecture
        state = 'STOPPED'
        if playback_info.playback_status == 4:  # Playing
            state = 'PLAYING'
        elif playback_info.playback_status == 3:  # Paused
            state = 'PAUSED'
        
        # Durée et position
        duration_sec = 0
        position_sec = 0
        
        if timeline.end_time:
            duration_sec = int(timeline.end_time.total_seconds())
        
        if timeline.position:
            position_sec = int(timeline.position.total_seconds())
        
        # Format MM:SS
        def format_time(seconds):
            mins = seconds // 60
            secs = seconds % 60
            return f"{mins}:{secs:02d}"
        
        # Copier la cover seulement si le titre a changé
        global last_cover_title, cover_timestamp
        cover_url = ''
        current_title = info.title or ''
        
        # Vérifier si on doit mettre à jour la cover
        should_update_cover = current_title and current_title != last_cover_title
        
        if should_update_cover and info.thumbnail:
            try:
                # Lire via le stream
                stream = await info.thumbnail.open_read_async()
                if stream:
                    from winsdk.windows.storage.streams import DataReader
                    
                    # Utiliser DataReader pour lire le stream
                    reader = DataReader(stream)
                    
                    # Charger tout le stream
                    bytes_loaded = await reader.load_async(10 * 1024 * 1024)  # 10MB max
                    
                    if bytes_loaded > 0:
                        # Créer un bytearray pour recevoir les bytes
                        image_array = bytearray(bytes_loaded)
                        reader.read_bytes(image_array)
                        
                        # Sauvegarder dans un fichier
                        with open(CURRENT_COVER, 'wb') as f:
                            f.write(image_array)
                        
                        # Mettre à jour APRÈS avoir réussi à charger
                        last_cover_title = current_title
                        cover_timestamp = int(datetime.now().timestamp())
                    
                    reader.close()
                    stream.close()
                    
            except Exception as e:
                pass
        
        # Envoyer l'URL avec timestamp seulement quand la cover change
        if CURRENT_COVER.exists():
            cover_url = f"http://127.0.0.1:{HTTP_PORT}/cover.jpg?t={cover_timestamp}"
        
        return {
            'state': state,
            'player_name': current_session.source_app_user_model_id or '',
            'title': info.title or '',
            'artist': info.artist or '',
            'album': info.album_title or '',
            'cover_url': cover_url,
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
    
    except Exception as e:
        return None

# Wrapper pour mettre à jour current_media_info
async def get_and_cache_media_info():
    global current_media_info
    info = await get_media_info()
    if info:
        current_media_info = info
    return info

async def serve_cover(request):
    """Sert la pochette via HTTP"""
    if CURRENT_COVER.exists():
        return web.FileResponse(CURRENT_COVER)
    else:
        return web.Response(status=404)

def generate_dashboard():
    """Génère le dashboard CLI avec Rich"""
    global current_media_info
    
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=5)
    )
    
    # Header
    header_text = Text("♫ NOW PLAYING SERVER", style="bold magenta", justify="center")
    layout["header"].update(Panel(header_text, border_style="magenta"))
    
    # Body - Infos du morceau
    if current_media_info and current_media_info['state'] == 'PLAYING':
        info = current_media_info
        
        # Créer le tableau principal
        table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        table.add_column("Field", style="cyan", width=15)
        table.add_column("Value", style="white")
        
        # État
        state_emoji = "▶️" if info['state'] == 'PLAYING' else "⏸️" if info['state'] == 'PAUSED' else "⏹️"
        table.add_row("État", f"{state_emoji} {info['state']}")
        
        # Titre et artiste
        title = info['title'] or '-'
        artist = info['artist'] or '-'
        table.add_row("Titre", f"[bold yellow]{title}[/bold yellow]")
        table.add_row("Artiste", f"[bold green]{artist}[/bold green]")
        
        if info['album']:
            table.add_row("Album", info['album'])
        
        # Temps
        position = info['position']
        duration = info['duration']
        percent = info['position_percent']
        
        # Barre de progression
        bar_width = 40
        filled = int(bar_width * percent / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        table.add_row("Progression", f"{position} / {duration}")
        table.add_row("", f"[cyan]{bar}[/cyan] {percent:.1f}%")
        
        # Cover
        cover_status = "✓ Disponible" if info['cover_url'] else "✗ Non disponible"
        table.add_row("Pochette", cover_status)
        
        layout["body"].update(Panel(table, title="[bold]🎵 Lecture en cours[/bold]", border_style="cyan"))
    
    elif current_media_info and current_media_info['state'] == 'PAUSED':
        paused_text = Text("⏸️  EN PAUSE", style="bold yellow", justify="center")
        layout["body"].update(Panel(paused_text, border_style="yellow"))
    
    else:
        stopped_text = Text("⏹️  AUCUNE LECTURE", style="bold red", justify="center")
        layout["body"].update(Panel(stopped_text, border_style="red"))
    
    # Footer - Stats serveur
    stats_table = Table(show_header=False, box=None, padding=(0, 2))
    stats_table.add_column(style="dim")
    stats_table.add_column(style="dim")
    
    stats_table.add_row("WebSocket", f"ws://127.0.0.1:{WS_PORT}")
    stats_table.add_row("HTTP (covers)", f"http://127.0.0.1:{HTTP_PORT}")
    stats_table.add_row("Clients connectés", f"{len(clients)}")
    
    layout["footer"].update(Panel(stats_table, title="[dim]Serveur[/dim]", border_style="dim"))
    
    return layout

async def broadcast_updates(live):
    """Envoie les mises à jour à tous les clients"""
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
                # Mettre à jour quand même pour le dashboard
                await get_and_cache_media_info()
            
            # Mettre à jour le dashboard
            live.update(generate_dashboard())
            
            await asyncio.sleep(0.2)
        
        except Exception as e:
            await asyncio.sleep(1)

async def handle_client(websocket):
    """Gère une connexion client"""
    print(f"[Client] Connecté: {websocket.remote_address}")
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
    
    # Serveur HTTP pour les covers
    app = web.Application()
    app.router.add_get('/cover.jpg', serve_cover)
    runner = web.AppRunner(app)
    await runner.setup()
    http_site = web.TCPSite(runner, '127.0.0.1', HTTP_PORT)
    await http_site.start()
    
    # Serveur WebSocket
    ws_server = await websockets.serve(handle_client, "127.0.0.1", WS_PORT)
    
    # Lancer le dashboard avec Live
    with Live(generate_dashboard(), console=console, refresh_per_second=5) as live:
        # Démarrer le broadcast
        broadcast_task = asyncio.create_task(broadcast_updates(live))
        
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            pass
        
        # Nettoyage
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
        print("\nArrêté par l'utilisateur")
    except Exception as e:
        print(f"\nErreur fatale: {e}")
        sys.exit(1)
