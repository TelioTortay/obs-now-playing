# 🎵 Now Playing Overlay

A beautiful, lightweight "Now Playing" widget for OBS Studio and streaming software.

**Cross-platform** • **Real-time** • **Zero configuration**

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)
[![Flatpak](https://img.shields.io/badge/flatpak-available-blue)](https://teliotortay.github.io/obs-now-playing-flatpak/)

## ✨ Features

- 🎨 **Smooth animations** - Fade transitions for artwork, text, and progress
- 📊 **Beautiful CLI dashboard** - Real-time display in your terminal
- 🖼️ **Album artwork** - Automatically fetches and displays cover art
- ⚡ **Low latency** - Updates every 200ms for responsive display
- 🔄 **Auto-reconnect** - Handles disconnections gracefully
- 🌍 **Cross-platform** - Works on Windows and Linux with zero config
- 🎯 **Universal support** - Works with any media player (Spotify, Deezer, VLC, etc.)
- 🎭 **Customizable** - Easy color and style customization

## 🖼️ Screenshots
# Widget
![Widget](https://github.com/TelioTortay/obs-now-playing/blob/main/screenshots/widget.png)

# Dashboard
Linux             |  Windows
:-------------------------:|:-------------------------:
![](https://github.com/TelioTortay/obs-now-playing/blob/main/screenshots/dashboard-linux.png)  |  ![](https://github.com/TelioTortay/obs-now-playing/blob/main/screenshots/dashboard-win.png)

## 🚀 Quick Start

### Linux (Flatpak)

The easiest way to install on Linux:

```bash
flatpak remote-add --user obs-now-playing https://teliotortay.github.io/obs-now-playing-flatpak/obs-now-playing.flatpakrepo
flatpak install obs-now-playing io.github.TelioTortay.ObsNowPlaying
flatpak run io.github.TelioTortay.ObsNowPlaying
```

**⚠️ Important:** Do not use the "Open" button in GNOME Software Center. Launch from terminal (command above) or from your application menu.

**Widget Location:** Download the HTML widget here: [releases page](https://github.com/teliotortay/obs-now-playing/releases)

[More details on the Flatpak repository →](https://teliotortay.github.io/obs-now-playing-flatpak/)

### Windows (Standalone Executable)

The easiest way to run on Windows:

1. Download the latest `NowPlayingServer.exe` from [Releases](https://github.com/teliotortay/obs-now-playing/releases)
2. Double-click to run (a terminal window will open with the server)
3. Download `now-playing-widget.html` from the same release
4. Add it to OBS (see instructions below)

No installation required - just download and run!

### From Source

#### Prerequisites

- **Python 3.8+**
- **OBS Studio** (or any streaming software with browser sources)
- **A media player** (Spotify, Deezer, VLC, etc.)

### Installation

**Linux (Flatpak - Recommended):**

```bash
# Add the repository
flatpak remote-add --user obs-now-playing https://teliotortay.github.io/obs-now-playing-flatpak/obs-now-playing.flatpakrepo

# Install
flatpak install obs-now-playing io.github.TelioTortay.ObsNowPlaying

# Run
flatpak run io.github.TelioTortay.ObsNowPlaying
```

Or launch **OBS Now Playing** from your application menu!

More info: [Flatpak Repository](https://teliotortay.github.io/obs-now-playing-flatpak/)

**Windows / Manual Installation:**

1. **Clone the repository**
   ```bash
   git clone https://github.com/teliotortay/obs-now-playing.git
   cd obs-now-playing
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   
   The installer automatically detects your OS and installs the correct backend:
   - **Windows**: Windows Media Control (WMC)
   - **Linux**: MPRIS

3. **Run the server**
   ```bash
   python server.py
   ```
   
   You should see a beautiful dashboard in your terminal! 🎉

### Add to OBS

1. In OBS, add a **Browser Source**
2. Configure:
   - ✅ **Local file**: Checked
   - 📁 **Local file path**: 
     - **Linux (Flatpak)**: `~/.var/app/io.github.TelioTortay.ObsNowPlaying/share/obs-now-playing/widget.html`
     - **Windows**: Browse to the downloaded `now-playing-widget.html`
     - **From source**: Browse to `now-playing-widget.html` in your project folder
   - 📏 **Width**: `1800`
   - 📏 **Height**: `450`
3. In your scene, **resize the source to 600×150** for crisp rendering
4. Done! The widget auto-connects and displays your music

## 🎨 Customization

### Colors

Edit `now-playing-widget.html` and change the CSS variables:

```css
:root {
    --zoom-level: 3;           /* Resolution multiplier (1-4) */
    --bg-color: #1e1e1e;       /* Widget background */
    --progress-bg: #2a2a2a;    /* Progress bar background */
    --progress-active: #4a9eff; /* Progress bar color */
}
```

### Fonts

The widget uses **Montserrat** from Google Fonts (free for all uses).

To use a different font:
1. Replace the `@import` URL in the `<style>` section
2. Update `font-family` properties in the CSS

## ⚙️ Configuration

### Server Ports

Edit `server.py` to change default ports:

```python
WS_PORT = 6534   # WebSocket for widget data
HTTP_PORT = 6535 # HTTP for album artwork
```

### High DPI / 4K Displays

The widget renders at 3× resolution by default for crisp display. Adjust if needed:

```css
--zoom-level: 3;  /* 1 = normal, 2 = 2K, 3 = 4K, 4 = 8K */
```

## 🐛 Troubleshooting

### Widget shows nothing

- ✅ Make sure the server is running (`python server.py`)
- ✅ Check that a media player is playing music
- ✅ Verify browser source dimensions: **1800×450**
- ✅ Try refreshing the browser source in OBS

### No album artwork

- **Windows**: Some apps don't provide artwork via WMC. Works best with Spotify Desktop, Deezer Desktop, VLC
- **Linux**: Player must support MPRIS artwork. **Works with**: VLC, Spotify, Deezer Desktop, Rhythmbox
- **Doesn't work**: Chrome/Chromium (buggy MPRIS implementation)
- Check the server dashboard - it shows if artwork is available

### Server won't start

**Windows:**
```bash
pip install winsdk
```

**Linux (Ubuntu/Debian):**
```bash
# Install system dependencies
sudo apt install python3-gi python3-gi-cairo gir1.2-glib-2.0 python3-pydbus

# Verify installation
python3 -c "import gi; from pydbus import SessionBus; print('OK')"
```

**Linux (Arch):**
```bash
sudo pacman -S python-gobject python-dbus
pip install pydbus
```

**Linux (Fedora):**
```bash
sudo dnf install python3-gobject python3-dbus
pip install pydbus
```

### Widget not connecting

- Check the browser console (right-click source → Interact → F12)
- Verify the server is running and shows "Connected clients: 0"
- Make sure no firewall is blocking localhost connections

### Linux: No playback detected

- **Supported players**: VLC, Spotify, Deezer Desktop, Rhythmbox, Audacious
- **Not supported**: Chrome/Chromium (broken MPRIS), web players in browsers
- Verify your player supports MPRIS:
  ```bash
  dbus-send --session --dest=org.freedesktop.DBus --type=method_call --print-reply /org/freedesktop/DBus org.freedesktop.DBus.ListNames > /tmp/dbus.txt
  grep mpris /tmp/dbus.txt
  ```
- If nothing shows up, your player doesn't support MPRIS

## 📖 How It Works

```
Media Player (Spotify/VLC/etc.)
         ↓
OS Media Control (WMC/MPRIS)
         ↓
Python Server (WebSocket + HTTP)
         ↓
OBS Browser Source (Widget)
```

**Server:**
- Reads media info from your OS every 200ms
- Extracts and serves album artwork via HTTP
- Broadcasts updates to widgets via WebSocket
- Displays a real-time dashboard

**Widget:**
- Connects to server via WebSocket
- Receives updates and animates smoothly
- Loads artwork from HTTP endpoint
- Auto-reconnects on disconnection

## 🔧 Advanced Usage

### Multiple Instances

Run multiple servers on different ports:

1. Copy `server.py` to `server2.py`
2. Edit ports: `WS_PORT = 6536`, `HTTP_PORT = 6537`
3. Update widget to connect to new port
4. Run both servers simultaneously

### Custom Themes

Create new themes by copying `now-playing-widget.html`:

1. Duplicate the file: `now-playing-widget-mytheme.html`
2. Modify colors, fonts, layout
3. Share your theme! (See CONTRIBUTING.md)

### Streaming Software

Works with:
- ✅ OBS Studio
- ✅ Streamlabs Desktop
- ✅ XSplit
- ✅ Any software supporting browser sources

## 🤝 Contributing

This is a personal project with **limited maintenance**.

- 🐛 **Bug reports**: Welcome! Open an issue
- ✨ **Feature requests**: Feel free to suggest, but no guarantees
- 🔧 **Pull requests**: Appreciated! I'll review when possible
- 🎨 **Themes**: Submit new themes, they'll likely get merged

**No support SLA.** This is hobby time, not a product. Fork freely!

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📜 License

MIT License - see [LICENSE](LICENSE) for details.

Uses **Montserrat** font from Google Fonts ([Open Font License](https://scripts.sil.org/OFL)) - free for all uses.

## 💡 Tips

- **Performance**: The server uses ~20MB RAM and negligible CPU
- **Compatibility**: Tested on Windows 10/11 and Ubuntu/Debian/Arch Linux
- **Privacy**: All data stays local - no internet connection required
- **Customization**: All CSS is in the HTML file for easy tweaking

### Supported Media Players

**Windows (WMC):**
- ✅ Spotify Desktop
- ✅ Deezer Desktop
- ✅ VLC
- ✅ Windows Media Player
- ✅ iTunes
- ❌ Web players (Spotify Web, YouTube Music in browser)

**Linux (MPRIS):**
- ✅ VLC
- ✅ Spotify (Desktop/Snap/Flatpak)
- ✅ Deezer Desktop
- ✅ Rhythmbox
- ✅ Audacious
- ✅ Clementine
- ❌ Chrome/Chromium (buggy MPRIS implementation)
- ❌ Web players

## ⭐ Support

If you find this useful:
- ⭐ Star the repo
- 🐛 Report bugs when you find them
- 🔧 Submit PRs if you fix/improve something
- 📣 Share with other streamers

**Built by a streamer, for streamers. Enjoy! 🎮🎵**

---

*No support guarantees, but I'll help when I can!*
