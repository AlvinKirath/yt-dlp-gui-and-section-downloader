## Mr. Alvin Rocks - yt-dlp GUI & Section Downloader v2.0
The Completed "Final Edition"

A powerful, Python-based graphical interface for yt-dlp designed for absolute precision. This tool allows you to preview videos, set exact timestamps visually, and download high-bitrate video or audio sections without ever touching a command prompt.

### 🆕 Today's Final Polish & Fixes
To ensure the v2.0 release is truly "Final," we’ve integrated the following mission-critical updates today:

MKV Quality Unlocked: Switched the default container to MKV. This allows yt-dlp to grab the absolute best streams (VP9/AV1) that YouTube offers, which were previously blocked by the MP4 format limit.

Intelligent File Naming: Added an Anti-Overwrite system. When downloading clips, the app now appends the timestamps (e.g., [00-10-00 to 00-12-30]) to the filename so you can download multiple sections of the same video without losing data.

The DASH Stability Fix: Implemented a protocol to bypass broken DASH segments in Live or DVR streams. This fixes the "Invalid data found" error that was causing FFmpeg to crash during section downloads.

Preview Window HUD: The in-app previewer now shows a live status update. You can see the filename, download percentage, real-time speed, and ETA directly in the preview window while it works.

Browser Workflow: The integrated YouTube browser now automatically closes once you've sent a link to the player, keeping your workspace clutter-free.

### 🚀 Core Features
Visual Sectional Downloads: Use the built-in player to set exact start and end times visually.

In-App Video Previewer: Powered by VLC, featuring a YouTube-style interactive timeline with hover-tooltips for frame-perfect seeking.

Integrated YouTube Browser: A built-in Edge-based browser (WebView2). Browse, select, and send links to the downloader or clipper instantly.

Phantom Menu: A smart menu that detects YouTube links in your clipboard and pops up at your mouse cursor for immediate action.

Pause & Resume: Fully supports pausing active downloads and resuming them later, managing all background child processes.

Smart Playlist Downloader: Fetch entire playlists and pick specific videos to download as MKV, MP3, or both.

### ✅ Prerequisites
VLC Media Player: Required for the In-App Previewer.

FFmpeg: Required for merging video/audio and processing section cuts.

Node.js: Recommended for solving complex YouTube signature challenges.

### 👑 Author's Note
"I am completely satisfied and happy with how Version 2.0 has turned out. It does exactly what I need it to do—highest quality, precise clipping, and no more overwriting files. This is the completed state of the application." — Mr. Alvin Rocks
