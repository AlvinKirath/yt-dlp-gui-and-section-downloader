import sys
import os

# --- V1.7.1 FIX: Force Permanent Browser Profile ---
# This MUST be set before tkwebview2 is imported, otherwise Edge creates a temporary profile that deletes your login!
# FIX: Force forward slashes. Windows backslashes can silently corrupt the WebView2 Chromium parser!
user_data_dir = os.path.abspath(os.path.join(os.path.expanduser("~"), "yt_gui_browser_data")).replace("\\", "/")

# Ensure directory exists BEFORE WebView2 initializes
os.makedirs(user_data_dir, exist_ok=True)

# Force WebView2 to use persistent profile
os.environ["WEBVIEW2_USER_DATA_FOLDER"] = user_data_dir

# --- V1.8.2 FIX: Spoof User-Agent to stop Google from destroying the login session ---
# We MUST pretend to be standard Chrome, otherwise Google flags the WebView2 engine and wipes the cookies!
fake_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
# FIX: Removed the duplicate --user-data-dir argument which caused parser conflicts, and explicitly locked the profile directory.
os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--user-agent=\"{fake_ua}\" --profile-directory=\"Default\""

# --- V1.6 FIX: Lock Windows Threading to STA Natively ---
# tkwebview2/pywebview MUST be imported before VLC to prevent the RPC_E_CHANGED_MODE crash.
if os.name == 'nt':
    import ctypes
    ctypes.windll.ole32.CoInitializeEx(None, 2)

try:
    from tkwebview2.tkwebview2 import WebView2
    
    # --- V1.6 FIX: Monkey-patch to fix tkwebview2 compatibility with pywebview 5.0+ ---
    # Pywebview renamed an internal variable, breaking tkwebview2. This dynamically fixes the missing attribute!
    try:
        from webview.platforms.edgechromium import EdgeChrome
        if not hasattr(EdgeChrome, 'web_view'):
            EdgeChrome.web_view = property(lambda self: self.webview)
    except ImportError:
        pass
        
except ImportError:
    WebView2 = None

import colorsys
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
import os
import csv
import json
import subprocess
import threading
import math
import re
from datetime import datetime
import psutil  # --- NEW: Required for Pause/Resume feature ---
import webbrowser
import urllib.request
import urllib.parse
import shutil

# --- V1.6 FIRST RUN AUTOMATIC SETUP ---
def auto_install_dependencies():
    config_path = os.path.join(os.path.expanduser("~"), "yt_gui_config.json")
    try:
        with open(config_path, 'r') as f: cfg = json.load(f)
    except Exception: cfg = {}
    
    if not cfg.get("first_run_setup", False):
        print("First run detected! Checking and installing missing dependencies... (This might take a minute)")
        # 1. Install missing Python packages silently
        packages = ['yt-dlp', 'python-vlc', 'nodejs-bin[cmd]', 'tkwebview2', 'psutil', 'pillow']
        for pkg in packages:
            subprocess.run([sys.executable, '-m', 'pip', 'install', '-U', pkg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 2. Attempt to install missing system binaries on Windows using winget
        if os.name == 'nt':
            try:
                if not shutil.which("ffmpeg"):
                    print("Installing FFmpeg (System)...")
                    subprocess.run(['winget', 'install', 'Gyan.FFmpeg', '--silent', '--accept-package-agreements', '--accept-source-agreements'], stdout=subprocess.DEVNULL)
                if not shutil.which("vlc") and not os.path.exists(r"C:\Program Files\VideoLAN\VLC\vlc.exe") and not os.path.exists(r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"):
                    print("Installing VLC Media Player (System)...")
                    subprocess.run(['winget', 'install', 'VideoLAN.VLC', '--silent', '--accept-package-agreements', '--accept-source-agreements'], stdout=subprocess.DEVNULL)
            except FileNotFoundError:
                print("Winget not found. Skipping system-level installs.")

        # Mark setup as complete so it skips next time
        cfg["first_run_setup"] = True
        try:
            with open(config_path, 'w') as f: json.dump(cfg, f, indent=2)
        except: pass
        print("Setup complete! Booting app...")

auto_install_dependencies()
# --------------------------------------

try:
    import vlc
except ImportError:
    vlc = None

try:
    node_path = shutil.which("node")
    # --- V1.13 FIX: Added remote-components to solve YouTube's new JS Signature Challenges ---
    base = ['yt-dlp', '--remote-components', 'ejs:github']
    if node_path:
        YT_DLP_BASE = base + ['--js-runtimes', f'node:{node_path}']
    else:
        YT_DLP_BASE = base
except Exception:
    YT_DLP_BASE = ['yt-dlp', '--remote-components', 'ejs:github']

try:
    import tkinter as tk
    from tkinter import filedialog, scrolledtext, messagebox
    from tkinter import ttk
    from PIL import Image, ImageTk
except ModuleNotFoundError:
    print("Error: tkinter and pillow are required. Please install them and try again.")
    sys.exit(1)

# Configuration file path
CONFIG_FILE = os.path.join(os.path.expanduser("~"), "yt_gui_config.json")


def load_cfg():
    """Load configuration from JSON file (or defaults)."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    # Enforce Black theme if missing
    cfg.setdefault('theme', 'Black')  # Force dark theme
    cfg.setdefault('download_dir', os.path.expanduser("~"))
    cfg.setdefault('bg_image', '')
    cfg.setdefault('pos', (100, 100))
    
    # --- V1.8.1 FIX: Force Edge as default even for existing users ---
    if cfg.get('cookie_browser') == 'None' or 'cookie_browser' not in cfg:
        cfg['cookie_browser'] = 'edge'
        
    return cfg

def save_cfg(cfg):
    """Save configuration to JSON file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)

def update_progress_gui(pct, speed, eta):
        """Helper to update the custom progress bar and stats safely from the thread."""
        if not hasattr(app, 'prog_canvas'): return
        
        # Update the visual bar width based on current window size
        c_width = app.prog_canvas.winfo_width()
        if c_width <= 1: c_width = 560 # Fallback default width
        bar_width = (pct / 100.0) * c_width
        app.prog_canvas.coords(app.prog_bar, 0, 0, bar_width, 25)
        
        # Update percentage text & keep it perfectly centered
        app.prog_canvas.itemconfig(app.prog_text, text=f"{pct:.1f}%")
        app.prog_canvas.coords(app.prog_text, c_width / 2, 12)
        
        # Update Speed/ETA label
        if 0 < pct < 100:
            app.stats_label.config(text=f"Speed: {speed}   |   ETA: {eta}")
        elif pct >= 100:
            app.stats_label.config(text="Processing complete / Finalizing file...")
        else:
            app.stats_label.config(text="")
            
        # --- V1.9.1: Guarantee Preview text and bar updates synchronously ---
        if getattr(app, 'preview_dialog', None) and app.preview_dialog.winfo_exists():
            pd = app.preview_dialog
            if hasattr(pd, 'preview_status_main') and hasattr(pd, 'preview_status_stats'):
                if 0 < pct < 100:
                    current_title = app.status_label.cget('text')
                    pd.preview_status_main.config(text=f"{current_title} ({pct:.1f}%)")
                    pd.preview_status_stats.config(text=f"Speed: {speed}   |   ETA: {eta}")
                elif pct >= 100:
                    pd.preview_status_main.config(text="Processing complete...")
                    pd.preview_status_stats.config(text="")
                else:
                    pd.preview_status_main.config(text=app.status_label.cget('text'))
                    pd.preview_status_stats.config(text="")

            if hasattr(pd, 'preview_prog_canvas'):
                c_width_p = pd.preview_prog_canvas.winfo_width()
                if c_width_p <= 1: c_width_p = 200
                bar_width_p = (pct / 100.0) * c_width_p
                pd.preview_prog_canvas.coords(pd.preview_prog_bar, 0, 0, bar_width_p, 10)


def perform_online_tagging(filepath):
    """Queries the iTunes API to find metadata and applies it via ffmpeg."""
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    # Clean up title to improve search (remove "Official Video", brackets, etc.)
    clean_title = re.sub(r'(?i)\(.*?official.*?\)|\[.*?\]', '', base_name).strip()
    
    try:
        query = urllib.parse.quote(clean_title)
        url = f"https://itunes.apple.com/search?term={query}&entity=song&limit=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        if data.get('resultCount', 0) > 0:
            track = data['results'][0]
            artist = track.get('artistName', 'Unknown Artist')
            album = track.get('collectionName', 'Unknown Album')
            title = track.get('trackName', clean_title)
            genre = track.get('primaryGenreName', 'Unknown')
            
            temp_file = filepath + ".temp.mp3"
            ffmpeg_cmd = [
                'ffmpeg', '-y', '-i', filepath,
                '-metadata', f'title={title}',
                '-metadata', f'artist={artist}',
                '-metadata', f'album_artist={artist}',
                '-metadata', f'album={album}',
                '-metadata', f'genre={genre}',
                '-codec', 'copy', temp_file
            ]
            
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
            os.replace(temp_file, filepath)
            app.after(0, lambda: app.stats_label.config(text=f"Tagged: {artist} - {title}"))
        else:
            app.after(0, lambda: app.stats_label.config(text="Tagging skipped: No match found."))
    except Exception:
        app.after(0, lambda: app.stats_label.config(text="Tagging failed: Network error."))


def stream_process(cmd, status_label, prefix_msg=None, is_full_audio=False):
    """Run a subprocess, intercept progress for the bar, and stream other output to the terminal."""
    if prefix_msg:
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"{timestamp} {prefix_msg}")

    # Force yt-dlp to output nice newlines so python can read it properly
    if cmd[0] == 'yt-dlp' and '--newline' not in cmd:
        cmd.append('--newline')

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    
    # --- NEW: Store proc for Pause/Resume feature ---
    app.current_proc = proc  
    app.is_paused = False

    # Regex to catch standard yt-dlp progress
    prog_regex = re.compile(r'\[download\]\s+([0-9.]+)%.*?at\s+([a-zA-Z0-9./]+).*?ETA\s+([0-9:]+)')
    # V1.9.7: Regex to catch FFmpeg progress for sections/live streams!
    ffmpeg_prog_regex = re.compile(r'time=([0-9:\.]+).*?speed=\s*([0-9.]+)x')
    
    # Extract total duration if it's a section download to calculate FFmpeg percentage
    total_duration_sec = 0
    if prefix_msg and " - " in prefix_msg:
        try:
            times_part = prefix_msg.split("Downloading: ")[-1]
            # Strip off any quality tags like [1080p Max Quality] before splitting
            if "[" in times_part:
                times_part = times_part[:times_part.find("[")].strip()
            parts = times_part.split(" - ")
            h1, m1, s1 = map(int, parts[0].split(':'))
            h2, m2, s2 = map(int, parts[1].split(':'))
            total_duration_sec = (h2*3600 + m2*60 + s2) - (h1*3600 + m1*60 + s1)
        except: pass

    # --- NEW: Regex to catch the current downloading file ---
    dest_regex = re.compile(r'\[download\] Destination:\s*(.*)|\[ExtractAudio\] Destination:\s*(.*)|\[Merger\] Merging formats into "(.*)"')
    downloaded_mp3_path = None

    # Extract quality tag from the prefix message to keep it visible in the UI
    q_tag = ""
    if prefix_msg and "[" in prefix_msg and "]" in prefix_msg:
        q_tag = " " + prefix_msg[prefix_msg.find("["):prefix_msg.find("]")+1]

    for line in proc.stdout:
        line_str = line.strip()
        if not line_str: continue
        
        # --- NEW: Check for filename to update the title dynamically ---
        dest_match = dest_regex.search(line_str)
        if dest_match:
            # Grab whichever group matched (Video, Audio, or Merger)
            raw_path = dest_match.group(1) or dest_match.group(2) or dest_match.group(3)
            if raw_path:
                # Save the actual path for the Play Downloaded Video button
                if not raw_path.endswith('.part') and not raw_path.endswith('.ytdl'):
                    app.last_downloaded_file = raw_path
                    
                if raw_path.lower().endswith('.mp3'):
                    downloaded_mp3_path = raw_path
                filename = os.path.basename(raw_path)
                # Remove extension for a cleaner look
                clean_name = os.path.splitext(filename)[0]
                # Append the visual quality tag securely alongside the filename
                app.after(0, lambda f=clean_name, q=q_tag: status_label.config(text=f"Downloading: {f}{q}"))
        # --------------------------------------------------------------

        match = prog_regex.search(line_str)
        if match:
            # Standard yt-dlp progress line
            pct_val = float(match.group(1))
            speed = match.group(2)
            eta = match.group(3)
            app.after(0, update_progress_gui, pct_val, speed, eta)
        else:
            ff_match = ffmpeg_prog_regex.search(line_str)
            if ff_match and total_duration_sec > 0:
                # FFmpeg progress line (for section cuts). Calculate % math manually!
                try:
                    time_str = ff_match.group(1)
                    speed_val = float(ff_match.group(2))
                    speed = f"{speed_val}x"
                    h, m, s = time_str.split(':')
                    current_sec = int(h)*3600 + int(m)*60 + float(s)
                    pct_val = min(100.0, (current_sec / total_duration_sec) * 100)
                    
                    # V1.9.8: Dynamically calculate ETA using remaining media length / FFmpeg's encoding speed
                    eta = "Calculating..."
                    if speed_val > 0:
                        remaining_sec = max(0, total_duration_sec - current_sec)
                        real_eta_sec = int(remaining_sec / speed_val)
                        
                        # Format into MM:SS (or HH:MM:SS)
                        eta_m, eta_s = divmod(real_eta_sec, 60)
                        eta_h, eta_m = divmod(eta_m, 60)
                        if eta_h > 0:
                            eta = f"{eta_h:02d}:{eta_m:02d}:{eta_s:02d}"
                        else:
                            eta = f"{eta_m:02d}:{eta_s:02d}"
                            
                    app.after(0, update_progress_gui, pct_val, speed, eta)
                except: pass
            elif not line_str.startswith("frame=") and not line_str.startswith("[libx264") and not line_str.startswith("[https") and not line_str.startswith("[hls"):
                # Normal output line. Suppress spammy FFmpeg frame & network logs!
                timestamp = datetime.now().strftime('%H:%M:%S')
                print(f"{timestamp} {line_str}")

    proc.wait()
    
    if is_full_audio and downloaded_mp3_path and os.path.exists(downloaded_mp3_path):
        app.after(0, lambda: status_label.config(text="MP3 tagging Please wait..."))
        app.after(0, lambda: app.stats_label.config(text="Querying online database for tags..."))
        perform_online_tagging(downloaded_mp3_path)
    
    # --- NEW: Cleanup process tracking and disable pause button ---
    app.current_proc = None
    app.after(0, lambda: app.pause_btn.config(state='disabled', text="Pause", bg='#ffc107'))
    app.after(0, lambda: status_label.config(text="Ready"))
    # --------------------------------------------------------------

    final_status = 'Success' if proc.returncode == 0 else 'Failed'
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"{timestamp} {prefix_msg or 'Command'} - {final_status}")
    
    # Reset progress bar to zero when completely finished
    app.after(0, update_progress_gui, 0.0, "", "")
    
    # Pulse the Open Folder button if successful
    if proc.returncode == 0:
        app.after(0, lambda: app.trigger_open_folder_pulse())




class SettingsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Settings")
        self.configure(bg='#000000')

        # Download directory
        ttk.Label(
            self, text="Download Directory:",
            background='#2e2e2e', foreground='white'
        ).pack(pady=(10, 0))
        self.dir_var = tk.StringVar(value=parent.download_dir)
        ttk.Entry(
            self, textvariable=self.dir_var, width=50
        ).pack(pady=5)
        ttk.Button(
            self, text="Change...", command=self.change_dir
        ).pack(pady=5)

        # Background image
        ttk.Label(
            self, text="Background Image:",
            background='#2e2e2e', foreground='White'
        ).pack(pady=(10, 0))
        ttk.Button(
            self, text="Select Image...", command=self.change_bg
        ).pack(pady=5)

	    # Theme selection
        ttk.Label(
    		self, text="Theme:",
    		background='#000000', foreground='White'
	    ).pack(pady=(10, 0))
        self.theme_var = tk.StringVar(value=self.parent.cfg.get('theme', 'Black'))
        themes = ["Black", "Light", "Blue", "Purple"]
        ttk.OptionMenu(
    		self, self.theme_var, self.parent.cfg['theme'], *themes
	    ).pack(pady=5)

        # Save & Close button
        ttk.Button(
            self, text="Save & Close", command=self.close
        ).pack(pady=(20, 10)) 
        
    def change_dir(self):
        selected = filedialog.askdirectory(
            initialdir=self.parent.download_dir
        )
        if selected:
            self.parent.download_dir = selected
            self.dir_var.set(selected)
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.parent.log.insert(
                'end', f"{timestamp} Download directory set to: {selected}\n"
            )

    def change_bg(self):
        filetypes = [('Image Files', '*.png;*.jpg;*.jpeg;*.gif')]
        selected = filedialog.askopenfilename(filetypes=filetypes)
        if selected:
            self.parent.set_background(selected)
            self.parent.cfg['bg_image'] = selected

    def close(self):
        self.parent.cfg['theme'] = self.theme_var.get()
        self.parent.build_ui()
        self.parent.apply_theme(self.theme_var.get())
        save_cfg(self.parent.cfg)
        self.destroy()


