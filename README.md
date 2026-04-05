Mr. Alvin Rocks - yt-dlp GUI & Section Downloader v2.0
The Final Edition

A powerful, Python-based graphical interface for yt-dlp designed for precision. This tool allows you to preview videos, set exact timestamps visually, and download high-bitrate video or audio sections without needing the command line.

🚀 Key Features
🎯 Visual Sectional Downloads: Use the built-in player to set exact start and end times. No more guessing timestamps.

📺 In-App Video Previewer: Powered by VLC, featuring a YouTube-style interactive timeline with hover-tooltips for frame-perfect seeking.

🌐 Integrated YouTube Browser: A built-in Edge-based browser (WebView2) that allows you to browse YouTube and send links directly to the downloader or previewer with one click.

👻 Phantom Menu: A smart, invisible menu that detects when you copy a YouTube link to your clipboard and pops up at your mouse cursor for instant action.

⏸️ Pause & Resume: Fully supports pausing active downloads and resuming them later, including child processes like FFmpeg.

💎 Max Quality Bitrate: Automatically unlocks the highest available bitrates (VP9/AV1) for 1080p, 2K, and 4K downloads.

📑 Smart Playlist Downloader: Fetch entire playlists and select specifically which videos you want to download as MP4, MP3, or both.

🔍 Format Explorer: A technical deep-dive tool to view every available stream (resolution, FPS, bitrate, and size) for a specific URL.

🍪 Cookie & Account Support: Supports importing cookies from Edge, Chrome, Firefox, or a cookies.txt file to download age-restricted or private content.

🎨 Dynamic Themes & UI: Features an animated "breathing" rainbow header and multiple themes (Black, Light, Blue, Purple).

✅ Prerequisites
Before running the application, ensure your system has the following installed:

VLC Media Player: Required for the In-App Previewer.

FFmpeg: Required for merging video/audio and processing section cuts.

Node.js: Recommended to help yt-dlp solve complex YouTube JavaScript signature challenges.

⚙️ Installation & Setup
This version features V1.6 Automatic Setup. On the first run, the app will:

Automatically install required Python libraries (yt-dlp, tkwebview2, pillow, psutil, python-vlc).

Attempt to install FFmpeg and VLC via winget if they are missing (Windows only).

Manual Install:

Bash
pip install yt-dlp tkwebview2 pillow psutil python-vlc nodejs-bin[cmd]
🚀 Usage
1. The Main Dashboard
Paste Link: Paste a URL or let the Auto-Grab feature pull it from your clipboard automatically.

Set Times: Manually enter Start/End times or click Open In-App Player to set them visually.

Download: Choose your resolution (up to 2160p) or audio bitrate (up to 320kbps) and hit Video or Audio.

2. The In-App Previewer
Watch the video directly in the app.

Click [Set as Start] or [Set as End] while the video is playing to capture the current timestamp instantly.

Use the Playlist button in the previewer to download other items from the same series without leaving the window.

3. The Integrated Browser
Click 🌐 Browser to open the built-in YouTube window.

When you find a video you like, click the action buttons at the bottom to send the URL to the downloader or the clipper.

4. Managing Tools
Use the Update Tools button to keep yt-dlp and your environment up to date with the latest YouTube changes.

👑 Author's Note (Mr. Alvin Rocks)
"I am completely satisfied and happy with how Version 2.0 has turned out. It does exactly what I need it to do, and because of that, this is the final release of the application. While the browser sign-in may occasionally require a re-login due to Edge's strict sandboxing, the app is now in a stable, completed state. Feel free to use Pull Requests if you find a solution to any remaining quirks!"

Disclaimer: Still 100% AI-generated chaos. If it breaks, blame the robots. If it works, I'm a genius.
