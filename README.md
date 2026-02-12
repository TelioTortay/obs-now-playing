# 🎵 Custom Now Playing for OBS

A beautiful, lightweight, and reliable "Now Playing" widget for OBS Studio with real-time media control integration.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)

## ✨ Features

- 🎨 **Beautiful animated widget** with smooth transitions
- 📊 **Real-time CLI dashboard** showing current playback
- 🖼️ **Album artwork support** with fade animations
- ⚡ **Low latency** - updates every 200ms
- 🔄 **Auto-reconnect** - handles connection drops gracefully
- 🎯 **Native integration** - reads directly from Windows Media Control (MPRIS on Linux)
- 🎭 **Multiple themes** - customizable appearance
- 📱 **Works with any media player** - Deezer, Spotify, VLC, YouTube Music, etc.

## 🖼️ Screenshots

### Widget in OBS
*Insert screenshot of widget here*

### CLI Dashboard
*Insert screenshot of dashboard here*

## 📋 Requirements

- Python 3.8 or higher
- OBS Studio
- Windows 10/11 (or Linux with MPRIS support)
- A media player (Deezer, Spotify, VLC, etc.)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

**Requirements:**
- `websockets` - WebSocket server
- `aiohttp` - HTTP server for album artwork
- `winsdk` - Windows Media Control integration (Windows only)
- `rich` - Beautiful CLI dashboard

### 2. Run the Server

```bash
python server/now-playing-server.py
```

You should see a beautiful dashboard displaying:
- Current track information
- Playback progress bar
- Server status
- Connected clients count

### 3. Add Widget to OBS

1. In OBS, add a **Browser Source**
2. Configure it:
   - **Local file**: ✅ Checked
   - **Local file path**: Browse to `widget/now-playing-widget.html`
   - **Width**: `1800`
   - **Height**: `450`
3. Resize the source in your scene to `600x150` (for crisp 3x rendering)
4. Done! The widget will automatically connect and display your music

## 🎨 Customization

The widget uses CSS variables for easy color customization.

Edit `now-playing-widget.html`:

```css
:root {
    /* Zoom level for high resolution (1 = normal, 3 = 3x for crisp 4K) */
    --zoom-level: 3;
    
    /* Colors - customize these! */
    --bg-color: #1e1e1e;
    --progress-bg: #2a2a2a;
    --progress-active: #4a9eff;
}
```

**Font**: Uses Montserrat from Google Fonts (free, no license required).

## ⚙️ Configuration

### Server Ports

Edit `now-playing-server.py`:

```python
# Ports
WS_PORT = 6534  # WebSocket for widget data
HTTP_PORT = 6535  # HTTP for album artwork
```

## 🐛 Troubleshooting

### Widget shows nothing
- Make sure the server is running (`python now-playing-server.py`)
- Check that a media player is playing music
- Verify the browser source dimensions (1800x450)

### No album artwork
- Verify the media player supports artwork (Deezer Desktop, Spotify Desktop work well)
- Check the server logs for cover loading errors

### Server won't close properly
- Press `Ctrl+C` in the terminal
- The server should close cleanly with all resources freed

### OBS Browser Source shows a blank screen
- Right-click the source → **Interact**
- Press `F12` to open developer tools
- Check the Console tab for errors

## 🔧 Advanced Usage

### Custom Colors

Change the CSS variables at the top of `now-playing-widget.html`:
- `--bg-color`: Widget background
- `--progress-bg`: Progress bar background
- `--progress-active`: Progress bar fill color

### Custom Fonts

To use different fonts:
1. Replace the Google Fonts import URL
2. Update `font-family` properties in the CSS

### Multiple Widgets

Run multiple instances on different ports:
1. Copy the server script
2. Change `WS_PORT` and `HTTP_PORT`
3. Update widget connection port accordingly

## 🐧 Linux Support

Linux support via MPRIS is planned. The architecture is ready, only the media control backend needs to be swapped.

**To contribute Linux support:**
1. Replace `winsdk` with `pydbus` 
2. Implement MPRIS2 interface reading
3. Test with popular Linux media players

Pull requests welcome!

## 📝 How It Works

```
Media Player (Deezer/Spotify/etc.)
         ↓
Windows Media Control / MPRIS
         ↓
Python Server (WebSocket + HTTP)
         ↓
OBS Browser Source (Widget)
```

The server:
1. Reads media info from Windows Media Control every 200ms
2. Extracts album artwork and serves it via HTTP
3. Broadcasts updates to all connected widgets via WebSocket
4. Displays a real-time dashboard in the terminal

The widget:
1. Connects to the server via WebSocket
2. Receives updates and animates smoothly
3. Loads album artwork from the HTTP server
4. Handles disconnections and auto-reconnects

## 🤝 Contributing

This is a personal project shared with the community. While contributions are welcome, please note:

- **Limited maintenance**: I may not respond immediately to issues or PRs
- **Best effort support**: Use at your own risk, no guarantees
- **Community-driven**: Feel free to fork and adapt to your needs

If you want to contribute:
- **Bug fixes**: Always appreciated, open a PR
- **New features**: Fork the repo and go wild!
- **Linux support**: This would be amazing! See CONTRIBUTING.md
- **Themes**: Submit new themes, they'll likely get merged

**No expectations, no pressure.** This is a tool I built for myself and decided to share. If it helps you, awesome! If you improve it, even better!

## 📜 License

MIT License - see LICENSE file for details.

Uses Montserrat font (Google Fonts, Open Font License) - free for all uses.

## ⭐ Support

If you find this useful:
- ⭐ Star the repo
- 🐛 Report bugs (I'll fix when I can)
- 🔧 Submit PRs (I'll review when possible)
- 📣 Share with other streamers

**No support guarantees, but I'll do my best when time allows!**

---

**Built by a streamer, for streamers. Enjoy! 🎮🎵**
