import colorsys
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
"""
YouTube Clip Downloader GUI - Fixed Black Theme, Speed/ETA, Video/Audio Issues
"""
import os
import sys
import csv
import json
import subprocess
import threading
import math
import re
from datetime import datetime

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
    cfg.setdefault('download_dir', os.path.expanduser("~"))
    cfg.setdefault('bg_image', '')
    cfg.setdefault('hw_accel', 'None')
    cfg.setdefault('pos', (100, 100))
    # default to Black
    cfg.setdefault('theme', 'Black')
    return cfg


def save_cfg(cfg):
    """Save configuration to JSON file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)


def detect_hwaccel():
    """Detect available hardware acceleration modes via ffmpeg."""
    try:
        output = subprocess.check_output(
            ['ffmpeg', '-hwaccels'], stderr=subprocess.STDOUT, text=True
        )
        modes = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            # Skip header lines
            if 'Hardware acceleration methods' in line:
                continue
            modes.append(line)
        return modes
    except Exception:
        return []


def stream_process(cmd, log_widget, status_label, prefix_msg=None):
    """Run a subprocess and stream output to the GUI log and status label."""
    if prefix_msg:
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_widget.insert('end', f"{timestamp} {prefix_msg}\n")
        log_widget.see('end')

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

    for line in proc.stdout:
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_widget.insert('end', f"{timestamp} {line.strip()}\n")
        log_widget.see('end')

        # Extract speed: e.g. '  512.34KiB/s'
        speed_match = re.search(r'speed\s*=\s*([0-9.]+[KMG]iB/s)', line)
        # Extract ETA: e.g. 'ETA 00:01:23'
        eta_match = re.search(r'ETA\s*([0-9:]+)', line)

        status_parts = []
        if speed_match:
            status_parts.append(f"Speed: {speed_match.group(1)}")
        if eta_match:
            status_parts.append(f"ETA: {eta_match.group(1)}")

        if status_parts:
            status_label.config(text=' | '.join(status_parts))

    proc.wait()
    final_status = 'Success' if proc.returncode == 0 else 'Failed'
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_widget.insert('end', f"{timestamp} {prefix_msg or 'Command'} - {final_status}\n")
    log_widget.see('end')

    # Reset status label
    status_label.config(text="Speed: -- | ETA: --")


def process_csv_file(log_widget, status_label):
    """Process a CSV batch of URLs with start/end times."""
    file_path = filedialog.askopenfilename(
        filetypes=[("CSV files", "*.csv")]
    )
    if not file_path:
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_widget.insert('end', f"{timestamp} CSV batch canceled by user.\n")
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

            # Safe filename suffix
            safe_start = start.replace(':', '-')
            safe_end = end.replace(':', '-')
            output_template = os.path.join(
                app.download_dir, f"%(title)s_{safe_start}-{safe_end}.%(ext)s"
            )

            cmd = ['yt-dlp', '--force-overwrites']
            if app.hw_var.get() == 'Auto':
                cmd += ['--postprocessor-args', 'ffmpeg:-hwaccel auto']

            if mode == 'video':
                cmd += [
                    url,
                    '--download-sections', f'*{start}-{end}',
                    '-o', output_template
                ]
            elif mode == 'audio':
                cmd += [
                    url,
                    '--extract-audio',
                    '--audio-format', 'mp3',
                    '--download-sections', f'*{start}-{end}',
                    '-o', output_template
                ]

            threading.Thread(
                target=stream_process,
                args=(cmd, app.log, app.status_label,
                      f"Downloading {mode} {start}-{end}"),
                daemon=True
            ).start()


class SettingsDialog(tk.Toplevel):
    """Modal dialog for changing settings."""
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

        # Acceleration mode
        ttk.Label(
            self, text="Hardware Acceleration:",
            background='#2e2e2e', foreground='white'
        ).pack(pady=(10, 0))
        self.hw_var = tk.StringVar(value=parent.cfg.get('hw_accel', 'None'))
        ttk.OptionMenu(
            self, self.hw_var, self.hw_var.get(), 'None', 'Auto'
        ).pack(pady=5)

        # Detect available modes
        ttk.Button(
            self, text="Detect Accels...", command=self.show_hw_modes
        ).pack(pady=(10, 5))

	    # Theme selection
        ttk.Label(
    		self, text="Theme:",
    		background='#000000', foreground='White'
	    ).pack(pady=(10, 0))
        # Initialize from the saved config (defaulting to Black if nothing’s set)
        self.theme_var = tk.StringVar(value="Black")
        themes = ["Black", "Light", "Blue", "Purple"]
        ttk.OptionMenu(
    		self, self.theme_var, self.theme_var.get(), *themes
	    ).pack(pady=5)

        # Close
        ttk.Button(
            self, text="Save & Close", command=self.close
        ).pack(pady=(5, 10))

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

    def show_hw_modes(self):
        modes = detect_hwaccel()
        if modes:
            messagebox.showinfo(
                "Available Hardware Accels",
                "Detected: " + ", ".join(modes)
            )
        else:
            messagebox.showwarning(
                "No Accels Detected",
                "ffmpeg did not report any hwaccel modes."
            )

    def close(self):
        self.parent.cfg['hw_accel'] = self.hw_var.get()
        # Save the newly chosen theme
        self.parent.cfg['theme']    = self.theme_var.get()
        self.parent.apply_theme(self.theme_var.get())
        self.parent.build_ui()
        save_cfg(self.parent.cfg)
        self.destroy()


class Mr_AlvinRocks(tk.Tk):
    """Main application window."""
    def __init__(self):
        super().__init__()
        global app
        app = self
        self.cfg = load_cfg()
        # immediately apply the saved (or default) theme
        self.apply_theme(self.cfg.get('theme', 'Black'))

        # Window setup
        x, y = self.cfg['pos']
        self.geometry(f"+{x}+{y}")
        self.title("Mr. Alvin Rocks - YouTube Clip Downloader")
        self.configure(bg='#000000')

        # Download directory
        self.download_dir = self.cfg['download_dir']
        self.hw_var = tk.StringVar(value=self.cfg.get('hw_accel', 'None'))

        # Background image label
        self.bg_label = tk.Label(self)
        self.bg_label.place(relwidth=1, relheight=1)
        bg_img = self.cfg.get('bg_image')
        if bg_img:
            self.set_background(bg_img)

        # Build UI
        self.build_ui()

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
                "bg": "#000000", "fg": "white", "entry_bg": "#000000", "entry_fg": "white",
                "button_bg": "#444", "button_fg": "white"
            },
            "Light": {
                "bg": "white", "fg": "black", "entry_bg": "white", "entry_fg": "black",
                "button_bg": "#e0e0e0", "button_fg": "black"
            },
            "Blue": {
                "bg": "#1e3a5f", "fg": "white", "entry_bg": "#29527a", "entry_fg": "white",
                "button_bg": "#3a6ea5", "button_fg": "white"
            },
            "Purple": {
                "bg": "#3d1a4f", "fg": "white", "entry_bg": "#5e2e7e", "entry_fg": "white",
                "button_bg": "#8e44ad", "button_fg": "white"
            },
            "Black": {  
                "bg": "#000000", "fg": "white",
                "entry_bg": "#000000", "entry_fg": "white",
                "button_bg": "#000000", "button_fg": "white"
            }
        }
        t = themes.get(theme, themes["Black"])
        self.configure(bg=t["bg"])
        for widget in self.winfo_children():
            try:
                widget.configure(bg=t["bg"], fg=t["fg"])
            except: pass


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
            self, text="Mr Alvin Rocks",
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
            bg='#3e3e3e', fg='white', insertbackground='white'
        )
        self.url.grid(row=0, column=1, padx=5, sticky='w')

        # Status label for speed/ETA
        self.status_label = tk.Label(
            url_frame, text="Speed: -- | ETA: --",
            font=(None, 12), bg='#2e2e2e', fg='lightgreen'
        )
        self.status_label.grid(row=1, column=1, sticky='w', pady=(5,0))

        # Buttons
        btn_frame = tk.Frame(self, bg='#2e2e2e')
        btn_frame.pack(pady=15)
        button_info = [
            ("Download", self.on_download, '#28a745'),
            ("Audio", self.on_audio, '#17a2b8'),
            ("Open Folder", self.on_open_folder, '#6c757d'),
            ("Clear Log", self.on_clear_log, '#dc3545'),
            ("Export Log", self.on_export_log, '#007bff'),
            ("Settings", self.on_settings, '#ff33ff'),
            ("CSV Batch", lambda: process_csv_file(self.log, self.status_label), '#6610f2'),
            ("Exit", self.on_close, '#343a40'),
            ("Help", lambda: messagebox.showinfo("Help", "For help, visit:\nhttps://github.com/yt-dlp gui and Section Downloader"), '#17a2b8'),
            ("About", lambda: messagebox.showinfo("About", "YouTube Clip Downloader v1.0\nCreated by Mr.AlvinRocks"), '#17a2b8'),
            ("Check for Updates", lambda: messagebox.showinfo("Updates", "No updates available."), '#17a2b8'),
            ("Feedback", lambda: messagebox.showinfo("Feedback", "For feedback, visit:\nhttps://github.com/yt-dlp gui and Section Downloader"), '#17a2b8'),
            ("Report Issues", lambda: messagebox.showinfo("Report Issues", "To report issues, visit:\nhttps://github.com/yt-dlp gui and Section Downloader"), '#17a2b8')
        ]
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
            btn.grid(row=row, column=col, padx=5, pady=5, sticky='nsew')
            btn_frame.columnconfigure(col, weight=1)

        # Log box (must pack before progress, otherwise nothing is shown)
        self.log = scrolledtext.ScrolledText(
            self, height=6,
            bg='#1e1e1e', fg='white', insertbackground='white'
        )
        self.log.configure(bg='#1e1e1e', fg='white')
        self.log.pack(fill='both', expand=True, padx=20, pady=(0,10))

        # Progress bar (below the log)
        self.progress = ttk.Progressbar(self, mode='indeterminate')
        self.progress.pack(fill='x', padx=20, pady=(0,20))



    def animate_header(self):
        """Animate header with a full-spectrum rainbow + white breathing effect."""
        # θ runs continuously; map to a hue between 0.0 and 1.0
        hue = (self.theta % (2 * math.pi)) / (2 * math.pi)
        # full saturation/value = rainbow; a tiny pulse to white
        sat = 1.0
        val = 1.0 if math.sin(self.theta * 0.5) > 0 else 0.8  # pulse brightness
        # convert to RGB (each 0–1)
        r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
        # build hex string
        color_hex = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
        # apply and schedule next frame
        self.header.config(fg=color_hex)
        self.theta += 0.05
        self.after(30, self.animate_header)


    def run_custom(self, cmd, msg):
        """Helper to start streaming thread."""
        threading.Thread(
            target=stream_process,
            args=(cmd, self.log, self.status_label, msg),
            daemon=True
        ).start()

    def on_download(self):
        """Start video download with selected timestamps."""
        cmd = ['yt-dlp', '--force-overwrites']
        cmd += ['--format', 'bestvideo+bestaudio', '--merge-output-format', 'mp4']
        if self.hw_var.get() == 'Auto':
            cmd += ['--postprocessor-args', 'ffmpeg:-hwaccel auto']

        url = self.url.get().strip()
        start = ':'.join(e.get() or '00' for e in self.start)
        end = ':'.join(e.get() or '00' for e in self.end)
        safe_start = start.replace(':', '-')
        safe_end = end.replace(':', '-')
        output_template = os.path.join(
                self.download_dir,
            f"%(title)s_{safe_start}-{safe_end}.%(ext)s"
        )
        cmd += [
            url,
            '--download-sections', f'*{start}-{end}',
            '-o', output_template
        ]
        self.run_custom(cmd, f"Downloading {start} - {end}")

    def on_audio(self):
        """Start audio extraction with selected timestamps."""
        cmd = ['yt-dlp', '--force-overwrites']
        cmd += ['--format', 'bestaudio', '--extract-audio', '--audio-format', 'mp3']
        if self.hw_var.get() == 'Auto':
            cmd += ['--postprocessor-args', 'ffmpeg:-hwaccel auto']

        url = self.url.get().strip()
        start = ':'.join(e.get() or '00' for e in self.start)
        end = ':'.join(e.get() or '00' for e in self.end)
        safe_start = start.replace(':', '-')
        safe_end = end.replace(':', '-')
        output_template = os.path.join(
            self.download_dir,
            f"%(title)s_{safe_start}-{safe_end}.%(ext)s"
        )
        cmd += [
            url,
            '--download-sections', f'*{start}-{end}',
            '-o', output_template
        ]
        cmd += ['--postprocessor-args', '-acodec libmp3lame -q:a 0']
        self.run_custom(cmd, f"Extracting audio {start} - {end}")

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