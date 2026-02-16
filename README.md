# 🎵 Now Playing Overlay

A beautiful, lightweight "Now Playing" widget for OBS Studio and streaming software.

**Cross-platform** • **Real-time** • **Zero configuration**

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)
[![Flatpak](https://img.shields.io/badge/flatpak-available-blue)](https://teliotortay.github.io/obs-now-playing-flatpak/)

## ✨ Features

- 🖥️ **System tray app** - Runs quietly in your system tray with a clean GUI window
- 🖼️ **Album artwork** - Automatically fetches and displays cover art
- ⚡ **Low latency** - Updates every 200ms for responsive display
- 🔄 **Auto-reconnect** - Handles disconnections gracefully
- 🌍 **Cross-platform** - Works on Windows and Linux with zero config
- 🎯 **Universal support** - Works with any media player (Spotify, Deezer, VLC, etc.)
- ⚙️ **Settings UI** - Configure ports and network mode without editing any file
- 🌐 **LAN mode** - Optionally expose the server on your local network

## 🖼️ Screenshots
# Widget
![Widget](https://github.com/TelioTortay/obs-now-playing/blob/main/screenshots/widget.png)

# Dashboard
Linux             |  Windows
:-------------------------:|:-------------------------:
![](https://github.com/TelioTortay/obs-now-playing/blob/main/screenshots/dashboard-linux.png)  |  ![](https://github.com/TelioTortay/obs-now-playing/blob/main/screenshots/dashboard-win.png)

## 🚀 Quick Start

### Linux (Flatpak — recommended)

```bash
flatpak remote-add --user obs-now-playing https://teliotortay.github.io/obs-now-playing-flatpak/obs-now-playing.flatpakrepo
flatpak install obs-now-playing io.github.TelioTortay.ObsNowPlaying
flatpak run io.github.TelioTortay.ObsNowPlaying
```

Or launch **OBS Now Playing** directly from your application menu/Software Center.

**Widget:** Download `now-playing-widget.html` from the [releases page](https://github.com/teliotortay/obs-now-playing/releases).

[More details on the Flatpak repository →](https://teliotortay.github.io/obs-now-playing-flatpak/)

---

### Windows (Standalone Executable)

1. Download the latest `NowPlayingServer.exe` from [Releases](https://github.com/teliotortay/obs-now-playing/releases)
2. Double-click to run — the app appears in your **system tray**
3. Download `now-playing-widget.html` from the same release
4. Add it to OBS (see instructions below)

No installation required — just download and run!

---

### From Source

**Prerequisites:** Python 3.8+, OBS Studio, a media player

```bash
git clone https://github.com/teliotortay/obs-now-playing.git
cd obs-now-playing
pip install -r requirements.txt
python server/now-playing-server.py
```

The installer automatically detects your OS and installs the correct backend:
- **Windows**: Windows Media Control (WMC)
- **Linux**: MPRIS

## 📺 Add to OBS

1. In OBS, add a **Browser Source**
2. Configure:
   - ✅ **Local file**: Checked
   - 📁 **File path**: Browse to the downloaded `now-playing-widget.html`
   - 📏 **Width**: `1800`
   - 📏 **Height**: `450`
3. In your scene, **resize the source to 600×150** for crisp rendering
4. Done! The widget auto-connects and displays your music

## ⚙️ Configuration

All settings are accessible via the **⚙ button** in the app window or via **Paramètres…** in the system tray menu — no need to edit any file.

### Ports

| Port | Default | Purpose |
|------|---------|---------|
| WebSocket | `6534` | Real-time data sent to the widget |
| HTTP | `6535` | Album artwork served to the widget |

### Network mode

| Mode | Binding | Use case |
|------|---------|---------|
| Localhost (default) | `127.0.0.1` | OBS on the same machine |
| Local network | `0.0.0.0` | OBS on another PC on the same LAN |

In local network mode, the cover art URL sent to clients automatically uses the detected LAN IP of the server machine.

> Changes take effect on the next application restart.

### Widget appearance

Edit `now-playing-widget.html` and change the CSS variables:

```css
:root {
    --zoom-level: 3;            /* Resolution multiplier (1–4) */
    --bg-color: #1e1e1e;        /* Widget background */
    --progress-bg: #2a2a2a;     /* Progress bar background */
    --progress-active: #4a9eff; /* Progress bar color */
}
```

### High DPI / 4K Displays

The widget renders at 3× resolution by default for crisp display. Adjust `--zoom-level` if needed:

```css
--zoom-level: 3;  /* 1 = normal, 2 = 2K, 3 = 4K, 4 = 8K */
```

## 🐛 Troubleshooting

### Widget shows nothing

- ✅ Make sure the app is running (tray icon visible)
- ✅ Check that a media player is playing music
- ✅ Verify browser source dimensions: **1800×450**
- ✅ Try refreshing the browser source in OBS (right-click → Refresh)

### No album artwork

- **Windows**: Some apps don't provide artwork via WMC. Works best with Spotify Desktop, Deezer Desktop, VLC
- **Linux**: Player must support MPRIS artwork — works with VLC, Spotify, Deezer Desktop, Rhythmbox
- Chrome/Chromium: **not supported** (buggy MPRIS implementation)

### Server won't start

**Windows:**
```bash
pip install winsdk PySide6
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-glib-2.0 python3-pydbus
pip install PySide6
python3 -c "import gi; from pydbus import SessionBus; print('OK')"
```

**Linux (Arch):**
```bash
sudo pacman -S python-gobject python-dbus
pip install pydbus PySide6
```

**Linux (Fedora):**
```bash
sudo dnf install python3-gobject python3-dbus
pip install pydbus PySide6
```

### Widget not connecting

- Check the browser console (right-click source → Interact → F12)
- Make sure no firewall is blocking the configured ports
- If using **local network mode**, make sure your firewall allows inbound connections on the WebSocket and HTTP ports

### Linux: No playback detected

- **Supported players**: VLC, Spotify, Deezer Desktop, Rhythmbox, Audacious, Clementine
- **Not supported**: Chrome/Chromium (broken MPRIS)
- Verify your player supports MPRIS:
  ```bash
  dbus-send --session --dest=org.freedesktop.DBus --type=method_call --print-reply \
    /org/freedesktop/DBus org.freedesktop.DBus.ListNames | grep -i mpris
  ```

## 📖 How It Works

```
Media Player (Spotify / VLC / etc.)
         ↓
OS Media Control (WMC on Windows · MPRIS on Linux)
         ↓
Python Server  ──  System tray GUI  ──  Settings (ports, network)
         ↓
OBS Browser Source (Widget HTML)
```

- The server polls media info every 200ms and broadcasts it to connected widgets via **WebSocket**
- Album artwork is extracted and served locally via **HTTP**
- The widget auto-connects, animates smoothly, and auto-reconnects on disconnection

## 🔧 Advanced Usage

### Multiple Instances

To run two widgets simultaneously (e.g., two different players):

1. Copy the server script and launch a second instance
2. Open **Settings** (⚙) and assign different WebSocket and HTTP ports to each instance
3. Point each widget HTML file to its corresponding port

### Custom Themes

1. Duplicate `now-playing-widget.html` → `now-playing-widget-mytheme.html`
2. Modify colors, fonts, layout in the CSS section
3. Add it as a separate browser source in OBS

### Streaming Software

Works with any software supporting browser sources:
- ✅ OBS Studio
- ✅ Streamlabs Desktop
- ✅ XSplit

## 🎮 Supported Media Players

**Windows (WMC):**
- ✅ Spotify Desktop
- ✅ Deezer Desktop
- ✅ VLC
- ✅ Windows Media Player
- ✅ iTunes
- 🟨 Web players (depends on the browser)

**Linux (MPRIS):**
- ✅ VLC
- ✅ Spotify (Desktop / Snap / Flatpak)
- ✅ Deezer Desktop
- ✅ Rhythmbox
- ✅ Audacious
- ✅ Clementine
- ❌ Chrome/Chromium (buggy MPRIS implementation)
- ❌ Web players

## 🤝 Contributing

This is a personal project with **limited maintenance**.

- 🐛 **Bug reports**: Welcome! Open an issue
- ✨ **Feature requests**: Feel free to suggest, no guarantees
- 🔧 **Pull requests**: Appreciated, I'll review when possible
- 🎨 **Themes**: Submit new themes, they'll likely get merged

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📜 License

MIT License — see [LICENSE](LICENSE) for details.

Uses **Montserrat** font from Google Fonts ([Open Font License](https://scripts.sil.org/OFL)) — free for all uses.

## 💡 Tips

- **Performance**: The server uses ~70 MB RAM and negligible CPU
- **Compatibility**: Tested on Windows 10/11 and Ubuntu / Debian / Arch Linux
- **Privacy**: All data stays local — no internet connection required
- **Config file**: Settings are saved in `config.json` next to the executable

## ⭐ Support

If you find this useful:
- ⭐ Star the repo
- 🐛 Report bugs when you find them
- 🔧 Submit PRs if you fix or improve something
- 📣 Share with other streamers

**Built by a streamer, for streamers. Enjoy! 🎮🎵**

---

*No support guarantees, but I'll help when I can!*
