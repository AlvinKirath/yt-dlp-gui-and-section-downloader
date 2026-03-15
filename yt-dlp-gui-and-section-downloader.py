import colorsys
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
import os
import sys
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

    # Regex to catch: [download]  15.5% of 10.50MiB at  3.10MiB/s ETA 00:02
    prog_regex = re.compile(r'\[download\]\s+([0-9.]+)%.*?at\s+([a-zA-Z0-9./]+).*?ETA\s+([0-9:]+)')
    # --- NEW: Regex to catch the current downloading file ---
    dest_regex = re.compile(r'\[download\] Destination:\s*(.*)|\[ExtractAudio\] Destination:\s*(.*)')
    downloaded_mp3_path = None

    for line in proc.stdout:
        line_str = line.strip()
        if not line_str: continue
        
        # --- NEW: Check for filename to update the title dynamically ---
        dest_match = dest_regex.search(line_str)
        if dest_match:
                # Group 1 is video, Group 2 is audio. Fallback appropriately.
                raw_path = dest_match.group(1) or dest_match.group(2)
                if raw_path:
                    if raw_path.lower().endswith('.mp3'):
                        downloaded_mp3_path = raw_path
                    filename = os.path.basename(raw_path)
                    # Remove extension for a cleaner look
                    clean_name = os.path.splitext(filename)[0]
                app.after(0, lambda f=clean_name: status_label.config(text=f"Downloading: {f}"))
        # --------------------------------------------------------------

        match = prog_regex.search(line_str)
        if match:
            # We found a progress line! Update the GUI, DO NOT write to log
            pct_val = float(match.group(1))
            speed = match.group(2)
            eta = match.group(3)
            app.after(0, update_progress_gui, pct_val, speed, eta)
        else:
            # Normal output line, send to the terminal
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

