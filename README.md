# YT Downloader 3.0
### More control. Less compromise.

**A powerful, no-nonsense YouTube downloader built for people who want things done their way.**

YT Downloader 3.0 isn't just another interface wrapped around yt-dlp. It's a feature-packed desktop utility designed to give you greater control over downloads, timestamps, formats, playlists, and playback — without making the process unnecessarily complicated.

Whether you're downloading an entire video, extracting a specific section, saving audio, or managing an entire playlist, everything is accessible from one unified interface.

## What's New in Version 3.0

### 1. Smarter Section Downloads
Downloading a specific timestamp range should be straightforward — and reliable.

- Improved section-download recovery and validation.
- Automatically checks downloaded clips for integrity using FFprobe.
- Attempts targeted timestamp-based recovery when a section download is incomplete.
- Avoids unnecessarily downloading the entire source video as a fallback.
- Better handling of interrupted connections and incomplete downloads.

### 2. Hardware-Accelerated Encoding
Make use of the hardware you already own.

Choose between:
- AMD AMF
- NVIDIA NVENC
- Intel Quick Sync
- CPU Encoding
- Automatic Encoder Selection

Automatic mode detects available hardware encoders and selects an appropriate option. If hardware encoding fails, the application can fall back to CPU encoding.

### 3. A Redesigned Settings Centre
A cleaner, more organised settings experience, with dedicated sections for:

- **General:** Download location, automatic clipboard grabbing and overwrite protection.
- **Downloads:** Resolution, formats, audio quality, subtitles, retries and concurrent fragments.
- **Appearance:** Themes and optional wallpaper.
- **Access:** Browser cookies and cookies.txt support.
- **Advanced:** Startup and window behaviour.

The settings interface also supports full-page scrolling, so options aren't hidden beyond the visible screen.

### 4. Improved Download Reliability
- Better handling of extraction and format-availability errors.
- Improved retry behaviour for interrupted downloads.
- Better support for YouTube's changing extraction requirements.
- Startup diagnostics and dependency checks.
- Automatic setup of supported tools and dependencies.

## Core Features

**Precision Timestamp Clipping**
- Set start and end timestamps manually.
- Preview videos using the integrated VLC player.
- Navigate through an interactive timeline.
- Use playback controls, volume adjustment and quick seeking.
- Copy the start timestamp directly into the end timestamp when needed.

**Video & Audio Downloads**
- Multiple resolution options.
- MP4, MKV and supported format merging.
- MP3, WAV, FLAC, M4A, AAC and original audio options.
- Selectable audio bitrates up to 320 kbps.
- Embedded metadata for supported MP3 downloads.

**Playlist Manager**
- Load entire playlists.
- Select individual videos or manage the entire selection.
- Download videos or audio using your preferred settings.

**Format Explorer**
- Inspect available formats.
- Filter MP4 video and audio formats.
- Sort available options and download selected formats.

**Integrated Browser**
- Embedded Microsoft Edge WebView2 browser.
- Persistent browser profile for login sessions.
- Quick actions for grabbing supported YouTube links.

**Download Management**
- Pause and resume downloads.
- Live progress, download speed and estimated completion time.
- Download logs and quick access to the output folder.

## Built for Control, Not Compromise.

YT Downloader 3.0 brings precision, flexibility and reliability together in one desktop application.

No unnecessary clutter. No needless complications. Just the controls you need, the formats you want, and the freedom to download on your own terms.

**YT Downloader 3.0 — Your downloads. Your settings. Your control.**