class PlaylistDialog(tk.Toplevel):
    """Dialog for fetching and downloading entire playlists."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Playlist Downloader")
        self.configure(bg='#000000')
        self.geometry("600x450")

        # URL Frame
        url_frame = tk.Frame(self, bg='#2e2e2e')
        url_frame.pack(pady=10, fill='x', padx=20)
        tk.Label(url_frame, text="Playlist URL:", bg='#2e2e2e', fg='white').pack(side='left')
        self.url_entry = tk.Entry(url_frame, width=50, bg='#3e3e3e', fg='white', insertbackground='white')
        self.url_entry.pack(side='left', padx=5)
        
        # Pre-fill with the URL from the main window if available
        self.url_entry.insert(0, self.parent.url.get())

        tk.Button(url_frame, text="Fetch Names", command=self.fetch_playlist, bg='#17a2b8', fg='white').pack(side='left')

        # Listbox for videos
        list_frame = tk.Frame(self, bg='#000000')
        list_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        self.listbox = tk.Listbox(list_frame, bg='#1e1e1e', fg='white', selectmode=tk.EXTENDED)
        self.listbox.pack(side='left', fill='both', expand=True)
        
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scrollbar.pack(side='right', fill='y')
        self.listbox.config(yscrollcommand=scrollbar.set)

        # --- NEW: Select All / Deselect All Buttons ---
        sel_frame = tk.Frame(self, bg='#000000')
        sel_frame.pack(fill='x', padx=20)
        tk.Button(sel_frame, text="Select All", command=self.select_all, bg='#17a2b8', fg='white').pack(side='left', padx=(0, 5))
        tk.Button(sel_frame, text="Deselect All", command=self.deselect_all, bg='#dc3545', fg='white').pack(side='left')
        # ----------------------------------------------

        # Options Frame for MP3/MP4 selection
        opt_frame = tk.Frame(self, bg='#2e2e2e')
        opt_frame.pack(pady=10, fill='x', padx=20)
        
        self.format_var = tk.StringVar(value="MKV_BEST")
        tk.Radiobutton(opt_frame, text="Max Quality (MKV)", variable=self.format_var, value="MKV_BEST", bg='#2e2e2e', fg='white', selectcolor='#000000').pack(side='left', padx=5)
        tk.Radiobutton(opt_frame, text="MP3", variable=self.format_var, value="MP3", bg='#2e2e2e', fg='white', selectcolor='#000000').pack(side='left', padx=5)
        # --- NEW: Both Option ---
        tk.Radiobutton(opt_frame, text="Both", variable=self.format_var, value="BOTH", bg='#2e2e2e', fg='white', selectcolor='#000000').pack(side='left', padx=5)

        tk.Button(opt_frame, text="Download Playlist", command=self.download_playlist, bg='#28a745', fg='white', font=(None, 10, 'bold')).pack(side='right')

    def select_all(self):
        """Select all items in the listbox."""
        self.listbox.select_set(0, tk.END)

    def deselect_all(self):
        """Deselect all items in the listbox."""
        self.listbox.selection_clear(0, tk.END)

    def fetch_playlist(self):
        url = self.url_entry.get().strip()
        if not url: return
        self.listbox.delete(0, tk.END)
        self.listbox.insert(tk.END, "Fetching playlist data... please wait.")
        threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

    def _fetch_worker(self, url):
        # --flat-playlist gets the metadata quickly without downloading videos
        cmd = self.parent.get_base_cmd() + ['--flat-playlist', '--dump-json', url]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        videos = []
        for line in proc.stdout:
            try:
                data = json.loads(line)
                title = data.get('title', 'Unknown Title')
                videos.append(title)
            except: pass
        
        self.listbox.after(0, self._update_listbox, videos)

    def _update_listbox(self, videos):
        self.listbox.delete(0, tk.END)
        if not videos:
            self.listbox.insert(tk.END, "No videos found. Make sure the URL is a public playlist.")
        else:
            for i, v in enumerate(videos, 1):
                self.listbox.insert(tk.END, f"{i}. {v}")

    def download_playlist(self):
        url = self.url_entry.get().strip()
        if not url: return
        fmt = self.format_var.get()
        
        # --- NEW: Get selected items ---
        selected_indices = self.listbox.curselection()
        if not selected_indices:
            # If nothing is selected, we cancel the download to prevent accidental full-playlist downloads
            self.listbox.insert(tk.END, "ERROR: Please select at least one video before downloading.")
            return
            
        # yt-dlp uses 1-based indexing, so we add 1 to the tkinter indices
        playlist_items = ",".join(str(i + 1) for i in selected_indices)
        # -------------------------------
        
        # --- MODIFIED: Added %(playlist_title)s to automatically create a folder named after the playlist ---
        output_template = os.path.join(self.parent.download_dir, "%(playlist_title)s", "%(playlist_index)s - %(title)s.%(ext)s")
        
        cmd = self.parent.get_base_cmd() + ['--force-overwrites']
        
        # --- NEW: Tell yt-dlp to only download the selected indices ---
        cmd += ['--playlist-items', playlist_items]
        # --------------------------------------------------------------
        
        if fmt == "MKV_BEST":
            cmd += ['-f', 'bestvideo+bestaudio', '--merge-output-format', 'mkv', '--postprocessor-args', 'ffmpeg:-threads 0 -preset fast']
        elif fmt == "MP3":
            cmd += ['--extract-audio', '--audio-format', 'mp3', '--embed-thumbnail', '--postprocessor-args', 'ffmpeg:-threads 0']
        elif fmt == "BOTH":
            # Downloads the best video, merges to MKV, extracts MP3, and keeps the MKV
            cmd += ['-f', 'bestvideo+bestaudio', '--merge-output-format', 'mkv', '--extract-audio', '--keep-video', '--audio-format', 'mp3', '--postprocessor-args', 'ffmpeg:-threads 0 -preset fast']
            
        cmd += ['-o', output_template, url]
            
        self.parent.run_custom(cmd, f"Downloading items [{playlist_items}] as {fmt}")
        self.destroy()


class FormatExplorerDialog(tk.Toplevel):
    """Dialog to explore available formats for a URL."""
    def __init__(self, parent, url):
        super().__init__(parent)
        self.title("Format Explorer")
        self.geometry("700x400")
        self.configure(bg='#000000')
        self.url = url
        self.formats = []

        # Filter buttons
        btn_frame = tk.Frame(self, bg='#2e2e2e')
        btn_frame.pack(fill='x', pady=5, padx=10)
        tk.Button(btn_frame, text="Show All", command=lambda: self.populate_list("ALL"), bg='#6c757d', fg='white').pack(side='left', padx=5)
        tk.Button(btn_frame, text="MP4 Video", command=lambda: self.populate_list("MP4"), bg='#007bff', fg='white').pack(side='left', padx=5)
        tk.Button(btn_frame, text="MP3 / Audio", command=lambda: self.populate_list("AUDIO"), bg='#28a745', fg='white').pack(side='left', padx=5)
        tk.Button(btn_frame, text="Download Selected", command=self.download_selected, bg='#dc3545', fg='white', font=(None, 9, 'bold')).pack(side='right', padx=5)

        # Treeview for formats
        style = ttk.Style(self)
        style.configure("T.Treeview", background="#1e1e1e", foreground="white", fieldbackground="#1e1e1e")
        cols = ("ID", "Ext", "Resolution", "FPS", "Bitrate", "Size")
        self.tree = ttk.Treeview(self, columns=cols, show='headings', height=15, style="T.Treeview")
        self.sort_order = {c: True for c in cols}
        for c in cols:
            self.tree.heading(c, text=c, command=lambda _c=c: self.sort_column(_c, True))
            self.tree.column(c, width=100, anchor='center')
        self.tree.pack(fill='both', expand=True, padx=10, pady=10)

        self.fetch_formats()

    def fetch_formats(self):
        self.tree.insert('', 'end', values=("Loading...", "", "Querying yt-dlp...", "", "", ""))
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        cmd = ['yt-dlp', '--dump-json', self.url]
        try:
            # Suppress cmd popup on Windows, capture stderr just in case
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, startupinfo=startupinfo)
            data = json.loads(proc.stdout)
            self.formats = data.get('formats', [])
            
            # Ensure window wasn't closed before updating UI
            if self.winfo_exists():
                self.after(0, lambda: self.populate_list("ALL"))
        except Exception as e:
            print(f"Format fetch error: {e}")
            if self.winfo_exists():
                self.after(0, lambda: self.tree.insert('', 'end', values=("Error", "", "Failed to fetch formats", "", "", "")))

    def populate_list(self, filter_type):
        if not self.winfo_exists(): return
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        for f in self.formats:
            ext = f.get('ext', 'N/A')
            vcodec = f.get('vcodec', 'none')
            acodec = f.get('acodec', 'none')
            
            if filter_type == "MP4" and ext != 'mp4': continue
            if filter_type == "AUDIO" and vcodec != 'none': continue

            fid = f.get('format_id', 'N/A')
            res = f.get('resolution', 'audio only' if vcodec == 'none' else 'N/A')
            size_bytes = f.get('filesize') or f.get('filesize_approx') or 0
            size_mb = f"{size_bytes / (1024 * 1024):.2f} MB" if size_bytes else "Unknown"

            self.tree.insert('', 'end', values=(fid, ext, res, size_mb, vcodec, acodec))


class FormatExplorerDialog(tk.Toplevel):
    """Dialog to explore available formats for a URL."""
    def __init__(self, parent, url):
        super().__init__(parent)
        self.title("Format Explorer")
        self.geometry("700x400")
        self.configure(bg='#000000')
        self.url = url
        self.formats = []

        # Filter buttons
        btn_frame = tk.Frame(self, bg='#2e2e2e')
        btn_frame.pack(fill='x', pady=5, padx=10)
        tk.Button(btn_frame, text="Show All", command=lambda: self.populate_list("ALL"), bg='#6c757d', fg='white').pack(side='left', padx=5)
        tk.Button(btn_frame, text="MP4 Video", command=lambda: self.populate_list("MP4"), bg='#007bff', fg='white').pack(side='left', padx=5)
        tk.Button(btn_frame, text="MP3 / Audio", command=lambda: self.populate_list("AUDIO"), bg='#28a745', fg='white').pack(side='left', padx=5)
        tk.Button(btn_frame, text="Download Selected", command=self.download_selected, bg='#dc3545', fg='white', font=(None, 9, 'bold')).pack(side='right', padx=5)

        # Treeview for formats
        style = ttk.Style(self)
        style.configure("T.Treeview", background="#1e1e1e", foreground="white", fieldbackground="#1e1e1e")
        cols = ("ID", "Ext", "Resolution", "FPS", "Bitrate", "Size")
        self.tree = ttk.Treeview(self, columns=cols, show='headings', height=15, style="T.Treeview")
        self.sort_order = {c: True for c in cols}
        for c in cols:
            self.tree.heading(c, text=c, command=lambda _c=c: self.sort_column(_c, self.sort_order[_c]))
            self.tree.column(c, width=100, anchor='center')
        self.tree.pack(fill='both', expand=True, padx=10, pady=10)

        self.fetch_formats()

    def fetch_formats(self):
        self.tree.insert('', 'end', values=("Loading...", "", "Querying yt-dlp...", "", "", ""))
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def sort_column(self, col, reverse):
        self.sort_order[col] = not self.sort_order[col]
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        def convert(val):
            try:
                if col == "Size": return float(val.replace(" MB", "")) if "MB" in val else -1.0
                if col == "Resolution": return int(val.split("x")[1]) if "x" in val else -1
                if col == "FPS": return float(val) if val != "N/A" else -1.0
                if col == "Bitrate": return float(val.replace("k", "")) if "k" in val else -1.0
            except:
                return -1.0
            return val
        l.sort(key=lambda t: convert(t[0]), reverse=self.sort_order[col])
        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)
        self.tree.heading(col, command=lambda _c=col: self.sort_column(_c, not reverse))

    def _fetch_worker(self):
        cmd = self.master.get_base_cmd() + ['--dump-json', self.url]
        try:
            # Use startupinfo to hide console window on Windows if desired, otherwise standard subprocess
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=True)
            data = json.loads(proc.stdout)
            self.formats = data.get('formats', [])
            self.after(0, lambda: self.populate_list("ALL"))
        except Exception as e:
            self.after(0, lambda: self.tree.insert('', 'end', values=("Error", "", "Failed to fetch formats", "", "", "")))

    def populate_list(self, filter_type):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        display_items = []
        for f in self.formats:
            vcodec = f.get('vcodec', 'none')
            acodec = f.get('acodec', 'none')
            # Force UI to show MP4 for videos and MP3 for audio, ignoring raw server formats
            ext = 'mp4' if vcodec != 'none' else 'mp3'
            
            height = f.get('height', 0)
            if height and height > 1080: continue
            
            if filter_type == "MP4" and ext != 'mp4': continue
            if filter_type == "AUDIO" and vcodec != 'none': continue

            fid = f.get('format_id', 'N/A')
            res = f.get('resolution', 'audio only' if vcodec == 'none' else 'N/A')
            fps = f.get('fps')
            fps_str = str(fps) if fps else "N/A"
            tbr = f.get('tbr')
            bitrate_str = f"{int(tbr)}k" if tbr else "N/A"
            
            size_bytes = f.get('filesize') or f.get('filesize_approx') or 0
            size_raw_mb = size_bytes / (1024 * 1024) if size_bytes else 0
            size_mb = f"{size_raw_mb:.2f} MB" if size_raw_mb else "Unknown"
            
            # Ranking: High quality MP4 (<=1080p) -> High quality MP3/Audio -> Rest
            is_vid = (vcodec != 'none' and ext == 'mp4')
            is_aud = (vcodec == 'none')
            score = 100000 + height if is_vid else (50000 + size_raw_mb if is_aud else size_raw_mb)
            
            display_items.append((score, fid, ext, res, fps_str, bitrate_str, size_mb))

        # Sort descending by score for default order
        display_items.sort(key=lambda x: x[0], reverse=True)
        
        for item in display_items:
            self.tree.insert('', 'end', values=item[1:])

    def download_selected(self):
        """Downloads the format currently selected in the Treeview."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a format to download.")
            return
            
        item = self.tree.item(selected[0])
        format_id = item['values'][0] # ID is the first visible column
        
        output_template = os.path.join(self.master.download_dir, "%(title)s.%(ext)s")
        cmd = self.master.get_base_cmd() + ['--force-overwrites', '-f', str(format_id), '-o', output_template, self.url]
        
        self.master.run_custom(cmd, f"Downloading format {format_id}")
        self.destroy()