def process_csv_file(status_label):
    """Process a CSV batch of URLs with start/end times."""
    file_path = filedialog.askopenfilename(
        filetypes=[("CSV files", "*.csv")]
    )
    if not file_path:
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"{timestamp} CSV batch canceled by user.")
        return

    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            url = row.get('URL', '').strip()
            if not url:
                continue

            start = row.get('Start', '00:00:00')
            end = row.get('End', '00:00:00')
            mode = row.get('Mode', 'video').lower()

            output_template = os.path.join(
                app.download_dir, "%(title)s.%(ext)s"
            )

            cmd = ['yt-dlp', '--force-overwrites']
            if mode == 'video':
                cmd += ['--postprocessor-args', 'ffmpeg:-threads 0 -preset fast -movflags +faststart']
            elif mode == 'audio':
                cmd += ['--postprocessor-args', 'ffmpeg:-threads 0 -movflags +faststart']

            # Then add mode-specific args
            if mode == 'video':
                cmd += [url, '--download-sections', f'*{start}-{end}', '-o', output_template]
            elif mode == 'audio':
                cmd += [url, '--extract-audio', '--audio-format', 'mp3', '--embed-thumbnail',
            '--download-sections', f'*{start}-{end}', '-o', output_template]

            threading.Thread(
                target=stream_process,
                args=(cmd, app.status_label,
                      f"Downloading {mode} {start}-{end}"),
                daemon=True
            ).start()


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
        
        self.format_var = tk.StringVar(value="MP4")
        tk.Radiobutton(opt_frame, text="MP4", variable=self.format_var, value="MP4", bg='#2e2e2e', fg='white', selectcolor='#000000').pack(side='left', padx=5)
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
        cmd = ['yt-dlp', '--flat-playlist', '--dump-json', url]
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
        
        cmd = ['yt-dlp', '--force-overwrites']
        
        # --- NEW: Tell yt-dlp to only download the selected indices ---
        cmd += ['--playlist-items', playlist_items]
        # --------------------------------------------------------------
        
        if fmt == "MP4":
            cmd += ['-f', 'bestvideo+bestaudio', '--merge-output-format', 'mp4', '--postprocessor-args', 'ffmpeg:-threads 0 -preset fast -movflags +faststart']
        elif fmt == "MP3":
            cmd += ['--extract-audio', '--audio-format', 'mp3', '--embed-thumbnail', '--postprocessor-args', 'ffmpeg:-threads 0 -movflags +faststart']
        elif fmt == "BOTH":
            # Downloads the best video, merges to MP4, extracts MP3, and keeps the MP4
            cmd += ['-f', 'bestvideo+bestaudio', '--merge-output-format', 'mp4', '--extract-audio', '--keep-video', '--audio-format', 'mp3', '--postprocessor-args', 'ffmpeg:-threads 0 -preset fast -movflags +faststart']
            
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
        cmd = ['yt-dlp', '--dump-json', self.url]
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
        cmd = ['yt-dlp', '--force-overwrites', '-f', str(format_id), '-o', output_template, self.url]
        
        self.master.run_custom(cmd, f"Downloading format {format_id}")
        self.destroy()


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
                    justify='center', bg='#3e3e3e', fg='white'
                )
                entry.pack(side='left', padx=2)
                target_list.append(entry)

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

        self.res_var = tk.StringVar(value="1080")
        tk.Label(url_frame, text="Res:", bg='#2e2e2e', fg='white').grid(row=0, column=2, padx=5)
        tk.OptionMenu(url_frame, self.res_var, "2160", "1080", "720", "480", "360").grid(row=0, column=3)
        
        # --- NEW: Audio Quality Dropdown ---
        self.audio_q_var = tk.StringVar(value="320")
        tk.Label(url_frame, text="Audio kbps:", bg='#2e2e2e', fg='white').grid(row=0, column=4, padx=5)
        tk.OptionMenu(url_frame, self.audio_q_var, "320", "256", "192", "128").grid(row=0, column=5)

        # Buttons
        btn_frame = tk.Frame(self, bg='#2e2e2e')
        btn_frame.pack(pady=15)
        button_info = [
            ("Video", self.on_download, '#28a745'),
            ("Audio", self.on_audio, '#17a2b8'),
            ("Playlist", self.on_playlist, '#ffc107'),
            ("Open Folder", self.on_open_folder, '#6c757d'),
            ("Settings", self.on_settings, '#ff33ff'),
            ("📋 Paste", self.paste_from_clipboard, '#6c757d'),
            ("🔍 Formats", self.on_format_explorer, '#17a2b8'),
            ("My Channel", self.on_my_channel, '#ff0000'),
            ("Exit", self.on_close, '#dc3545')
        ]
        
        # Grid layout adjusted for new button count
        for idx, (text, cmd, color) in enumerate(button_info):
            btn = tk.Button(
                btn_frame, text=text,
                command=cmd,
                bg=color, fg='white',
                font=(None, 10, 'bold'),
                padx=10, pady=5
            )
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

    def paste_from_clipboard(self):
        """Grabs text from the system clipboard and pastes it into the URL box."""
        try:
            self.url.delete(0, tk.END)
            self.url.insert(0, self.clipboard_get())
            self.validate_url_color() # --- NEW: Trigger validation immediately upon pasting
        except tk.TclError:
            pass # Fails gracefully if clipboard is empty or non-text

    def validate_url_color(self, event=None):
        """Dynamically changes URL box background based on validity."""
        url = self.url.get().strip()
        # Basic regex check for youtube or standard http/https links
        if re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$', url):
            self.url.config(bg='#28a745') # Green
        else:
            self.url.config(bg='#dc3545') # Red

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

    def on_download(self):
        """Start video download with selected timestamps."""
        cmd = ['yt-dlp', '--force-overwrites', '--force-keyframes-at-cuts']
        
        # New resolution logic:
        res = self.res_var.get()
        cmd += ['--format', f'bestvideo[height<={res}]+bestaudio/best', '--merge-output-format', 'mp4']
        
        cmd += ['--postprocessor-args', 'ffmpeg:-threads 0 -preset fast -movflags +faststart']

        url = self.url.get().strip()
        start = ':'.join(e.get() or '00' for e in self.start)
        end = ':'.join(e.get() or '00' for e in self.end)
        output_template = os.path.join(
            self.download_dir, "%(title)s.%(ext)s"
        )
        cmd += [
            url,
            '--download-sections', f'*{start}-{end}',
            '-o', output_template
        ]
        self.run_custom(cmd, f"Downloading {start} - {end}")

    def on_audio(self):
        """Start audio extraction with selected timestamps."""
        url = self.url.get().strip()
        start = ':'.join(e.get() or '00' for e in self.start)
        end = ':'.join(e.get() or '00' for e in self.end)
        output_template = os.path.join(
            self.download_dir, "%(title)s.%(ext)s"
        )
        
        is_full_audio = (start == '00:00:00' and end == '00:00:00')
        
        cmd = [
            'yt-dlp', 
            '--force-overwrites', 
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
            cmd.extend(['--force-keyframes-at-cuts', '--download-sections', f'*{start}-{end}'])
            
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

    def on_close(self):
        """Handle application close: save config and exit."""
        self.cfg['pos'] = (self.winfo_x(), self.winfo_y())
        save_cfg(self.cfg)
        self.destroy()


if __name__ == '__main__':
    Mr_AlvinRocks().mainloop()