class VideoPreviewDialog(tk.Toplevel):
    """V1.5 Breakthrough: In-App Video Player to visually set timestamps."""
    def __init__(self, parent, url):
        super().__init__(parent)
        self.parent = parent
        self.title("In-App Video Preview - Set Timestamps")
        self.geometry("800x600")
        self.configure(bg='#000000')
        self.url = url
        
        if vlc is None:
            tk.Label(self, text="Error: 'python-vlc' module is missing.\nPlease open your terminal and run:\npip install python-vlc", fg='red', bg='black', font=(None, 14)).pack(pady=50)
            return

        # Attempt to open window maximized
        try:
            self.state('zoomed')
        except tk.TclError:
            self.attributes('-zoomed', True)

        self.status_lbl = tk.Label(self, text="Loading video stream... (yt-dlp is extracting the raw feed. This takes 5-15 seconds)", fg='cyan', bg='black', font=(None, 12, 'bold'))
        self.status_lbl.pack(pady=5)

        self.video_frame = tk.Frame(self, bg='black')
        self.video_frame.pack(fill='both', expand=True, padx=10, pady=5)

        # --- NEW: Dedicated Slider Row (Top) ---
        slider_frame = tk.Frame(self, bg='#2e2e2e')
        slider_frame.pack(fill='x', pady=(10, 0), padx=10)

        self.current_time_lbl = tk.Label(slider_frame, text="00:00:00", fg='white', bg='#2e2e2e', font=(None, 10))
        self.current_time_lbl.pack(side='left', padx=5)

        # --- V1.6: Custom YouTube-style Interactive Timeline ---
        self.timeline = tk.Canvas(slider_frame, height=20, bg='#444', highlightthickness=0, cursor="hand2")
        self.timeline.pack(side='left', fill='x', expand=True, padx=5)
        
        # Floating Tooltip for exact timeline seeking
        self.tooltip = tk.Label(self, text="00:00:00", bg='black', fg='white', font=(None, 10, 'bold'), borderwidth=1, relief='solid')
        
        # Bindings for the custom timeline
        self.is_seeking = False
        self.timeline.bind("<Motion>", self.on_timeline_hover)
        self.timeline.bind("<Leave>", lambda e: self.tooltip.place_forget())
        self.timeline.bind("<ButtonPress-1>", self.on_timeline_press)
        self.timeline.bind("<B1-Motion>", self.on_timeline_drag)
        self.timeline.bind("<ButtonRelease-1>", self.on_timeline_release)

        self.total_time_lbl = tk.Label(slider_frame, text="00:00:00", fg='white', bg='#2e2e2e', font=(None, 10))
        self.total_time_lbl.pack(side='right', padx=5)

        # --- V1.8: Dedicated Skip Buttons Row ---
        skip_frame = tk.Frame(self, bg='#1e1e1e')
        skip_frame.pack(fill='x', pady=(0, 10), padx=10)

        intervals = [(5, '5s'), (10, '10s'), (30, '30s'), (60, '1m'), (120, '2m'), (300, '5m')]
        
        # Left side frame (skip backward)
        left_skip = tk.Frame(skip_frame, bg='#1e1e1e')
        left_skip.pack(side='left', expand=True, anchor='e')
        for secs, lbl in reversed(intervals):
            tk.Button(left_skip, text=f"⏪ {lbl}", command=lambda s=secs: self.skip_video(-s), bg='#343a40', fg='white', font=(None, 8)).pack(side='left', padx=2)

        tk.Label(skip_frame, text=" Seek ", bg='#1e1e1e', fg='grey', font=(None, 9, 'bold')).pack(side='left', padx=10)

        # Right side frame (skip forward)
        right_skip = tk.Frame(skip_frame, bg='#1e1e1e')
        right_skip.pack(side='left', expand=True, anchor='w')
        for secs, lbl in intervals:
            tk.Button(right_skip, text=f"{lbl} ⏩", command=lambda s=secs: self.skip_video(s), bg='#343a40', fg='white', font=(None, 8)).pack(side='left', padx=2)

        # --- NEW: Buttons Row (Bottom) ---
        ctrl_frame = tk.Frame(self, bg='#2e2e2e')
        ctrl_frame.pack(fill='x', pady=(0, 10), padx=10)

        self.play_btn = tk.Button(ctrl_frame, text="⏯ Play/Pause", command=self.toggle_pause, bg='#007bff', fg='white', font=(None, 10, 'bold'))
        self.play_btn.pack(side='left', padx=5)
        
        # --- NEW: Volume Slider ---
        tk.Label(ctrl_frame, text="🔊", bg='#2e2e2e', fg='white').pack(side='left', padx=(10,0))
        self.vol_var = tk.IntVar(value=100)
        self.vol_slider = tk.Scale(ctrl_frame, variable=self.vol_var, orient='horizontal', from_=0, to=100, showvalue=0, command=self.change_volume, bg='#2e2e2e', highlightthickness=0, length=80)
        self.vol_slider.pack(side='left', padx=5)

        # Center the Set Start / Set End buttons
        center_frame = tk.Frame(ctrl_frame, bg='#2e2e2e')
        center_frame.pack(side='left', expand=True)
        tk.Button(center_frame, text="[ Set as Start ]", command=self.set_start, bg='#28a745', fg='white', font=(None, 10, 'bold')).pack(side='left', padx=10)
        tk.Button(center_frame, text="[ Set as End ]", command=self.set_end, bg='#dc3545', fg='white', font=(None, 10, 'bold')).pack(side='left', padx=10)
        
        tk.Button(ctrl_frame, text="Save & Close", command=self.close_player, bg='#ffc107', fg='black', font=(None, 10, 'bold')).pack(side='right', padx=5)

        # --- V1.7: Secondary Home Layout (Action Frame) ---
        action_frame = tk.Frame(self, bg='#1e1e1e', bd=1, relief='solid')
        action_frame.pack(fill='x', pady=(0, 10), padx=10)

        # Start/End labels
        time_display_frame = tk.Frame(action_frame, bg='#1e1e1e')
        time_display_frame.pack(side='left', padx=10, pady=5)
        
        def get_time_str(entries):
            try: return f"{int(entries[0].get() or 0):02d}:{int(entries[1].get() or 0):02d}:{int(entries[2].get() or 0):02d}"
            except: return "00:00:00"
            
        self.lbl_start_display = tk.Label(time_display_frame, text=f"Start: {get_time_str(self.parent.start)}", bg='#1e1e1e', fg='#28a745', font=(None, 10, 'bold'))
        self.lbl_start_display.pack(anchor='w')
        self.lbl_end_display = tk.Label(time_display_frame, text=f"End: {get_time_str(self.parent.end)}", bg='#1e1e1e', fg='#dc3545', font=(None, 10, 'bold'))
        self.lbl_end_display.pack(anchor='w')

        # Action Buttons
        btn_frame = tk.Frame(action_frame, bg='#1e1e1e')
        btn_frame.pack(side='left', padx=20)
        tk.Button(btn_frame, text="Video", command=self.parent.on_download, bg='#28a745', fg='white', font=(None, 10, 'bold')).pack(side='left', padx=5)
        tk.Button(btn_frame, text="Audio", command=self.parent.on_audio, bg='#17a2b8', fg='white', font=(None, 10, 'bold')).pack(side='left', padx=5)
        # V1.9.7: Added dedicated Playlist button to the Preview window!
        tk.Button(btn_frame, text="Playlist", command=self.parent.on_playlist, bg='#e83e8c', fg='white', font=(None, 10, 'bold')).pack(side='left', padx=5)
        self.preview_open_folder_btn = tk.Button(btn_frame, text="Open Folder", command=self.parent.on_open_folder, bg='#6c757d', fg='white', font=(None, 10, 'bold'))
        self.preview_open_folder_btn.pack(side='left', padx=5)
        self.preview_play_btn = tk.Button(btn_frame, text="▶ Play Video", command=self.parent.play_last_download, bg='#6c757d', fg='white', font=(None, 10, 'bold'))
        self.preview_play_btn.pack(side='left', padx=5)

        # Mini Progress Status with Canvas
        prog_frame = tk.Frame(action_frame, bg='#1e1e1e')
        prog_frame.pack(side='right', fill='x', expand=True, padx=10)
        
        lbl_frame = tk.Frame(prog_frame, bg='#1e1e1e')
        lbl_frame.pack(fill='x', expand=True)
        
        self.preview_status_main = tk.Label(lbl_frame, text="Ready", bg='#1e1e1e', fg='cyan', font=(None, 10, 'bold'))
        self.preview_status_main.pack(side='left', anchor='w')
        self.preview_status_stats = tk.Label(lbl_frame, text="", bg='#1e1e1e', fg='white', font=(None, 9))
        self.preview_status_stats.pack(side='right', anchor='e')
        
        self.preview_prog_canvas = tk.Canvas(prog_frame, height=10, bg='#3e3e3e', highlightthickness=0)
        self.preview_prog_canvas.pack(fill='x', pady=(2, 0))
        self.preview_prog_bar = self.preview_prog_canvas.create_rectangle(0, 0, 0, 10, fill='cyan')

        self.parent.preview_dialog = self # Register dialog to main app for animations

        # --- NEW: Bind Spacebar and Arrow Keys for media control ---
        self.bind("<space>", lambda e: self.toggle_pause())
        self.bind("<Left>", lambda e: self.skip_video(-10))
        self.bind("<Right>", lambda e: self.skip_video(10))
        self.focus_set()

        try:
            # --- NEW: Inject deep network caching (5000ms) to fix stream lag ---
            self.instance = vlc.Instance('--no-xlib', '--quiet', '--network-caching=5000', '--live-caching=5000')
            self.player = self.instance.media_player_new()
        except Exception as e:
            tk.Label(self.video_frame, text="VLC Media Player is not installed on your computer.\nPlease install the standard VLC player from videolan.org to use this feature.", fg='red', bg='black', font=(None, 12)).pack(pady=50)
            self.player = None
            return
            
        if os.name == 'nt':
            self.player.set_hwnd(self.video_frame.winfo_id())
        elif sys.platform.startswith('linux'):
            self.player.set_xwindow(self.video_frame.winfo_id())
        elif sys.platform == 'darwin':
            self.player.set_nsobject(self.video_frame.winfo_id())

        self.protocol("WM_DELETE_WINDOW", self.close_player)
        
        threading.Thread(target=self.load_stream, daemon=True).start()
        self.update_ui()

    def load_stream(self):
        try:
            # --- V1.12.1 FIX: Foolproof Tracebacks & Broader Fallback ---
            # Added --verbose to dump the EXACT python/extractor line that failed to the terminal.
            # Added 'best' to the fallback chain to catch edge-case streams.
            cmd = self.parent.get_base_cmd() + ['-g', '--verbose', '-f', '18/22/b/best/w', self.url]
                
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo)
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or "Unknown yt-dlp error"
                
                # --- V1.12 FIX: Print full error to terminal for debugging ---
                print("\n" + "="*60)
                print(f"[VLC PREVIEW ERROR] Failed to load stream for: {self.url}")
                print(f"FULL ERROR OUTPUT:\n{result.stderr}")
                print("="*60 + "\n")
                
                # Make the label multi-line (wraplength) so it doesn't get cut off in the UI
                self.status_lbl.config(text=f"Error (See Terminal for full details):\n{error_msg[:150]}...", fg='red', wraplength=750)
                return

            stream_url = result.stdout.strip().split('\n')[0]
            
            media = self.instance.media_new(stream_url)
            self.player.set_media(media)
            self.player.play()
            self.status_lbl.config(text="Preview Loaded (Fast Mode). Use the slider to seek.")
        except Exception as e:
            self.status_lbl.config(text=f"Failed to load stream. Error: {e}")

    def toggle_pause(self):
        if self.player:
            self.player.pause()

    def change_volume(self, val):
        """Adjusts VLC player volume (0-100)."""
        if getattr(self, 'player', None):
            self.player.audio_set_volume(int(val))

    def skip_video(self, seconds):
        """Skips the video forward or backward by the specified number of seconds."""
        if getattr(self, 'player', None) and self.player.get_length() > 0:
            current_ms = self.player.get_time()
            max_ms = self.player.get_length()
            
            # Calculate target time, clamped between 0 and the max length of the video
            target_ms = max(0, min(current_ms + (seconds * 1000), max_ms))
            self.player.set_time(target_ms)
            
            # Instantly update visual timeline bar for snappy feedback
            if getattr(self, 'timeline', None) and self.timeline.winfo_width() > 0:
                pct = target_ms / max_ms
                w = self.timeline.winfo_width()
                self.timeline.delete("progress")
                self.timeline.create_rectangle(0, 0, w * pct, 20, fill="#ff0000", tags="progress")

    def trigger_play_pulse(self, flashes=20):
        """Flashes the Play button yellow/blue to indicate the video is ready."""
        if flashes <= 0 or not self.winfo_exists():
            if hasattr(self, 'play_btn'): self.play_btn.config(bg='#007bff')
            return
        current_bg = self.play_btn.cget('bg')
        new_bg = '#ffc107' if current_bg == '#007bff' else '#007bff'
        self.play_btn.config(bg=new_bg)
        self.after(500, self.trigger_play_pulse, flashes - 1)

    def _get_timeline_pct(self, event):
        w = self.timeline.winfo_width()
        return max(0.0, min(1.0, event.x / w)) if w > 0 else 0

    def on_timeline_hover(self, event):
        if not self.player or self.player.get_length() <= 0: return
        pct = self._get_timeline_pct(event)
        hover_sec = int(pct * (self.player.get_length() // 1000))
        h, m, s = hover_sec // 3600, (hover_sec % 3600) // 60, hover_sec % 60
        
        # Position tooltip exactly above mouse
        x = event.x_root - self.winfo_rootx() - 30
        y = event.y_root - self.winfo_rooty() - 35
        self.tooltip.config(text=f"{h:02d}:{m:02d}:{s:02d}")
        self.tooltip.place(x=x, y=y)

    def on_timeline_press(self, event):
        self.is_seeking = True
        self.on_timeline_drag(event)

    def on_timeline_drag(self, event):
        if not getattr(self, 'player', None) or self.player.get_length() <= 0: return
        pct = self._get_timeline_pct(event)
        
        # V1.9: Do NOT spam the network with seek commands while dragging. 
        # Only update the visual red bar and the tooltip so it is perfectly smooth.
        self.on_timeline_hover(event)
        w = self.timeline.winfo_width()
        self.timeline.delete("progress")
        self.timeline.create_rectangle(0, 0, w * pct, 20, fill="#ff0000", tags="progress")

    def on_timeline_release(self, event):
        if getattr(self, 'player', None) and self.player.get_length() > 0:
            pct = self._get_timeline_pct(event)
            self.player.set_position(pct) # Perform the actual video jump ONLY on mouse release
        self.is_seeking = False

    def get_current_seconds(self):
        if self.player:
            return self.player.get_time() // 1000
        return 0

    def set_start(self):
        secs = self.get_current_seconds()
        if secs >= 0:
            self.parent.set_timestamp(self.parent.start, secs)
            self.status_lbl.config(text=f"Start time captured: {secs} seconds")
            h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
            self.lbl_start_display.config(text=f"Start: {h:02d}:{m:02d}:{s:02d}")

    def set_end(self):
        secs = self.get_current_seconds()
        if secs >= 0:
            self.parent.set_timestamp(self.parent.end, secs)
            self.status_lbl.config(text=f"End time captured: {secs} seconds")
            h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
            self.lbl_end_display.config(text=f"End: {h:02d}:{m:02d}:{s:02d}")

    def close_player(self):
        self.parent.preview_dialog = None
        if self.player:
            self.player.stop()
            self.player.release()
        self.destroy()

    def update_ui(self):
        if getattr(self, 'player', None) and self.winfo_exists():
            length = self.player.get_length() // 1000
            current = self.player.get_time() // 1000
            
            if length > 0 and current >= 0:
                ch, cm, cs = current // 3600, (current % 3600) // 60, current % 60
                th, tm, ts = length // 3600, (length % 3600) // 60, length % 60
                
                self.current_time_lbl.config(text=f"{ch:02d}:{cm:02d}:{cs:02d}")
                self.total_time_lbl.config(text=f"{th:02d}:{tm:02d}:{ts:02d}")
                
                if not self.is_seeking:
                    pct = current / length
                    w = self.timeline.winfo_width()
                    self.timeline.delete("progress")
                    self.timeline.create_rectangle(0, 0, w * pct, 20, fill="#ff0000", tags="progress")
            
        if self.winfo_exists():
            self.after(100, self.update_ui) # Faster refresh for smoother canvas timeline


class YouTubeBrowserDialog(tk.Toplevel):
    """V1.6: In-App YouTube Browser using WebView2."""
    def __init__(self, parent, start_url="https://www.youtube.com"):
        super().__init__(parent)
        self.parent = parent
        self.start_url = start_url
        self.title("YouTube Browser")
        self.geometry("1000x700")
        self.configure(bg='#000000')

        # --- V1.7 FIX: Maximize window ---
        try: self.state('zoomed')
        except tk.TclError: self.attributes('-zoomed', True)

        if WebView2 is None:
            tk.Label(self, text="Error: 'tkwebview2' module is missing.\nPlease click 'Update Tools' or run:\npip install tkwebview2", fg='red', bg='black', font=(None, 14)).pack(pady=50)
            return

        # Top Control Frame
        ctrl_frame = tk.Frame(self, bg='#2e2e2e')
        ctrl_frame.pack(fill='x', pady=5, padx=5)

        tk.Button(ctrl_frame, text="⬅ Back", command=self.go_back, bg='#6c757d', fg='white').pack(side='left', padx=5)
        tk.Button(ctrl_frame, text="➡ Forward", command=self.go_forward, bg='#6c757d', fg='white').pack(side='left', padx=5)
        tk.Button(ctrl_frame, text="🏠 Home", command=self.go_home, bg='#17a2b8', fg='white').pack(side='left', padx=5)
        
        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(ctrl_frame, textvariable=self.url_var, width=50, bg='#3e3e3e', fg='white', insertbackground='white')
        self.url_entry.pack(side='left', padx=10, fill='x', expand=True)
        self.url_entry.bind("<Return>", lambda e: self.load_url_from_entry())

        # --- V1.7: Browser Action Frame (Bottom) ---
        action_frame = tk.Frame(self, bg='#1e1e1e', bd=1, relief='solid')
        action_frame.pack(side='bottom', fill='x', pady=(0, 5), padx=10)

        # Download Buttons
        tk.Button(action_frame, text="⬇ Video", command=self.quick_video, bg='#28a745', fg='white', font=(None, 10, 'bold')).pack(side='left', padx=10, pady=8)
        tk.Button(action_frame, text="🎵 Audio", command=self.quick_audio, bg='#17a2b8', fg='white', font=(None, 10, 'bold')).pack(side='left', padx=5, pady=8)
        tk.Button(action_frame, text="📑 Playlist", command=self.quick_playlist, bg='#e83e8c', fg='white', font=(None, 10, 'bold')).pack(side='left', padx=5, pady=8)

        # Send to Preview for clipping
        tk.Button(action_frame, text="✂️ Set Timestamps (Opens Player)", command=self.send_to_app, bg='#ffc107', fg='black', font=(None, 10, 'bold')).pack(side='right', padx=10, pady=8)

        # WebView2 Frame
        try:
            self.browser = WebView2(self, width=1000, height=650)
            self.browser.pack(fill='both', expand=True)
            self.go_home()
        except Exception as e:
            self.browser = None
            tk.Label(self, text=f"Browser Engine Failed to Load.\nTry restarting the app.\n\nError: {e}", fg='red', bg='black', font=(None, 12)).pack(pady=50)

    def go_back(self):
        if getattr(self, 'browser', None): self.browser.core.GoBack()

    def go_forward(self):
        if getattr(self, 'browser', None): self.browser.core.GoForward()

    def go_home(self):
        if getattr(self, 'browser', None):
            self.browser.load_url(self.start_url)
            self.url_var.set(self.start_url)

    def load_url_from_entry(self):
        if not getattr(self, 'browser', None): return
        url = self.url_var.get()
        if not url.startswith("http"): url = "https://" + url
        self.browser.load_url(url)

    def _sync_url(self):
        """Updates the main app's URL box with the browser's current URL."""
        current_url = getattr(self.browser.core, 'Source', None)
        if current_url:
            self.parent.url.delete(0, tk.END)
            self.parent.url.insert(0, current_url)
            self.parent.validate_url_color()
            return True
        return False

    def _pause_browser_media(self):
        """V1.13 FIX: Forcefully pauses and mutes any playing video in the browser."""
        try:
            js_code = """
            var players = document.querySelectorAll('.html5-video-player');
            players.forEach(p => p.pauseVideo());
            document.querySelectorAll('video').forEach(v => { v.pause(); v.volume = 0; v.muted = true; });
            """
            self.browser.core.ExecuteScriptAsync(js_code)
        except Exception: pass

    def quick_video(self):
        if self._sync_url():
            self._pause_browser_media()
            self.parent.clear_timestamps() # Ensure full video downloads
            self.parent.on_download()

    def quick_audio(self):
        if self._sync_url():
            self._pause_browser_media()
            self.parent.clear_timestamps()
            self.parent.on_audio()

    def quick_playlist(self):
        if self._sync_url():
            self._pause_browser_media()
            self.parent.on_playlist()

    def send_to_app(self):
        """Grabs the URL and sends it to the VLC Preview Player for exact timestamping."""
        if self._sync_url():
            self.parent.open_preview()
            self.destroy()


class PhantomMenu(tk.Toplevel):
    """V1.9.2: Invisible Smart-Menu that appears exactly at your mouse when you copy a link."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Phantom Menu")
        self.overrideredirect(True) # Completely borderless (looks like a native context menu)
        self.attributes('-topmost', True)
        self.configure(bg='#1e1e1e', bd=2, relief='ridge')
        self.withdraw() # Start completely invisible so it doesn't clutter your screen

        # Header
        tk.Label(self, text="Link Grabbed! Quick Action:", bg='#1e1e1e', fg='cyan', font=(None, 9, 'bold')).pack(pady=(5,2), padx=10)

        # Button Grid
        btn_frame = tk.Frame(self, bg='#1e1e1e')
        btn_frame.pack(fill='both', expand=True, padx=5, pady=(0,5))
        
        tk.Button(btn_frame, text="⬇ Video", command=self.quick_video, bg='#28a745', fg='white', font=(None, 10, 'bold'), width=10).grid(row=0, column=0, padx=2, pady=2)
        tk.Button(btn_frame, text="🎵 Audio", command=self.quick_audio, bg='#17a2b8', fg='white', font=(None, 10, 'bold'), width=10).grid(row=0, column=1, padx=2, pady=2)
        tk.Button(btn_frame, text="✂️ Player", command=self.quick_preview, bg='#ffc107', fg='black', font=(None, 10, 'bold'), width=10).grid(row=1, column=0, padx=2, pady=2)
        tk.Button(btn_frame, text="📑 Playlist", command=self.quick_playlist, bg='#e83e8c', fg='white', font=(None, 10, 'bold'), width=10).grid(row=1, column=1, padx=2, pady=2)
        
        tk.Button(self, text="✖ Cancel (Hide)", command=self.hide_menu, bg='#dc3545', fg='white', font=(None, 9, 'bold')).pack(fill='x', padx=5, pady=(0,5))

        self.last_clipboard = ""
        self.check_trigger()

    def check_trigger(self):
        try:
            clip = self.clipboard_get().strip()
            if clip != self.last_clipboard:
                self.last_clipboard = clip
                # Only trigger the popup if it's a 100% valid YouTube link
                if re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$', clip):
                    # Teleport the menu exactly to the user's mouse cursor!
                    x = self.winfo_pointerx()
                    y = self.winfo_pointery()
                    self.geometry(f"+{x+15}+{y+15}")
                    self.deiconify() # Reveal the menu instantly
                    
                    # Background sync to main app so it's ready
                    self.parent.url.delete(0, tk.END)
                    self.parent.url.insert(0, clip)
                    self.parent.validate_url_color()
        except tk.TclError: pass
        
        self.after(500, self.check_trigger)

    def hide_menu(self):
        self.withdraw()

    def _system_pause(self):
        """V1.11 FIX: Sends OS-level Media Play/Pause keystroke to pause Edge in the background!"""
        if os.name == 'nt':
            import ctypes
            # 0xB3 is the Windows virtual key code for Media Play/Pause
            ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0xB3, 0, 2, 0)

    def quick_video(self):
        self._system_pause()
        self.parent.clear_timestamps()
        self.parent.on_download()
        self.hide_menu()

    def quick_audio(self):
        self._system_pause()
        self.parent.clear_timestamps()
        self.parent.on_audio()
        self.hide_menu()
        
    def quick_playlist(self):
        self._system_pause()
        self.parent.on_playlist()
        self.hide_menu()

    def quick_preview(self):
        self._system_pause()
        self.parent.open_preview()
        self.hide_menu()


# --- THIS REPLACES THE OLD FLOATINGACTIONBAR COMPLETELY ---
        self.geometry("450x65+100+100") # Small, wide bar
        self.configure(bg='#1e1e1e')
        self.resizable(False, False)

        # Instruction Label
        self.lbl = tk.Label(self, text="1. Copy a YouTube link (Ctrl+C) ➔ 2. Click an action!", bg='#1e1e1e', fg='cyan', font=(None, 9, 'bold'))
        self.lbl.pack(side='top', fill='x', pady=(4,2))

        # Button Frame
        btn_frame = tk.Frame(self, bg='#1e1e1e')
        btn_frame.pack(side='bottom', fill='x', pady=4, padx=5)

        tk.Button(btn_frame, text="⬇ Video", command=self.quick_video, bg='#28a745', fg='white', font=(None, 9, 'bold')).pack(side='left', padx=2, expand=True, fill='x')
        tk.Button(btn_frame, text="🎵 Audio", command=self.quick_audio, bg='#17a2b8', fg='white', font=(None, 9, 'bold')).pack(side='left', padx=2, expand=True, fill='x')
        # (Old FloatingActionBar removed)


class Mr_AlvinRocks(tk.Tk):
    """Main application window."""
    def __init__(self):
        super().__init__()
        global app
        app = self
        self.cfg = load_cfg()
        # Force black theme on first run
        if 'theme' not in self.cfg:
            self.cfg['theme'] = 'Black'
            save_cfg(self.cfg)  # Immediately persist

        # Window setup
        x, y = self.cfg['pos']
        self.geometry(f"+{x}+{y}")
        self.title("Mr. Alvin Rocks - YouTube Clip Downloader")
        self.configure(bg='#000000')

        # Download directory
        self.download_dir = self.cfg['download_dir']

        # Background image label
        self.bg_label = tk.Label(self)
        self.bg_label.place(relwidth=1, relheight=1)
        bg_img = self.cfg.get('bg_image')
        if bg_img:
            self.set_background(bg_img)

        # Build UI
        self.build_ui()

        # Apply the theme AFTER all widgets (including bg_label) are created
        self.apply_theme(self.cfg.get('theme', 'Black'))

        # Header animation
        self.theta = 0.0
        self.animate_header()

        # Close handler
        self.protocol('WM_DELETE_WINDOW', self.on_close)

    def set_background(self, path):
        """Set a background image stretched to window size."""
        img = Image.open(path)
        # Resize to current window size
        img = img.resize(
            (self.winfo_width(), self.winfo_height()),
            Image.ANTIALIAS
        )
        self.bg_imgtk = ImageTk.PhotoImage(img)
        self.bg_label.config(image=self.bg_imgtk)

    
    def apply_theme(self, theme):
        themes = {
            "Black": {
                "bg": "#000000", "fg": "white",
                "entry_bg": "#000000", "entry_fg": "white",
                "button_bg": "#444", "button_fg": "white"
            },
            "Light": {
                "bg": "white", "fg": "black",
                "entry_bg": "white", "entry_fg": "black",
                "button_bg": "#e0e0e0", "button_fg": "black"
            },
            "Blue": {
                "bg": "#1e3a5f", "fg": "white",
                "entry_bg": "#29527a", "entry_fg": "white",
                "button_bg": "#3a6ea5", "button_fg": "white"
            },
            "Purple": {
                "bg": "#3d1a4f", "fg": "white",
                "entry_bg": "#5e2e7e", "entry_fg": "white",
                "button_bg": "#8e44ad", "button_fg": "white"
            }
        }
        t = themes.get(theme, themes["Black"])
        self.configure(bg=t["bg"])
        
        # Recursively apply theme to all nested widgets
        def style_widget(parent):
            for widget in parent.winfo_children():
                # Skip colored buttons and the progress canvas so we don't break them
                if not isinstance(widget, (tk.Button, tk.Canvas)):
                    try:
                        widget.configure(bg=t["bg"], fg=t["fg"])
                    except:
                        pass
                style_widget(widget) # Go deeper into nested frames
                
        style_widget(self)


    def build_ui(self):
            # 0. wipe out old UI (but keep the background image label)
        for widget in self.winfo_children():
            if widget is not self.bg_label:
                widget.destroy()

        """Construct all UI elements."""
        style = ttk.Style(self)
        style.theme_use('clam')
        themes = {
            "Black":   {"ttk_bg":"#2e2e2e","ttk_fg":"white","entry_bg":"#3e3e3e","button_bg":"#444"},
            "Light":  {"ttk_bg":"white",  "ttk_fg":"black","entry_bg":"white",  "button_bg":"#e0e0e0"},
            "Blue":   {"ttk_bg":"#1e3a5f","ttk_fg":"white","entry_bg":"#29527a","button_bg":"#3a6ea5"},
            "Purple": {"ttk_bg":"#3d1a4f","ttk_fg":"white","entry_bg":"#5e2e7e","button_bg":"#8e44ad"},
        }
        theme = self.cfg.get('theme', 'Black')
        t = themes.get(theme, themes["Black"])
        style.configure(
            '.',
            background=t["ttk_bg"],
            foreground=t["ttk_fg"],
            fieldbackground=t["entry_bg"]
        )
        style.map('TButton', background=[('active', t["button_bg"])])
        style.configure('TEntry', fieldbackground='#3e3e3e', foreground='white')
        style.configure('TScrollbar', background='#3e3e3e')


        # Header label
        self.header = tk.Label(
            self, text="Mr.AlvinRocks - YouTube Clip Downloader",
            font=(None, 32, 'bold'),
            bg='#2e2e2e', fg='cyan'
        )
        self.header.pack(pady=(20, 10))

        # Timestamp fields
        ts_frame = tk.Frame(self, bg='#2e2e2e')
        ts_frame.pack(pady=5)
        self.start = []
        self.end = []
        for label_text, target_list in [('Start', self.start), ('End', self.end)]:
            tk.Label(
                ts_frame, text=label_text,
                font=(None, 14), bg='#2e2e2e', fg='white'
            ).pack(side='left', padx=5)
            for _ in range(3):  # H, M, S
                entry = tk.Entry(
                    ts_frame, width=5, font=(None, 12),
                    justify='center', bg='#3e3e3e', fg='white',
                    insertbackground='white'
                )
                entry.pack(side='left', padx=2)
                target_list.append(entry)
                
        # --- NEW: Clear button for timestamps ---
        tk.Button(
            ts_frame, text="Clear", command=self.clear_timestamps,
            bg='#4b0082', fg='white', font=(None, 10, 'bold'), padx=5
        ).pack(side='left', padx=(15, 5))

        # URL & status
        url_frame = tk.Frame(self, bg='#2e2e2e')
        url_frame.pack(pady=10, fill='x', padx=20)
        tk.Label(
            url_frame, text="YouTube URL:",
            font=(None, 14), bg='#2e2e2e', fg='white'
        ).grid(row=0, column=0, sticky='e')
        self.url = tk.Entry(
            url_frame, font=(None, 12), width=50,
            bg='#dc3545', fg='white', insertbackground='white'
        )
        self.url.grid(row=0, column=1, padx=5, sticky='w')
        self.url.bind("<KeyRelease>", self.validate_url_color)
        
        # --- NEW: Bind Ctrl+V to our custom paste method ---
        self.url.bind("<Control-v>", self.on_ctrl_v)
        self.url.bind("<Command-v>", self.on_ctrl_v) # For Mac
        
        # --- NEW: Auto-Grab Link Checkbox ---
        self.auto_grab_var = tk.BooleanVar(value=True) # Now ON by default
        self.last_clipboard = ""
        tk.Checkbutton(
            url_frame, text="Auto-Grab YouTube Links from Clipboard", variable=self.auto_grab_var,
            bg='#2e2e2e', fg='cyan', selectcolor='#1e1e1e', activebackground='#2e2e2e', activeforeground='cyan'
        ).grid(row=1, column=1, sticky='w', padx=5, pady=(2,0))
        
        # --- NEW V1.5: In-App Player Button ---
        self.preview_btn = tk.Button(
            url_frame, text="▶ Open In-App Player", command=self.open_preview,
            bg='#174c4f', fg='white', font=(None, 9, 'bold'), state='disabled'
        )
        self.preview_btn.grid(row=1, column=2, columnspan=2, sticky='w', pady=(2,0))

        self.res_var = tk.StringVar(value="1080")
        tk.Label(url_frame, text="Res:", bg='#2e2e2e', fg='white').grid(row=0, column=2, padx=5)
        tk.OptionMenu(url_frame, self.res_var, "2160", "1080", "720", "480", "360").grid(row=0, column=3)
        
        # --- NEW: Audio Quality Dropdown ---
        self.audio_q_var = tk.StringVar(value="320")
        tk.Label(url_frame, text="Audio kbps:", bg='#2e2e2e', fg='white').grid(row=0, column=4, padx=5)
        tk.OptionMenu(url_frame, self.audio_q_var, "320", "256", "192", "128").grid(row=0, column=5)

        # --- V1.8 FEATURE: System Browser Cookies Integration ---
        # Ensure the UI variable reflects the updated config default
        current_cookie = self.cfg.get('cookie_browser', 'edge')
        self.cookie_var = tk.StringVar(value=current_cookie)
        
        tk.Label(url_frame, text="Cookies:", bg='#2e2e2e', fg='#ffc107', font=(None, 9, 'bold')).grid(row=0, column=6, padx=5)
        
        # --- V1.10 FIX: Added 'cookies.txt' option to bypass Chromium App-Bound Encryption ---
        cookie_options = ["None", "edge", "chrome", "firefox", "brave", "opera", "safari", "vivaldi", "cookies.txt"]
        cookie_dropdown = tk.OptionMenu(url_frame, self.cookie_var, *cookie_options, command=self.save_cookie_setting)
        cookie_dropdown.config(bg='#2e2e2e', fg='white', activebackground='#444', activeforeground='white')
        cookie_dropdown.grid(row=0, column=7)

        # Buttons
        btn_frame = tk.Frame(self, bg='#2e2e2e')
        btn_frame.pack(pady=15)
        button_info = [
            ("Video", self.on_download, '#28a745'),
            ("Audio", self.on_audio, '#17a2b8'),
            ("Playlist", self.on_playlist, '#e83e8c'),
            ("Open Folder", self.on_open_folder, '#6c757d'),
            ("Settings", self.on_settings, '#ff33ff'),
            ("📋 Paste", self.paste_from_clipboard, '#8a2be2'),
            ("🔍 Formats", self.on_format_explorer, '#007bff'),
            ("🌐 Browser", self.open_browser, '#20c997'),
            ("🌐 Browser (Channel)", self.open_browser_channel, '#17a2b8'),
            ("My Channel (External)", self.on_my_channel, '#ff0000'),
            ("Update Tools", self.on_update_tools, '#d2691e'),
            ("Exit", self.on_close, '#dc3545')
        ]
        
        # Grid layout adjusted for new button count
        self.action_buttons = {} # Store button references for animations
        for idx, (text, cmd, color) in enumerate(button_info):
            btn = tk.Button(
                btn_frame, text=text,
                command=cmd,
                bg=color, fg='white',
                font=(None, 10, 'bold'),
                padx=10, pady=5
            )
            self.action_buttons[text] = btn # Save reference
            row = idx // 4
            col = idx % 4
            btn.grid(row=row, column=col, padx=8, pady=8, sticky='nsew') # Increased padding slightly
            btn_frame.columnconfigure(col, weight=1)

        # Log box removed. Expanding the Status Frame to utilize the freed space.
        
        # --- NEW: Status Frame for Label + Pause Button ---
        status_frame = tk.Frame(self, bg='#1e1e1e')
        status_frame.pack(pady=(15, 10), fill='both', expand=True, padx=20) # Added 'expand=True'
        
        self.status_label = tk.Label(
            status_frame, 
            text="Ready", 
            bg='#1e1e1e', 
            fg='white', 
            font=(None, 10),
            anchor='w' # Align text to the left
        )
        self.status_label.pack(side='left', fill='x', expand=True)

        # Made the Pause button much larger with bigger font and internal padding
        self.pause_btn = tk.Button(
            status_frame, text="Pause", command=self.toggle_pause,
            bg='#ffc107', fg='black', font=(None, 12, 'bold'), state='disabled',
            padx=10, pady=2
        )
        self.pause_btn.pack(side='right', padx=5, ipadx=10, ipady=2)
        # ---------------------------------------------------

        # Download Stats (Speed, ETA)
        self.stats_label = tk.Label(
            self, text="", bg='#000000', fg='white', font=(None, 11, 'bold')
        )
        self.stats_label.pack(fill='x', padx=20, pady=(5, 2))

        # Canvas for Custom Breathing Progress Bar
        self.prog_canvas = tk.Canvas(self, height=25, bg='#3e3e3e', highlightthickness=0)
        self.prog_canvas.pack(fill='x', padx=20, pady=(0, 20))
        
        # Draw initial empty bar and centered text
        self.prog_bar = self.prog_canvas.create_rectangle(0, 0, 0, 25, fill='cyan')
        self.prog_text = self.prog_canvas.create_text(
            300, 12, text="0.0%", fill='white', font=(None, 11, 'bold') # 300 is rough center, updates dynamically
        )
        
        # Start clipboard polling for Auto-Grab
        self.after(1000, self.check_clipboard)

    def save_cookie_setting(self, value):
        """Save the chosen cookie browser instantly. If cookies.txt is selected, prompt for the file."""
        if value == "cookies.txt":
            file_path = filedialog.askopenfilename(title="Select cookies.txt file", filetypes=[("Text Files", "*.txt")])
            if file_path:
                self.cfg['cookie_file'] = file_path
            else:
                # If user cancels the prompt, revert back to None so it doesn't break
                self.cookie_var.set("None")
                value = "None"
                
        self.cfg['cookie_browser'] = value
        save_cfg(self.cfg)

    def get_base_cmd(self):
        """Returns the base yt-dlp command, injecting cookies securely."""
        cmd = list(YT_DLP_BASE)
        browser = self.cookie_var.get()
        
        if browser == "cookies.txt":
            cookie_file = self.cfg.get('cookie_file', '')
            if os.path.exists(cookie_file):
                cmd.extend(['--cookies', cookie_file])
        elif browser != "None":
            cmd.extend(['--cookies-from-browser', browser])
        return cmd

    def animate_header(self):
        """Animate header with a full-spectrum rainbow + white breathing effect."""
        hue = (self.theta % (2 * math.pi)) / (2 * math.pi)
        sat = 1.0
        val = 1.0 if math.sin(self.theta * 0.5) > 0 else 0.8
        r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
        color_hex = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
        
        self.header.config(fg=color_hex)
        
        # Apply the breathing color to the new progress bar and stats
        if hasattr(self, 'prog_canvas'):
            self.prog_canvas.itemconfig(self.prog_bar, fill=color_hex)
            self.stats_label.config(fg=color_hex)
            
        # --- NEW: Breathe the preview bar too ---
        if getattr(self, 'preview_dialog', None) and self.preview_dialog.winfo_exists():
            if hasattr(self.preview_dialog, 'preview_prog_canvas'):
                self.preview_dialog.preview_prog_canvas.itemconfig(self.preview_dialog.preview_prog_bar, fill=color_hex)
            
        self.theta += 0.05
        self.after(30, self.animate_header)

    def run_custom(self, cmd, msg, is_full_audio=False):
        """Helper to start streaming thread."""
        # --- NEW: Enable the Pause button when a download starts ---
        self.pause_btn.config(state='normal', text="Pause", bg='#ffc107')
        
        threading.Thread(
            target=stream_process,
            args=(cmd, self.status_label, msg, is_full_audio),
            daemon=True
        ).start()

    def clear_timestamps(self):
        """Clears both Start and End timestamp entries."""
        for entry in self.start + self.end:
            entry.delete(0, tk.END)

    def set_timestamp(self, target_list, total_seconds):
        """Fills a timestamp entry list (H, M, S) given total seconds."""
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        for i, val in enumerate([h, m, s]):
            target_list[i].delete(0, tk.END)
            target_list[i].insert(0, f"{val:02d}")

    def get_video_id(self, url):
        """Extracts the base video ID from a YouTube URL to compare links."""
        match = re.search(r'(?:v=|youtu\.be/)([^&?]+)', url)
        return match.group(1) if match else url

    def is_empty_time(self, target_list):
        """Checks if a timestamp list is effectively empty or 00:00:00."""
        return all(not e.get().strip() or e.get().strip() == '00' or e.get().strip() == '0' for e in target_list)

    def on_ctrl_v(self, event):
        """Intercept Ctrl+V to use custom paste logic instead of default Tkinter paste."""
        self.paste_from_clipboard()
        return "break" # Prevents default UI behavior

    def check_clipboard(self):
        """Polls the clipboard periodically to auto-grab YouTube links."""
        if getattr(self, 'auto_grab_var', None) and self.auto_grab_var.get():
            try:
                current_clip = self.clipboard_get().strip()
                if current_clip != self.last_clipboard:
                    self.last_clipboard = current_clip
                    # Check if it looks like a YouTube link before auto-pasting
                    if re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$', current_clip):
                        self.paste_from_clipboard()
            except tk.TclError:
                pass
        self.after(500, self.check_clipboard)

    def paste_from_clipboard(self):
        """Grabs text from the clipboard, pastes it, and parses timestamps if present."""
        try:
            clipboard_text = self.clipboard_get().strip()
            self.last_clipboard = clipboard_text # Update tracker so Auto-Grab doesn't re-trigger
            current_url = self.url.get().strip()
            
            # Check for timestamp parameter like t=427 or t=427s
            time_match = re.search(r'[?&]t=(\d+)s?', clipboard_text)
            new_seconds = int(time_match.group(1)) if time_match else None
            
            self.url.delete(0, tk.END)
            self.url.insert(0, clipboard_text)
            self.validate_url_color()
            
            if new_seconds is not None:
                def get_sec(t_list):
                    try: return int(t_list[0].get() or 0)*3600 + int(t_list[1].get() or 0)*60 + int(t_list[2].get() or 0)
                    except: return -1
                
                if self.is_empty_time(self.start):
                    self.set_timestamp(self.start, new_seconds)
                else:
                    if self.get_video_id(current_url) == self.get_video_id(clipboard_text) and self.get_video_id(clipboard_text):
                        # Same video. Only assign to End if the timestamp is actually different.
                        if new_seconds != get_sec(self.start):
                            self.set_timestamp(self.end, new_seconds)
                    else:
                        # Different video entirely, reset and fill start
                        self.clear_timestamps()
                        self.set_timestamp(self.start, new_seconds)

        except tk.TclError:
            pass # Fails gracefully if clipboard is empty or non-text

    def validate_url_color(self, event=None):
        """Dynamically changes URL box background based on validity."""
        url = self.url.get().strip()
        # Basic regex check for youtube or standard http/https links
        if re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$', url):
            self.url.config(bg='#28a745') # Green
            if hasattr(self, 'preview_btn'):
                self.preview_btn.config(state='normal', bg='#20c997', fg='white') # Unique Teal color
        else:
            self.url.config(bg='#dc3545') # Red
            if hasattr(self, 'preview_btn'):
                self.preview_btn.config(state='disabled', bg='#174c4f', fg='white') # Distinct Dark Teal

    def open_preview(self):
        """V1.5 Feature: Launch the internal video player."""
        url = self.url.get().strip()
        if url:
            VideoPreviewDialog(self, url)

    def open_browser(self):
        """V1.12 Revert: Launch the internal Python YouTube browser."""
        YouTubeBrowserDialog(self, "https://www.youtube.com")

    def open_browser_channel(self):
        """V1.12 Revert: Launch internal Python browser directly to your channel."""
        YouTubeBrowserDialog(self, "https://www.youtube.com/@Mr.Alvin_Games/streams")

    def launch_native_edge(self, url):
        """V1.9 Breakthrough: Launches your REAL Microsoft Edge."""
        try:
            if os.name == 'nt':
                # --- V1.11 FIX: Use --new-window instead of --app so the URL bar is fully visible! ---
                subprocess.Popen(f'start msedge --new-window "{url}"', shell=True)
            else:
                webbrowser.open(url) # Fallback for Mac/Linux
                
            # --- V1.9.2 FIX: Spawn the invisible Phantom Menu watcher ---
            PhantomMenu(self)
        except Exception as e:
            messagebox.showerror("Error", f"Could not launch Edge: {e}")

    # --- NEW: Pause / Resume Functionality ---
    def toggle_pause(self):
        """Pause or Resume the current download process and all its children."""
        if not getattr(self, 'current_proc', None): return
        
        try:
            p = psutil.Process(self.current_proc.pid)
            # Find all child processes (like ffmpeg) that yt-dlp spawned
            children = p.children(recursive=True)
            
            if getattr(self, 'is_paused', False):
                for child in children:
                    try: child.resume() 
                    except: pass
                p.resume()
                self.is_paused = False
                self.pause_btn.config(text="Pause", bg='#ffc107')
                current_text = self.status_label.cget("text").replace(" [PAUSED]", "")
                self.status_label.config(text=current_text)
            else:
                for child in children:
                    try: child.suspend() 
                    except: pass
                p.suspend()
                self.is_paused = True
                self.pause_btn.config(text="Resume", bg='#28a745')
                self.status_label.config(text=self.status_label.cget("text") + " [PAUSED]")
        except Exception as e:
            messagebox.showerror("Error", f"Could not toggle pause: {e}")
    # -----------------------------------------

    def _build_video_download_args(self, res, is_full_video):
        """Use MKV to allow the absolute highest quality streams (VP9/AV1)."""
        if is_full_video:
            return [
                '--format',
                f'bestvideo[height<={res}]+bestaudio/best',
                '--merge-output-format', 'mkv'
            ]

        return [
            '--format',
            f'bestvideo[protocol!=http_dash_segments][height<={res}]+bestaudio[protocol!=http_dash_segments]/best[protocol!=http_dash_segments]',
            '--merge-output-format', 'mkv',
            '--force-keyframes-at-cuts',
            '--concurrent-fragments', '1',
            '--hls-prefer-native',
            '--fragment-retries', '10'
        ]

    def on_download(self):
        """Start video download with selected timestamps."""
        # V1.9.7: Added --no-playlist so pasting a playlist URL doesn't accidentally download everything
        cmd = self.get_base_cmd() + ['--force-overwrites', '--no-playlist']
        
        res = self.res_var.get()
        url = self.url.get().strip()
        start = ':'.join(e.get() or '00' for e in self.start)
        end = ':'.join(e.get() or '00' for e in self.end)
        
        is_full_video = (start == '00:00:00' and end == '00:00:00')
        
        if is_full_video:
            output_template = os.path.join(self.download_dir, "%(title)s.%(ext)s")
        else:
            safe_start = start.replace(':', '-')
            safe_end = end.replace(':', '-')
            output_template = os.path.join(self.download_dir, f"%(title)s [{safe_start} to {safe_end}].%(ext)s")
        
        cmd += self._build_video_download_args(res, is_full_video)

        if not is_full_video:
            cmd.extend(['--download-sections', f'*{start}-{end}'])
            # --- V1.13 FIX: Force FFmpeg to maintain 1080p High Quality (CRF 18) during section cuts! ---
            cmd += ['--postprocessor-args', 'ffmpeg:-threads 0 -c:v libx264 -crf 18 -preset fast -c:a aac -b:a 192k']
        else:
            cmd += ['--postprocessor-args', 'ffmpeg:-threads 0 -preset fast']
            
        cmd.extend(['-o', output_template, url])
        
        # Inject the resolution tag into the starting message so the UI can capture it
        quality_tag = f"[{res}p Max Quality]"
        msg_suffix = f"Full Video {quality_tag}" if is_full_video else f"{start} - {end} {quality_tag}"
        self.run_custom(cmd, f"Downloading: {msg_suffix}")

    def on_audio(self):
        """Start audio extraction with selected timestamps."""
        url = self.url.get().strip()
        start = ':'.join(e.get() or '00' for e in self.start)
        end = ':'.join(e.get() or '00' for e in self.end)
        
        is_full_audio = (start == '00:00:00' and end == '00:00:00')
        
        if is_full_audio:
            output_template = os.path.join(self.download_dir, "%(title)s.%(ext)s")
        else:
            safe_start = start.replace(':', '-')
            safe_end = end.replace(':', '-')
            output_template = os.path.join(self.download_dir, f"%(title)s [{safe_start} to {safe_end}].%(ext)s")
        
        cmd = self.get_base_cmd() + [
            '--force-overwrites', '--no-playlist', 
            '--extract-audio',
            '--audio-format', 'mp3',
            '--embed-thumbnail',
            '--embed-metadata',
            '--parse-metadata', '%(title)s:%(meta_title)s',
            '--audio-quality', f'{self.audio_q_var.get()}K',
            '-o', output_template
        ]
        
        # Only pass section flags if the user actually inputted timestamps
        if not is_full_audio:
            cmd.extend(['--format', 'bestaudio[protocol!=http_dash_segments]/best[protocol!=http_dash_segments]'])
            cmd.extend(['--download-sections', f'*{start}-{end}'])
            
        cmd.extend(['--postprocessor-args', 'ffmpeg:-threads 0 -movflags +faststart', url])
        
        msg_suffix = "Full Audio" if is_full_audio else f"{start} - {end}"
        self.run_custom(cmd, f"Extracting audio: {msg_suffix}", is_full_audio=is_full_audio)

    def on_format_explorer(self):
        """Open the format explorer dialog."""
        url = self.url.get().strip()
        if not url:
            messagebox.showerror("Error", "Please paste a valid URL first.")
            return
        FormatExplorerDialog(self, url)

    def on_playlist(self):
        """Open the playlist dialog."""
        PlaylistDialog(self)

    def on_my_channel(self):
        """Open the user's YouTube channel in the default web browser."""
        channel_url = "https://www.youtube.com/@Mr.Alvin_Games/streams" # TODO: Put your YouTube Channel URL here!
        webbrowser.open(channel_url)

    def play_last_download(self):
        """Play the last successfully downloaded file in the default media player."""
        target_file = getattr(self, 'last_downloaded_file', None)
        if target_file and os.path.exists(target_file):
            try:
                if os.name == 'nt':
                    os.startfile(target_file)
                elif sys.platform == 'darwin':
                    subprocess.run(['open', target_file])
                else:
                    subprocess.run(['xdg-open', target_file])
            except Exception as e:
                messagebox.showerror("Error", f"Cannot play file: {e}")
        else:
            messagebox.showinfo("No File", "No downloaded file found to play.")

    def trigger_open_folder_pulse(self, flashes=14):
        """Pulses the Open Folder and Play buttons green and back to indicate success."""
        if not hasattr(self, 'action_buttons') or "Open Folder" not in self.action_buttons: return
        btn = self.action_buttons["Open Folder"]
        
        preview_btn = None
        preview_play_btn = None
        if getattr(self, 'preview_dialog', None) and self.preview_dialog.winfo_exists():
            preview_btn = getattr(self.preview_dialog, 'preview_open_folder_btn', None)
            preview_play_btn = getattr(self.preview_dialog, 'preview_play_btn', None)
        
        # Stop pulsing if we reached the end
        if flashes <= 0:
            btn.config(bg='#6c757d') # Restore original grey
            if preview_btn: preview_btn.config(bg='#6c757d')
            if preview_play_btn: preview_play_btn.config(bg='#6c757d')
            return
        
        # Toggle color between grey and bright green
        current_bg = btn.cget('bg')
        new_bg = '#00ff00' if current_bg == '#6c757d' else '#6c757d'
        btn.config(bg=new_bg)
        if preview_btn: preview_btn.config(bg=new_bg)
        if preview_play_btn: preview_play_btn.config(bg=new_bg)
        
        # Schedule next toggle (500ms * 14 toggles = 7 seconds)
        self.after(500, self.trigger_open_folder_pulse, flashes - 1)

    def on_open_folder(self):
        """Open download directory in system file browser."""
        try:
            if os.name == 'nt':
                os.startfile(self.download_dir)
            else:
                subprocess.run(['xdg-open', self.download_dir])
        except Exception as e:
            messagebox.showerror("Error", f"Cannot open folder: {e}")

    def on_clear_log(self):
        """Clear the log display."""
        self.log.delete('1.0', 'end')

    def on_export_log(self):
        """Export log to a text file."""
        save_path = filedialog.asksaveasfilename(defaultextension='.txt')
        if save_path:
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(self.log.get('1.0', 'end'))
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.log.insert('end', f"{timestamp} Log saved to {save_path}\n")
            self.log.see('end')

    def on_settings(self):
        """Open the settings dialog."""
        SettingsDialog(self)

    def on_update_tools(self):
        """Install/Update dependencies (yt-dlp, python-vlc) and check FFmpeg/VLC system installations."""
        def update_worker():
            self.after(0, lambda: self.status_label.config(text="Checking and installing tool dependencies..."))
            try:
                # 1. Install/Update pip packages
                packages = ['yt-dlp', 'python-vlc', 'nodejs-bin[cmd]', 'tkwebview2']
                pip_msgs = []
                for pkg in packages:
                    proc = subprocess.Popen([sys.executable, '-m', 'pip', 'install', '-U', pkg], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    out, _ = proc.communicate()
                    if "Requirement already satisfied" in out:
                        pip_msgs.append(f"{pkg} up to date")
                    elif "Successfully installed" in out:
                        pip_msgs.append(f"{pkg} installed/updated")
                    else:
                        pip_msgs.append(f"{pkg} ready")
                
                # 2. Check & Install System FFmpeg
                if shutil.which("ffmpeg"):
                    ff_msg = "FFmpeg OK"
                else:
                    ff_msg = "FFmpeg MISSING"
                    if os.name == 'nt':
                        try:
                            self.after(0, lambda: self.status_label.config(text="Installing FFmpeg via Winget... Please wait."))
                            subprocess.run(['winget', 'install', 'Gyan.FFmpeg', '--silent', '--accept-package-agreements', '--accept-source-agreements'], stdout=subprocess.DEVNULL)
                            ff_msg = "FFmpeg Installed (Restart App)"
                        except FileNotFoundError:
                            pass

                # 3. Check & Install System VLC
                vlc_msg = "VLC OK"
                try:
                    import vlc
                    instance = vlc.Instance('--no-xlib', '--quiet')
                    if not instance: raise Exception()
                except Exception:
                    vlc_msg = "VLC MISSING"
                    if os.name == 'nt' and not os.path.exists(r"C:\Program Files\VideoLAN\VLC\vlc.exe") and not os.path.exists(r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"):
                        try:
                            self.after(0, lambda: self.status_label.config(text="Installing VLC via Winget... Please wait."))
                            subprocess.run(['winget', 'install', 'VideoLAN.VLC', '--silent', '--accept-package-agreements', '--accept-source-agreements'], stdout=subprocess.DEVNULL)
                            vlc_msg = "VLC Installed (Restart App)"
                        except FileNotFoundError:
                            pass

                # Update UI and log to console
                final_msg = f"{' | '.join(pip_msgs)} | {ff_msg} | {vlc_msg}"
                self.after(0, lambda: self.status_label.config(text=final_msg))
                timestamp = datetime.now().strftime('%H:%M:%S')
                print(f"{timestamp} Tools Status: {final_msg}")
            except Exception as e:
                self.after(0, lambda: self.status_label.config(text=f"Error checking tools: {e}"))
                timestamp = datetime.now().strftime('%H:%M:%S')
                print(f"{timestamp} Update Error: {str(e)}")

        # Run in a background thread to prevent GUI freezing
        threading.Thread(target=update_worker, daemon=True).start()

    def on_close(self):
        """Handle application close: save config and exit."""
        self.cfg['pos'] = (self.winfo_x(), self.winfo_y())
        save_cfg(self.cfg)
        self.destroy()


if __name__ == '__main__':
    Mr_AlvinRocks().mainloop()
