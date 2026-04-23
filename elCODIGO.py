import hashlib
import json
import os
import queue
import random
import re
import shutil
import threading
import time
import tkinter as tk
from io import BytesIO
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
 
import imageio_ffmpeg
import pygame
import requests
import yt_dlp
from mutagen import File as MutagenFile
from mutagen.mp3 import MP3
from PIL import Image, ImageDraw, ImageTk
 
from spotifiApi import SpotifyBuscar
 
 
BASE_DIR = Path(__file__).resolve().parent
MUSIC_DIR = BASE_DIR / "musica"
CACHE_COVERS_DIR = BASE_DIR / "cache" / "covers"
DATA_FILE = BASE_DIR / "playlist.json"
 
MUSIC_DIR.mkdir(exist_ok=True)
CACHE_COVERS_DIR.mkdir(parents=True, exist_ok=True)
 
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}
 
# ── Paleta Dark Luxury Audio ──────────────────────────────────────────────────
COLORS = {
    "bg":           "#0D0D0F",   # fondo principal
    "panel":        "#14141A",   # panel oscuro
    "panel_alt":    "#1C1C24",   # panel alternativo
    "surface":      "#22222E",   # superficie elevada
    "line":         "#2E2E3A",   # bordes sutiles
    "accent":       "#C8974A",   # dorado cálido principal
    "accent_soft":  "#A87840",   # dorado oscuro
    "accent_glow":  "#E8B86D",   # dorado claro / hover
    "text":         "#F0EDE8",   # blanco cálido
    "text2":        "#B8B4AC",   # texto secundario
    "muted":        "#5A5865",   # texto apagado
    "ok":           "#4CC98A",   # verde esmeralda
    "warn":         "#E8875A",   # naranja advertencia
    "chip":         "#282835",   # chip/tag
    "chip_hover":   "#323240",   # chip hover
    "scrollbar":    "#2A2A36",   # scrollbar track
    "progress_bg":  "#1E1E28",   # fondo barra progreso
}
 
FONT_MAIN = "Segoe UI"
FONT_MONO = "Consolas"
 
 
def slugify(text):
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", str(text).strip().lower())
    return clean.strip("-") or "audio"
 
 
def init_audio():
    if os.name == "nt":
        os.environ.setdefault("SDL_AUDIODRIVER", "directsound")
    for driver in ["directsound", "dsound", "winmm"]:
        try:
            if os.name == "nt":
                os.environ["SDL_AUDIODRIVER"] = driver
            pygame.mixer.pre_init(44100, -16, 2, 2048)
            pygame.init()
            pygame.mixer.init()
            return True
        except Exception:
            pygame.quit()
    return False
 
 
def rounded_rect_image(width, height, radius, fill, outline=None, outline_width=1):
    """Devuelve un ImageTk.PhotoImage con rectángulo redondeado."""
    width, height, radius = int(width), int(height), int(radius)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=fill)
    if outline:
        draw.rounded_rectangle(
            (outline_width // 2, outline_width // 2,
             width - 1 - outline_width // 2, height - 1 - outline_width // 2),
            radius=radius, outline=outline, width=outline_width
        )
    return ImageTk.PhotoImage(img)
 
 
class RoundedButton(tk.Frame):
    """Botón con esquinas redondeadas usando Frame + Canvas interno."""
 
    def __init__(self, parent, text, command, width=110, height=36,
                 radius=18, bg_color=None, fg_color=None,
                 bg_hover=None, font=None, accent=False, icon=None):
        self._bg_color = bg_color or (COLORS["accent"] if accent else COLORS["chip"])
        self._fg_color = fg_color or ("white" if accent else COLORS["text"])
        self._bg_hover = bg_hover or (COLORS["accent_glow"] if accent else COLORS["chip_hover"])
        self._text = text
        self._icon = icon
        self._command = command
        self._font = font or (FONT_MAIN, 10, "bold")
        self._pressed = False
        self._width = int(width)
        self._height = int(height)
        self._radius = int(radius)
 
        parent_bg = COLORS["panel"]
        try:
            parent_bg = parent.cget("bg")
        except Exception:
            pass
 
        super().__init__(parent, width=width, height=height,
                         bg=parent_bg, bd=0, highlightthickness=0)
        self.pack_propagate(False)
 
        self._canvas = tk.Canvas(
            self, width=width, height=height,
            bg=parent_bg, highlightthickness=0, bd=0
        )
        self._canvas.place(x=0, y=0, width=width, height=height)
 
        self._draw(self._bg_color)
 
        for w in (self, self._canvas):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._on_press)
            w.bind("<ButtonRelease-1>", self._on_release)
 
    def _draw(self, color):
        self._canvas.delete("all")
        img = rounded_rect_image(self._width, self._height, self._radius, color)
        self._bg_img = img
        self._canvas.create_image(0, 0, anchor="nw", image=img)
        display = (self._icon + "  " + self._text) if self._icon else self._text
        self._canvas.create_text(
            self._width // 2, self._height // 2,
            text=display, fill=self._fg_color,
            font=self._font, anchor="center"
        )
 
    def _on_enter(self, _e):
        self._draw(self._bg_hover)
 
    def _on_leave(self, _e):
        self._draw(self._bg_color if not self._pressed else self._bg_hover)
 
    def _on_press(self, _e):
        self._pressed = True
        self._draw(self._bg_hover)
 
    def _on_release(self, _e):
        self._pressed = False
        self._draw(self._bg_hover)
        if self._command:
            self._command()
 
    def config_colors(self, bg_color=None, fg_color=None):
        if bg_color:
            self._bg_color = bg_color
        if fg_color:
            self._fg_color = fg_color
        self._draw(self._bg_color)
 
    def config(self, **kwargs):
        if "bg" in kwargs:
            self._bg_color = kwargs["bg"]
        if "text" in kwargs:
            self._text = kwargs["text"]
        self._draw(self._bg_color)
 
 
class ProgressBar(tk.Frame):
    """Barra de progreso horizontal (Frame + Canvas interno)."""
 
    def __init__(self, parent, on_seek=None):
        parent_bg = COLORS["panel"]
        try:
            parent_bg = parent.cget("bg")
        except Exception:
            pass
 
        super().__init__(parent, height=28, bg=parent_bg,
                         bd=0, highlightthickness=0)
 
        self.on_seek = on_seek
        self.maximum = 100
        self.value = 0
        self.dragging = False
        self._hover = False
 
        self._canvas = tk.Canvas(
            self, height=28, bg=parent_bg,
            highlightthickness=0, bd=0
        )
        self._canvas.pack(fill="both", expand=True)
 
        for w in (self, self._canvas):
            w.bind("<Button-1>", self._click)
            w.bind("<B1-Motion>", self._drag)
            w.bind("<ButtonRelease-1>", self._release)
            w.bind("<Enter>", lambda _e: self._set_hover(True))
            w.bind("<Leave>", lambda _e: self._set_hover(False))
 
        self._canvas.bind("<Configure>", self.redraw)
 
    def _set_hover(self, val):
        self._hover = val
        self.redraw()
 
    def redraw(self, _event=None):
        self._canvas.delete("all")
        w = max(self._canvas.winfo_width(), 20)
        cy = 14
        track_h = 4 if not self._hover else 6
        thumb_r = 6 if not self._hover else 8
 
        x0, x1 = 14, w - 14
        y0 = cy - track_h // 2
        y1 = cy + track_h // 2
 
        self._create_rounded_rect(x0, y0, x1, y1, track_h // 2, COLORS["progress_bg"])
 
        ratio = 0 if self.maximum <= 0 else self.value / self.maximum
        fill_x = x0 + (x1 - x0) * ratio
        if fill_x > x0:
            self._create_rounded_rect(x0, y0, fill_x, y1, track_h // 2, COLORS["accent"])
 
        self._canvas.create_oval(
            fill_x - thumb_r, cy - thumb_r,
            fill_x + thumb_r, cy + thumb_r,
            fill=COLORS["accent_glow"] if self._hover else COLORS["accent"],
            outline=COLORS["panel_alt"], width=2
        )
 
    def _create_rounded_rect(self, x0, y0, x1, y1, r, color):
        r = min(r, max((y1 - y0) // 2, 1), max((x1 - x0) // 2, 1))
        if r <= 0:
            self._canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline=color)
            return
        self._canvas.create_arc(x0, y0, x0 + 2*r, y1, start=90, extent=180, fill=color, outline=color)
        self._canvas.create_arc(x1 - 2*r, y0, x1, y1, start=270, extent=180, fill=color, outline=color)
        self._canvas.create_rectangle(x0 + r, y0, x1 - r, y1, fill=color, outline=color)
 
    def _value_from_x(self, x):
        w = max(self._canvas.winfo_width(), 20)
        ratio = min(max((x - 14) / (w - 28), 0), 1)
        return ratio * self.maximum
 
    def _click(self, event):
        self.dragging = True
        self.value = self._value_from_x(event.x)
        self.redraw()
 
    def _drag(self, event):
        if self.dragging:
            self.value = self._value_from_x(event.x)
            self.redraw()
 
    def _release(self, event):
        self.dragging = False
        self.value = self._value_from_x(event.x)
        self.redraw()
        if self.on_seek:
            self.on_seek(self.value)
 
    def set(self, value):
        if not self.dragging:
            self.value = min(max(value, 0), self.maximum)
            self.redraw()
 
 
class VolumeKnob(tk.Frame):
    """Barra de volumen vertical estilizada (Frame + Canvas interno)."""
 
    def __init__(self, parent, command=None, initial=70):
        self._value = initial
        self._command = command
        self._dragging = False
 
        parent_bg = COLORS["panel"]
        try:
            parent_bg = parent.cget("bg")
        except Exception:
            pass
 
        super().__init__(parent, width=28, height=110,
                         bg=parent_bg, bd=0, highlightthickness=0)
        self.pack_propagate(False)
 
        self._canvas = tk.Canvas(
            self, width=28, height=110,
            bg=parent_bg, highlightthickness=0, bd=0
        )
        self._canvas.place(x=0, y=0, width=28, height=110)
 
        for w in (self, self._canvas):
            w.bind("<Button-1>", self._on_click)
            w.bind("<B1-Motion>", self._on_drag)
            w.bind("<ButtonRelease-1>", self._on_release)
            w.bind("<MouseWheel>", self._on_scroll)
 
        self._draw()
 
    def _draw(self):
        self._canvas.delete("all")
        cx = 14
        track_top = 8
        track_bot = 102
        track_w = 6
        x0 = cx - track_w // 2
        x1 = cx + track_w // 2
 
        self._create_vrect(x0, track_top, x1, track_bot, 3, COLORS["progress_bg"])
 
        fill_y = track_bot - (track_bot - track_top) * self._value / 100
        if fill_y < track_bot:
            self._create_vrect(x0, fill_y, x1, track_bot, 3, COLORS["accent"])
 
        r = 7
        self._canvas.create_oval(
            cx - r, fill_y - r, cx + r, fill_y + r,
            fill=COLORS["accent_glow"], outline=COLORS["panel_alt"], width=2
        )
 
    def _create_vrect(self, x0, y0, x1, y1, r, color):
        r = min(r, (x1 - x0) // 2, max((y1 - y0) // 2, 1))
        self._canvas.create_arc(x0, y0, x1, y0 + 2*r, start=0, extent=180, fill=color, outline=color)
        self._canvas.create_arc(x0, y1 - 2*r, x1, y1, start=180, extent=180, fill=color, outline=color)
        self._canvas.create_rectangle(x0, y0 + r, x1, y1 - r, fill=color, outline=color)
 
    def _val_from_y(self, y):
        top, bot = 8, 102
        ratio = 1 - min(max((y - top) / (bot - top), 0), 1)
        return ratio * 100
 
    def _on_click(self, e):
        self._dragging = True
        self._value = self._val_from_y(e.y)
        self._draw()
        if self._command:
            self._command(self._value)
 
    def _on_drag(self, e):
        if self._dragging:
            self._value = self._val_from_y(e.y)
            self._draw()
            if self._command:
                self._command(self._value)
 
    def _on_release(self, _e):
        self._dragging = False
 
    def _on_scroll(self, e):
        delta = 5 if e.delta > 0 else -5
        self._value = min(max(self._value + delta, 0), 100)
        self._draw()
        if self._command:
            self._command(self._value)
 
    def get(self):
        return self._value
 
    def set(self, value):
        self._value = min(max(value, 0), 100)
        self._draw()
 
 
class SpotifyDownloader:
    def __init__(self):
        self.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
 
    def _build_paths(self, track):
        text = f"{track.get('title', '')}-{track.get('artist', '')}"
        uid = track.get("id") or hashlib.md5(text.encode("utf-8")).hexdigest()[:10]
        audio_path = MUSIC_DIR / f"{slugify(text)}-{uid}.mp3"
        cover_path = CACHE_COVERS_DIR / f"{uid}.jpg"
        return audio_path, cover_path
 
    def ensure_cover(self, track):
        _audio_path, cover_path = self._build_paths(track)
        if cover_path.exists():
            return str(cover_path)
        url = track.get("cover_url", "")
        if not url:
            return ""
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        cover_path.write_bytes(response.content)
        return str(cover_path)
 
    def ensure_audio(self, track):
        audio_path, _cover_path = self._build_paths(track)
        if audio_path.exists():
            return str(audio_path)
        query = f"{track.get('title', '')} {track.get('artist', '')} audio"
        ydl_opts = {
            "format": "bestaudio/best",
            "default_search": "ytsearch1",
            "noplaylist": True,
            "outtmpl": str(audio_path.with_suffix(".%(ext)s")),
            "quiet": True,
            "no_warnings": True,
            "ffmpeg_location": self.ffmpeg,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([query])
        if not audio_path.exists():
            raise FileNotFoundError("No se pudo crear el MP3 desde YouTube.")
        return str(audio_path)
 
 
class Reproductor:
    def __init__(self, root):
        self.root = root
        self.root.title("JansonMusic")
        self.root.geometry("1400x860")
        self.root.minsize(1200, 720)
        self.root.configure(bg=COLORS["bg"])
 
        self.audio_ok = init_audio()
        self.spotify = SpotifyBuscar.from_env_or_defaults()
        self.downloader = SpotifyDownloader()
        self.ui_queue = queue.Queue()
        self.image_cache = {}
 
        self.library = {}
        self.playlists = {}
        self.spotify_results = []
        self.view_tracks = []
        self.current_track_id = None
        self.current_audio_path = ""
        self.current_duration = 0.0
        self.current_index = -1
        self.current_playlist_name = ""
        self.current_cover_path = ""
        self.is_playing = False
        self.is_paused = False
        self.loop = False
        self.shuffle = False
        self._play_started_at = 0.0
        self._paused_elapsed = 0.0
        self.last_spotify_query = ""
        self.spotify_result_map = {}
        self.spotify_auto_play_in_progress = False
        self.active_left_panel = None
        self.main_cover_size = (56, 56)
 
        self._build_styles()
        self._build_ui()
        self._load_data()
        self._scan_existing_music()
        self._refresh_all_views()
 
        if self.audio_ok:
            pygame.mixer.music.set_volume(0.7)
        else:
            messagebox.showwarning("Audio", "No se pudo iniciar el sistema de audio.")
 
        self.root.after(150, self._process_ui_queue)
        self.root.after(250, self._update_progress)
        self.root.after(500, self._check_end)
 
    def _build_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Treeview",
            background=COLORS["surface"],
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
            rowheight=44,
            bordercolor=COLORS["line"],
            lightcolor=COLORS["line"],
            darkcolor=COLORS["line"],
            font=(FONT_MAIN, 10),
        )
        style.configure(
            "Treeview.Heading",
            background=COLORS["panel_alt"],
            foreground=COLORS["muted"],
            relief="flat",
            borderwidth=0,
            font=(FONT_MAIN, 9, "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", COLORS["accent_soft"])],
            foreground=[("selected", COLORS["text"])],
        )
        # Scrollbar oscuro
        style.configure(
            "Dark.Vertical.TScrollbar",
            background=COLORS["scrollbar"],
            troughcolor=COLORS["panel_alt"],
            arrowcolor=COLORS["muted"],
            bordercolor=COLORS["panel_alt"],
            darkcolor=COLORS["panel_alt"],
            lightcolor=COLORS["panel_alt"],
        )
 
    # ── Helpers de widgets ────────────────────────────────────────────────────
 
    def _make_btn(self, parent, text, command, accent=False, width=110, height=34, icon=None):
        return RoundedButton(
            parent, text=text, command=command,
            width=width, height=height, radius=17,
            accent=accent, icon=icon,
            font=(FONT_MAIN, 10, "bold"),
        )
 
    def _make_chip(self, parent, text, command, width=80, height=28):
        return RoundedButton(
            parent, text=text, command=command,
            width=width, height=height, radius=14,
            bg_color=COLORS["chip"],
            fg_color=COLORS["text2"],
            bg_hover=COLORS["chip_hover"],
            font=(FONT_MAIN, 9, "bold"),
        )
 
    def _label(self, parent, text, font_size=10, bold=False, color=None, **kw):
        w = kw.get("weight", "bold" if bold else "normal")
        return tk.Label(
            parent, text=text,
            font=(FONT_MAIN, font_size, w),
            bg=parent.cget("bg"),
            fg=color or COLORS["text"],
            **{k: v for k, v in kw.items() if k not in ("weight",)}
        )
 
    def _divider(self, parent, pad=(4, 4)):
        tk.Frame(parent, bg=COLORS["line"], height=1).pack(fill="x", padx=12, pady=pad)
 
    def _panel(self, parent, **kw):
        """Frame con fondo surface y borde sutil."""
        return tk.Frame(parent, bg=COLORS["surface"],
                        highlightthickness=1,
                        highlightbackground=COLORS["line"], **kw)
 
    def _set_status(self, text, color=None):
        self.status_label.config(text=text, fg=color or COLORS["text2"])
 
    # ── Build UI ──────────────────────────────────────────────────────────────
 
    def _build_ui(self):
        app = tk.Frame(self.root, bg=COLORS["bg"])
        app.pack(fill="both", expand=True, padx=10, pady=10)
 
        body = tk.Frame(app, bg=COLORS["bg"])
        body.pack(fill="both", expand=True)
 
        # Sidebar
        sidebar = tk.Frame(body, bg=COLORS["panel"], width=270,
                           highlightthickness=1, highlightbackground=COLORS["line"])
        sidebar.pack(side="left", fill="y", padx=(0, 10))
        sidebar.pack_propagate(False)
 
        # Contenido central
        content = tk.Frame(body, bg=COLORS["bg"])
        content.pack(side="left", fill="both", expand=True)
 
        self._build_left(sidebar)
        self._build_center(content)
        self._show_left_panel("songs")
 
    def _build_left(self, parent):
        # ── Brand ──
        brand = tk.Frame(parent, bg=COLORS["panel"])
        brand.pack(fill="x", padx=16, pady=(18, 10))
 
        # Ícono decorativo dorado
        icon_canvas = tk.Canvas(brand, width=36, height=36, bg=COLORS["panel"],
                                highlightthickness=0, bd=0)
        icon_canvas.pack(side="left", padx=(0, 10))
        icon_canvas.create_oval(2, 2, 34, 34, fill=COLORS["accent"], outline="")
        icon_canvas.create_oval(10, 10, 26, 26, fill=COLORS["panel"], outline="")
        icon_canvas.create_oval(15, 15, 21, 21, fill=COLORS["accent"], outline="")
 
        tk.Label(
            brand, text="JansonMusic",
            font=(FONT_MAIN, 15, "bold"),
            bg=COLORS["panel"], fg=COLORS["accent"]
        ).pack(side="left", anchor="w")
 
        self._divider(parent, pad=(0, 8))
 
        # ── Nav buttons ──
        nav = tk.Frame(parent, bg=COLORS["panel"])
        nav.pack(fill="x", padx=14, pady=(0, 8))
 
        self.menu_spotify_btn = self._make_nav_btn(nav, "♪  Canciones", lambda: self._show_left_panel("songs"))
        self.menu_spotify_btn.pack(fill="x", pady=(0, 4))
        self.menu_folder_btn = self._make_nav_btn(nav, "⊞  Carpetas", lambda: self._show_left_panel("folder"))
        self.menu_folder_btn.pack(fill="x", pady=(0, 4))
        self.menu_playlist_btn = self._make_nav_btn(nav, "☰  Playlists", lambda: self._show_left_panel("playlist"))
        self.menu_playlist_btn.pack(fill="x")
 
        self._divider(parent, pad=(8, 6))
 
        # ── Panel container ──
        self.left_panel_container = tk.Frame(parent, bg=COLORS["panel"])
        self.left_panel_container.pack(fill="both", expand=True, padx=14)
        self.left_panel_container.pack_propagate(False)
 
        # --- Panel Canciones ---
        self.songs_panel = tk.Frame(self.left_panel_container, bg=COLORS["panel"])
        tk.Label(
            self.songs_panel,
            text="Modo Canciones\nUsá el buscador superior\npara buscar en Spotify.",
            font=(FONT_MAIN, 10),
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            justify="left",
        ).pack(anchor="w", pady=(10, 0))
 
        # --- Panel Carpeta ---
        self.folder_panel = tk.Frame(self.left_panel_container, bg=COLORS["panel"])
        self.import_btn = self._make_btn(self.folder_panel, "+ Carpeta", self._import_folder,
                                         accent=True, width=200, height=34)
        self.import_btn.pack(pady=(4, 10))
 
        tk.Label(self.folder_panel, text="CARPETAS",
                 font=(FONT_MAIN, 8, "bold"), bg=COLORS["panel"],
                 fg=COLORS["muted"]).pack(anchor="w")
 
        self.folder_listbox = self._make_listbox(self.folder_panel, height=4)
        self.folder_listbox.pack(fill="x", pady=(4, 8))
        self.folder_listbox.bind("<<ListboxSelect>>", lambda _e: self._on_folder_selected())
 
        self._divider(self.folder_panel, pad=(0, 6))
 
        tk.Label(self.folder_panel, text="CANCIONES EN CARPETA",
                 font=(FONT_MAIN, 8, "bold"), bg=COLORS["panel"],
                 fg=COLORS["muted"]).pack(anchor="w")
 
        self.folder_songs_listbox = self._make_listbox(self.folder_panel)
        self.folder_songs_listbox.pack(fill="both", expand=True, pady=(4, 0))
        self.folder_songs_listbox.bind("<Double-1>", lambda _e: self._play_folder_song_selected())
        self.folder_songs_listbox.bind("<<ListboxSelect>>", lambda _e: self._preview_folder_song_selected())
        self._folder_songs_list = []
 
        # --- Panel Playlist ---
        self.playlist_panel = tk.Frame(self.left_panel_container, bg=COLORS["panel"])
        row = tk.Frame(self.playlist_panel, bg=COLORS["panel"])
        row.pack(fill="x", pady=(4, 8))
        self._make_chip(row, "Crear", self._create_playlist, width=88, height=28).pack(side="left", padx=(0, 6))
        self._make_chip(row, "Borrar", self._delete_playlist, width=88, height=28).pack(side="left")
 
        tk.Label(self.playlist_panel, text="PLAYLISTS",
                 font=(FONT_MAIN, 8, "bold"), bg=COLORS["panel"],
                 fg=COLORS["muted"]).pack(anchor="w")
 
        self.playlist_listbox = self._make_listbox(self.playlist_panel, height=4)
        self.playlist_listbox.pack(fill="x", pady=(4, 8))
        self.playlist_listbox.bind("<<ListboxSelect>>", lambda _e: self._on_playlist_selected())
 
        self._divider(self.playlist_panel, pad=(0, 6))
 
        tk.Label(self.playlist_panel, text="CANCIONES EN PLAYLIST",
                 font=(FONT_MAIN, 8, "bold"), bg=COLORS["panel"],
                 fg=COLORS["muted"]).pack(anchor="w")
 
        self.playlist_songs_listbox = self._make_listbox(self.playlist_panel)
        self.playlist_songs_listbox.pack(fill="both", expand=True, pady=(4, 0))
        self.playlist_songs_listbox.bind("<Double-1>", lambda _e: self._play_playlist_song_selected())
        self.playlist_songs_listbox.bind("<<ListboxSelect>>", lambda _e: self._preview_playlist_song_selected())
        self._playlist_songs_list = []
 
        self._divider(parent, pad=(6, 8))
 
        # ── Now Playing card ──
        self._build_now_card(parent)
 
    def _make_nav_btn(self, parent, text, command):
        """Botón de navegación izquierda — texto alineado."""
        btn = tk.Label(
            parent, text=text,
            font=(FONT_MAIN, 10),
            bg=COLORS["panel"],
            fg=COLORS["text2"],
            anchor="w", padx=12, pady=8,
            cursor="hand2",
        )
        btn.bind("<Enter>", lambda _e, b=btn: b.config(bg=COLORS["surface"], fg=COLORS["text"]))
        btn.bind("<Leave>", lambda _e, b=btn: b.config(
            bg=COLORS["accent"] if btn.cget("fg") == "white" else COLORS["panel"],
            fg="white" if btn.cget("bg") == COLORS["accent"] else COLORS["text2"]
        ))
        btn.bind("<Button-1>", lambda _e: command())
        return btn
 
    def _activate_nav_btn(self, btn):
        """Marca un botón de nav como activo."""
        for b in [self.menu_spotify_btn, self.menu_folder_btn, self.menu_playlist_btn]:
            b.config(bg=COLORS["panel"], fg=COLORS["text2"])
        btn.config(bg=COLORS["accent"], fg="white")
 
    def _make_listbox(self, parent, height=8):
        lb = tk.Listbox(
            parent,
            height=height,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            selectbackground=COLORS["accent_soft"],
            selectforeground=COLORS["text"],
            borderwidth=0,
            relief="flat",
            activestyle="none",
            font=(FONT_MAIN, 9),
            highlightthickness=1,
            highlightbackground=COLORS["line"],
        )
        return lb
 
    def _build_now_card(self, parent):
        """Tarjeta 'Now Playing' en el fondo del sidebar."""
        card = tk.Frame(parent, bg=COLORS["surface"],
                        highlightthickness=1, highlightbackground=COLORS["line"])
        card.pack(fill="x", padx=14, pady=(0, 16))
 
        inner = tk.Frame(card, bg=COLORS["surface"])
        inner.pack(fill="x", padx=12, pady=10)
 
        self.now_cover_label = tk.Label(inner, bg=COLORS["surface"])
        self.now_cover_label.pack(side="left", padx=(0, 10))
 
        text_side = tk.Frame(inner, bg=COLORS["surface"])
        text_side.pack(side="left", fill="x", expand=True)
 
        self.now_title_label = tk.Label(
            text_side, text="Sin canción",
            font=(FONT_MAIN, 10, "bold"),
            bg=COLORS["surface"], fg=COLORS["text"],
            wraplength=160, justify="left", anchor="w"
        )
        self.now_title_label.pack(fill="x")
        self.now_artist_label = tk.Label(
            text_side, text="Seleccioná una canción",
            font=(FONT_MAIN, 9),
            bg=COLORS["surface"], fg=COLORS["muted"],
            wraplength=160, justify="left", anchor="w"
        )
        self.now_artist_label.pack(fill="x")
        self._set_now_card_placeholder()
 
    # ── Panel switcher ────────────────────────────────────────────────────────
 
    def _show_left_panel(self, panel_name):
        self.songs_panel.pack_forget()
        self.folder_panel.pack_forget()
        self.playlist_panel.pack_forget()
 
        self.active_left_panel = panel_name
        if panel_name == "songs":
            self.songs_panel.pack(fill="both", expand=True)
            self._activate_nav_btn(self.menu_spotify_btn)
            self.local_results_frame.pack_forget()
            self.spotify_results_frame.pack(fill="both", expand=True)
            self._update_search_hint("Buscar en Spotify...")
        elif panel_name == "playlist":
            self.playlist_panel.pack(fill="both", expand=True)
            self._activate_nav_btn(self.menu_playlist_btn)
            self.local_results_frame.pack_forget()
            self.spotify_results_frame.pack(fill="both", expand=True)
            self._update_search_hint("Buscar en Spotify para agregar a playlist...")
            self._refresh_playlist_songs()
        else:
            self.folder_panel.pack(fill="both", expand=True)
            self._activate_nav_btn(self.menu_folder_btn)
            self.local_results_frame.pack_forget()
            self.spotify_results_frame.pack(fill="both", expand=True)
            self._update_search_hint("Buscar en Spotify para guardar en carpeta...")
            self._refresh_folder_lists()
 
    # ── Build Center ──────────────────────────────────────────────────────────
 
    def _build_center(self, parent):
        # Barra superior de búsqueda
        top = tk.Frame(parent, bg=COLORS["bg"])
        top.pack(fill="x", pady=(0, 8))
 
        search_wrap = tk.Frame(
            top, bg=COLORS["surface"],
            highlightthickness=1, highlightbackground=COLORS["line"]
        )
        search_wrap.pack(side="left", fill="x", expand=True, ipady=0)
 
        # Ícono lupa
        tk.Label(search_wrap, text="🔍", bg=COLORS["surface"],
                 fg=COLORS["muted"], font=(FONT_MAIN, 11)).pack(side="left", padx=(10, 2))
 
        self.spotify_entry = tk.Entry(
            search_wrap,
            bg=COLORS["surface"], fg=COLORS["text"],
            insertbackground=COLORS["accent"],
            relief="flat", bd=0,
            font=(FONT_MAIN, 11)
        )
        self.spotify_entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.spotify_entry.bind("<Return>", lambda _e: self._search_spotify())
 
        self.spotify_btn = self._make_chip(search_wrap, "Buscar", self._search_spotify, width=80, height=30)
        self.spotify_btn.pack(side="right", padx=8, pady=5)
 
        # ── Contenedor resultados ──
        self.results_container = tk.Frame(parent, bg=COLORS["panel_alt"],
                                          highlightthickness=1,
                                          highlightbackground=COLORS["line"])
        self.results_container.pack(fill="both", expand=True, pady=(0, 8))
 
        self.spotify_results_frame = tk.Frame(self.results_container, bg=COLORS["panel_alt"])
        self.local_results_frame = tk.Frame(self.results_container, bg=COLORS["panel_alt"])
 
        # ── Panel de detalle DERECHO ──
        detail_panel = tk.Frame(
            self.spotify_results_frame, bg=COLORS["panel"],
            highlightthickness=1, highlightbackground=COLORS["line"],
            width=290
        )
        detail_panel.pack(side="right", fill="y", padx=(4, 8), pady=8)
        detail_panel.pack_propagate(False)
 
        # Cover grande con borde redondeado via Canvas
        cover_canvas_frame = tk.Frame(detail_panel, bg=COLORS["panel"])
        cover_canvas_frame.pack(fill="x", padx=20, pady=(24, 12))
 
        self.top_preview_image = tk.Label(cover_canvas_frame, bg=COLORS["panel"])
        self.top_preview_image.pack(anchor="center")
        self.cover_label = self.top_preview_image
 
        # Línea dorada decorativa
        gold_bar = tk.Canvas(detail_panel, height=3, bg=COLORS["panel"],
                             highlightthickness=0)
        gold_bar.pack(fill="x", padx=20, pady=(0, 14))
        gold_bar.bind("<Configure>", lambda e, c=gold_bar: (
            c.delete("all"),
            c.create_rectangle(0, 0, e.width, 3, fill=COLORS["accent"], outline="")
        ))
 
        self.top_preview_title = tk.Label(
            detail_panel, text="Sin canción",
            font=(FONT_MAIN, 13, "bold"),
            bg=COLORS["panel"], fg=COLORS["text"],
            anchor="center", justify="center",
            wraplength=250
        )
        self.top_preview_title.pack(fill="x", padx=20)
        self.track_title_label = self.top_preview_title
 
        self.top_preview_artist = tk.Label(
            detail_panel, text="—",
            font=(FONT_MAIN, 10),
            bg=COLORS["panel"], fg=COLORS["accent"],
            anchor="center", justify="center",
            wraplength=250
        )
        self.top_preview_artist.pack(fill="x", padx=20, pady=(6, 0))
        self.track_artist_label = self.top_preview_artist
 
        # ── Tabla Spotify ──
        spotify_left = tk.Frame(self.spotify_results_frame, bg=COLORS["panel_alt"])
        spotify_left.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)
 
        self.spotify_tree = ttk.Treeview(
            spotify_left, columns=("artist",),
            show="tree headings", height=10
        )
        self.spotify_tree.heading("#0", text="Canción")
        self.spotify_tree.heading("artist", text="Artista")
        self.spotify_tree.column("#0", width=230, minwidth=140)
        self.spotify_tree.column("artist", width=150, minwidth=80)
        self.spotify_tree.pack(side="left", fill="both", expand=True)
        self.spotify_tree.bind("<<TreeviewSelect>>", lambda _e: self._on_spotify_tree_selected())
        sp_scroll = ttk.Scrollbar(spotify_left, orient="vertical",
                                  command=self.spotify_tree.yview,
                                  style="Dark.Vertical.TScrollbar")
        sp_scroll.pack(side="right", fill="y")
        self.spotify_tree.configure(yscrollcommand=sp_scroll.set)
 
        self._set_big_cover_placeholder()
 
        # ── Tabla local (oculta) ──
        local_wrap = tk.Frame(self.local_results_frame, bg=COLORS["panel_alt"])
        local_wrap.pack(fill="both", expand=True, padx=8, pady=8)
        cols = ("artist", "album", "genre", "duration")
        self.tree = ttk.Treeview(local_wrap, columns=cols, show="tree headings", height=10)
        self.tree.heading("#0", text="Canción")
        self.tree.heading("artist", text="Artista")
        self.tree.heading("album", text="Álbum")
        self.tree.heading("genre", text="Género")
        self.tree.heading("duration", text="Dur.")
        self.tree.column("#0", width=340, minwidth=160)
        self.tree.column("artist", width=190, minwidth=80)
        self.tree.column("album", width=190, minwidth=80)
        self.tree.column("genre", width=110, minwidth=60)
        self.tree.column("duration", width=70, anchor="center", minwidth=50)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _e: self._play_selected_track())
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._preview_selected_library())
        ybar = ttk.Scrollbar(local_wrap, orient="vertical",
                             command=self.tree.yview,
                             style="Dark.Vertical.TScrollbar")
        ybar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=ybar.set)
 
        # Widgets ocultos para compatibilidad
        self.search_entry = tk.Entry(parent)
        self.search_field_var = tk.StringVar(value="Cancion")
        self.search_field_combo = ttk.Combobox(
            parent, textvariable=self.search_field_var, state="readonly",
            values=["Cancion", "Artista", "Album", "Genero", "Playlist"]
        )
        self.sort_var = tk.StringVar(value="Cancion")
        self.sort_combo = ttk.Combobox(
            parent, textvariable=self.sort_var, state="readonly",
            values=["Cancion", "Artista", "Album", "Genero", "Duracion"]
        )
 
        # ── Barra de controles inferior ──
        self._build_controls(parent)
 
    def _build_controls(self, parent):
        bottom = tk.Frame(parent, bg=COLORS["panel"],
                          highlightthickness=1, highlightbackground=COLORS["line"])
        bottom.pack(fill="x")
 
        # ── Volumen izquierda ──
        vol_frame = tk.Frame(bottom, bg=COLORS["panel"], width=80)
        vol_frame.pack(side="left", fill="y", padx=(14, 8), pady=12)
        vol_frame.pack_propagate(False)
 
        tk.Label(vol_frame, text="VOL", font=(FONT_MAIN, 8, "bold"),
                 bg=COLORS["panel"], fg=COLORS["muted"]).pack()
 
        self.volume_knob = VolumeKnob(vol_frame, command=self._set_volume_knob, initial=70)
        self.volume_knob.configure(bg=COLORS["panel"])
        self.volume_knob.pack(pady=(4, 2))
 
        self.vol_label = tk.Label(vol_frame, text="70%",
                                  font=(FONT_MAIN, 8),
                                  bg=COLORS["panel"], fg=COLORS["accent"])
        self.vol_label.pack()
 
        # Alias para compatibilidad
        self.volume_scale = self.volume_knob
 
        # ── Centro: estado + progreso + botones ──
        center_controls = tk.Frame(bottom, bg=COLORS["panel"])
        center_controls.pack(side="left", fill="both", expand=True, padx=10, pady=10)
 
        self.status_label = tk.Label(
            center_controls, text="Listo",
            font=(FONT_MAIN, 10, "bold"),
            bg=COLORS["panel"], fg=COLORS["accent"]
        )
        self.status_label.pack(anchor="center", pady=(0, 4))
 
        self.progress = ProgressBar(center_controls, on_seek=self._seek_audio)
        self.progress.configure(bg=COLORS["panel"])
        self.progress.pack(fill="x", padx=60, pady=(0, 2))
 
        times = tk.Frame(center_controls, bg=COLORS["panel"])
        times.pack(fill="x", padx=60)
        self.current_time_label = tk.Label(
            times, text="00:00",
            font=(FONT_MONO, 9),
            bg=COLORS["panel"], fg=COLORS["accent"]
        )
        self.current_time_label.pack(side="left")
        self.total_time_label = tk.Label(
            times, text="00:00",
            font=(FONT_MONO, 9),
            bg=COLORS["panel"], fg=COLORS["muted"]
        )
        self.total_time_label.pack(side="right")
 
        # ── Fila de botones ──
        controls_row = tk.Frame(center_controls, bg=COLORS["panel"])
        controls_row.pack(pady=(10, 0))
 
        self.prev_btn = self._make_btn(controls_row, "Prev", self._prev_song, width=64, height=38, icon="◀◀")
        self.prev_btn.pack(side="left", padx=3)
 
        self.stop_btn = self._make_btn(controls_row, "Stop", self._stop_song, width=64, height=38, icon="■")
        self.stop_btn.pack(side="left", padx=3)
 
        self.play_btn = self._make_btn(controls_row, "Play", self._toggle_play,
                                       accent=True, width=96, height=42, icon="▶")
        self.play_btn.pack(side="left", padx=8)
 
        self.next_btn = self._make_btn(controls_row, "Next", self._next_song, width=64, height=38, icon="▶▶")
        self.next_btn.pack(side="left", padx=3)
 
        # Separador visual
        tk.Frame(controls_row, bg=COLORS["panel"], width=16).pack(side="left")
 
        self.shuffle_btn = self._make_btn(controls_row, "Shuffle", self._toggle_shuffle, width=90, height=34)
        self.shuffle_btn.pack(side="left", padx=3)
 
        self.loop_btn = self._make_btn(controls_row, "Loop", self._toggle_loop, width=76, height=34)
        self.loop_btn.pack(side="left", padx=3)
 
        tk.Frame(controls_row, bg=COLORS["panel"], width=16).pack(side="left")
 
        self.add_to_playlist_btn = self._make_btn(controls_row, "Playlist", self._add_selected_to_playlist,
                                                   width=100, height=34, icon="+")
        self.add_to_playlist_btn.pack(side="left", padx=3)
 
        self.pause_btn = self.play_btn
 
    # ── Helpers portada ───────────────────────────────────────────────────────
 
    def _set_big_cover_placeholder(self):
        size = 220
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=22, fill=COLORS["surface"])
        # Patrón decorativo
        draw.ellipse((size // 2 - 50, size // 2 - 50, size // 2 + 50, size // 2 + 50),
                     fill=COLORS["panel_alt"])
        draw.ellipse((size // 2 - 32, size // 2 - 32, size // 2 + 32, size // 2 + 32),
                     fill=COLORS["accent_soft"])
        draw.ellipse((size // 2 - 14, size // 2 - 14, size // 2 + 14, size // 2 + 14),
                     fill=COLORS["panel"])
        photo = ImageTk.PhotoImage(image)
        self.top_preview_image.config(image=photo)
        self.top_preview_image.image = photo
        self.top_preview_title.config(text="Sin canción")
        self.top_preview_artist.config(text="—")
 
    def _set_cover_placeholder(self, text=""):
        self._set_big_cover_placeholder()
 
    def _set_now_card_placeholder(self):
        image = Image.new("RGBA", (44, 44), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, 43, 43), radius=10, fill=COLORS["surface"])
        draw.ellipse((10, 10, 34, 34), fill=COLORS["accent_soft"])
        draw.ellipse((18, 18, 26, 26), fill=COLORS["surface"])
        photo = ImageTk.PhotoImage(image)
        self.now_cover_label.config(image=photo)
        self.now_cover_label.image = photo
        self.now_title_label.config(text="Sin canción")
        self.now_artist_label.config(text="Seleccioná una canción")
 
    def _set_now_card_track(self, title, artist, cover_source=""):
        self.now_title_label.config(text=title or "Sin canción")
        self.now_artist_label.config(text=artist or "Desconocido")
        if cover_source:
            try:
                img = self._load_image(cover_source, (44, 44))
                self.now_cover_label.config(image=img)
                self.now_cover_label.image = img
                return
            except Exception:
                pass
        self._set_now_card_placeholder()
 
    # ── Volume ────────────────────────────────────────────────────────────────
 
    def _set_volume_knob(self, value):
        if self.audio_ok:
            pygame.mixer.music.set_volume(float(value) / 100)
        self.vol_label.config(text=f"{int(value)}%")
 
    def _set_volume(self, value):
        """Alias para compatibilidad con código que llama _set_volume."""
        self._set_volume_knob(float(value))
 
    def _update_search_hint(self, hint):
        current = self.spotify_entry.get()
        if not current or current in (
            "Buscar en Spotify...",
            "Buscar en Spotify para agregar a playlist...",
            "Buscar en Spotify para guardar en carpeta...",
        ):
            self.spotify_entry.delete(0, "end")
            self.spotify_entry.config(fg=COLORS["muted"])
            self.spotify_entry.insert(0, hint)
 
        def _on_focus_in(e):
            val = self.spotify_entry.get()
            if val in (
                "Buscar en Spotify...",
                "Buscar en Spotify para agregar a playlist...",
                "Buscar en Spotify para guardar en carpeta...",
            ):
                self.spotify_entry.delete(0, "end")
                self.spotify_entry.config(fg=COLORS["text"])
 
        def _on_focus_out(e):
            if not self.spotify_entry.get().strip():
                self.spotify_entry.config(fg=COLORS["muted"])
                self.spotify_entry.insert(0, hint)
 
        self.spotify_entry.bind("<FocusIn>", _on_focus_in)
        self.spotify_entry.bind("<FocusOut>", _on_focus_out)
 
    def _get_real_search_query(self):
        val = self.spotify_entry.get().strip()
        if val in (
            "Buscar en Spotify...",
            "Buscar en Spotify para agregar a playlist...",
            "Buscar en Spotify para guardar en carpeta...",
        ):
            return ""
        return val
 
    def _set_spotify_popup_visible(self, visible):
        pass
 
    # ── Library / Data ────────────────────────────────────────────────────────
 
    def _refresh_folder_lists(self):
        if not hasattr(self, "folder_listbox"):
            return
        current = self.folder_listbox.get(self.folder_listbox.curselection()[0]) if self.folder_listbox.curselection() else ""
        folders = sorted(
            {str(Path(track.get("path", "")).parent) for track in self.library.values() if track.get("path")},
            key=str.lower,
        )
        self.folder_listbox.delete(0, "end")
        for folder in folders:
            self.folder_listbox.insert("end", folder)
        if current and current in folders:
            idx = folders.index(current)
            self.folder_listbox.selection_set(idx)
        elif folders:
            self.folder_listbox.selection_set(0)
        self._on_folder_selected()
 
    def _on_folder_selected(self):
        if not hasattr(self, "folder_listbox"):
            return
        sel = self.folder_listbox.curselection()
        self._folder_songs_list = []
        self.folder_songs_listbox.delete(0, "end")
        if not sel:
            return
        folder = self.folder_listbox.get(sel[0])
        tracks = [
            t for t in self.library.values()
            if str(Path(t.get("path", "")).parent) == folder
        ]
        tracks.sort(key=lambda t: t.get("title", "").lower())
        self._folder_songs_list = tracks
        for t in tracks:
            dur = self._format_time(t.get("duration", 0))
            self.folder_songs_listbox.insert("end", f"{t.get('title', '?')}  [{dur}]")
 
    def _play_folder_song_selected(self):
        sel = self.folder_songs_listbox.curselection()
        if not sel:
            return
        track = self._folder_songs_list[sel[0]]
        self.view_tracks = self._folder_songs_list
        self.current_playlist_name = ""
        self._play_track(track)
 
    def _preview_folder_song_selected(self):
        sel = self.folder_songs_listbox.curselection()
        if not sel:
            return
        track = self._folder_songs_list[sel[0]]
        self._show_track_info(track)
 
    def _load_image(self, source, size):
        key = f"{source}|{size}"
        if key in self.image_cache:
            return self.image_cache[key]
        if not source:
            image = Image.new("RGB", size, COLORS["surface"])
        elif str(source).startswith("http"):
            response = requests.get(source, timeout=20)
            response.raise_for_status()
            image = Image.open(BytesIO(response.content))
        else:
            image = Image.open(source)
        image = image.convert("RGB").resize(size, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        self.image_cache[key] = photo
        return photo
 
    def _load_data(self):
        if not DATA_FILE.exists():
            self.library = {}
            self.playlists = {"Favoritos": []}
            self._save_data()
            return
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self.library = {}
                self.playlists = {"Favoritos": []}
                for raw in data:
                    path = Path(raw)
                    if path.exists() and path.suffix.lower() in AUDIO_EXTENSIONS:
                        track = self._extract_metadata(path)
                        self.library[track["id"]] = track
                        self.playlists["Favoritos"].append(track["id"])
                self._save_data()
                return
            self.library = {t["id"]: t for t in data.get("library", []) if isinstance(t, dict) and t.get("id")}
            self.playlists = data.get("playlists", {}) if isinstance(data.get("playlists", {}), dict) else {}
            if not self.playlists:
                self.playlists = {"Favoritos": []}
        except Exception:
            self.library = {}
            self.playlists = {"Favoritos": []}
            self._save_data()
 
        valid_ids = set(self.library.keys())
        for name, ids in list(self.playlists.items()):
            self.playlists[name] = [tid for tid in ids if tid in valid_ids]
 
    def _save_data(self):
        payload = {"library": list(self.library.values()), "playlists": self.playlists}
        DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
 
    def _scan_existing_music(self):
        imported = 0
        for path in MUSIC_DIR.rglob("*"):
            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            tid = self._track_id_from_path(path)
            if tid in self.library:
                continue
            meta = self._extract_metadata(path)
            self.library[tid] = meta
            imported += 1
        if imported:
            self._save_data()
 
    def _track_id_from_path(self, path):
        return hashlib.md5(str(path.resolve()).encode("utf-8")).hexdigest()
 
    def _extract_metadata(self, path, overrides=None):
        path = Path(path)
        overrides = overrides or {}
        title = path.stem
        artist = "Desconocido"
        album = "Desconocido"
        genre = "Desconocido"
        duration = 0.0
        cover_path = ""
 
        try:
            audio = MutagenFile(path, easy=True)
            if audio:
                title = (audio.get("title") or [title])[0]
                artist = (audio.get("artist") or [artist])[0]
                album = (audio.get("album") or [album])[0]
                genre = (audio.get("genre") or [genre])[0]
            mp3 = MP3(path)
            duration = float(mp3.info.length)
            tags = getattr(mp3, "tags", None)
            if tags:
                for key in tags.keys():
                    if key.startswith("APIC"):
                        data = tags[key].data
                        cover_name = f"{self._track_id_from_path(path)}.jpg"
                        cover_target = CACHE_COVERS_DIR / cover_name
                        if not cover_target.exists():
                            cover_target.write_bytes(data)
                        cover_path = str(cover_target)
                        break
        except Exception:
            pass
 
        title = overrides.get("title", title)
        artist = overrides.get("artist", artist)
        album = overrides.get("album", album)
        genre = overrides.get("genre", genre)
        cover_path = overrides.get("cover_path", cover_path)
        source = overrides.get("source", "local")
 
        return {
            "id": self._track_id_from_path(path),
            "path": str(path),
            "title": str(title).strip() or path.stem,
            "artist": str(artist).strip() or "Desconocido",
            "album": str(album).strip() or "Desconocido",
            "genre": str(genre).strip() or "Desconocido",
            "duration": duration,
            "cover_path": cover_path,
            "source": source,
        }
 
    def _refresh_all_views(self):
        self._refresh_playlists_listbox()
        self._refresh_folder_lists()
        self._apply_filter()
 
    def _refresh_playlists_listbox(self):
        current = self._get_selected_playlist_name()
        self.playlist_listbox.delete(0, "end")
        for name in sorted(self.playlists.keys(), key=str.lower):
            self.playlist_listbox.insert("end", name)
        if current and current in self.playlists:
            idx = sorted(self.playlists.keys(), key=str.lower).index(current)
            self.playlist_listbox.selection_clear(0, "end")
            self.playlist_listbox.selection_set(idx)
        self._refresh_playlist_songs()
 
    def _get_selected_playlist_name(self):
        selection = self.playlist_listbox.curselection()
        if not selection:
            return ""
        return self.playlist_listbox.get(selection[0])
 
    def _on_playlist_selected(self):
        self.current_playlist_name = self._get_selected_playlist_name()
        self._refresh_playlist_songs()
        if self.current_playlist_name:
            self._set_status(f"Playlist: {self.current_playlist_name}", COLORS["ok"])
 
    def _refresh_playlist_songs(self):
        if not hasattr(self, "playlist_songs_listbox"):
            return
        self._playlist_songs_list = []
        self.playlist_songs_listbox.delete(0, "end")
        name = self._get_selected_playlist_name()
        if not name or name not in self.playlists:
            return
        ids = self.playlists[name]
        tracks = [self.library[tid] for tid in ids if tid in self.library]
        self._playlist_songs_list = tracks
        for t in tracks:
            dur = self._format_time(t.get("duration", 0))
            self.playlist_songs_listbox.insert("end", f"{t.get('title', '?')}  [{dur}]")
 
    def _play_playlist_song_selected(self):
        sel = self.playlist_songs_listbox.curselection()
        if not sel:
            return
        track = self._playlist_songs_list[sel[0]]
        self.view_tracks = self._playlist_songs_list
        self._play_track(track)
 
    def _preview_playlist_song_selected(self):
        sel = self.playlist_songs_listbox.curselection()
        if not sel:
            return
        track = self._playlist_songs_list[sel[0]]
        self._show_track_info(track)
 
    def _create_playlist(self):
        name = simpledialog.askstring("Nueva playlist", "Nombre de la playlist:")
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in self.playlists:
            messagebox.showwarning("Playlist", "Esa playlist ya existe.")
            return
        self.playlists[name] = []
        self._save_data()
        self._refresh_playlists_listbox()
        self._set_status(f"Playlist creada: {name}", COLORS["ok"])
 
    def _delete_playlist(self):
        name = self._get_selected_playlist_name()
        if not name:
            messagebox.showinfo("Playlist", "Selecciona una playlist para borrar.")
            return
        if not messagebox.askyesno("Confirmar", f"Borrar playlist '{name}'?"):
            return
        self.playlists.pop(name, None)
        self.current_playlist_name = ""
        self._save_data()
        self._refresh_all_views()
        self._set_status("Playlist eliminada.", COLORS["ok"])
 
    def _add_selected_to_playlist(self):
        selected_track = self._get_selected_track_from_tree()
        if not selected_track:
            messagebox.showinfo("Playlist", "Selecciona una canción en la tabla.")
            return
        options = sorted(self.playlists.keys(), key=str.lower)
        if not options:
            messagebox.showinfo("Playlist", "Crea una playlist primero.")
            return
        name = simpledialog.askstring(
            "Agregar a playlist",
            f"Playlists disponibles: {', '.join(options)}\nEscribí el nombre exacto:"
        )
        if not name:
            return
        name = name.strip()
        if name not in self.playlists:
            messagebox.showwarning("Playlist", "La playlist no existe.")
            return
        if selected_track["id"] not in self.playlists[name]:
            self.playlists[name].append(selected_track["id"])
            self._save_data()
        self._set_status(f"'{selected_track['title']}' agregada a '{name}'.", COLORS["ok"])
 
    def _import_folder(self):
        folder = filedialog.askdirectory(title="Selecciona carpeta con música")
        if not folder:
            return
        self._set_status("Importando carpeta...", COLORS["accent"])
        threading.Thread(target=self._import_folder_worker, args=(folder,), daemon=True).start()
 
    def _import_folder_worker(self, folder):
        imported = 0
        for path in Path(folder).rglob("*"):
            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            tid = self._track_id_from_path(path)
            if tid in self.library:
                continue
            track = self._extract_metadata(path)
            self.library[tid] = track
            imported += 1
        self._save_data()
        self.ui_queue.put(("import_done", imported))
 
    def _apply_filter(self):
        query = ""
        field = self.search_field_var.get()
        selected_playlist = self.current_playlist_name
        tracks = list(self.library.values())
 
        if self.active_left_panel == "folder":
            selected = self.folder_listbox.curselection() if hasattr(self, "folder_listbox") else ()
            if selected:
                selected_folder = self.folder_listbox.get(selected[0])
                tracks = [t for t in tracks if str(Path(t.get("path", "")).parent) == selected_folder]
            else:
                tracks = []
 
        if self.active_left_panel == "playlist" and selected_playlist and selected_playlist in self.playlists:
            ids = set(self.playlists[selected_playlist])
            tracks = [t for t in tracks if t["id"] in ids]
 
        if query:
            if field == "Cancion":
                tracks = [t for t in tracks if query in t.get("title", "").lower()]
            elif field == "Artista":
                tracks = [t for t in tracks if query in t.get("artist", "").lower()]
            elif field == "Album":
                tracks = [t for t in tracks if query in t.get("album", "").lower()]
            elif field == "Genero":
                tracks = [t for t in tracks if query in t.get("genre", "").lower()]
            elif field == "Playlist":
                matching = [name for name in self.playlists if query in name.lower()]
                ids = set()
                for name in matching:
                    ids.update(self.playlists.get(name, []))
                tracks = [t for t in tracks if t["id"] in ids]
 
        sort_key = self.sort_var.get()
        if sort_key == "Cancion":
            tracks.sort(key=lambda t: t.get("title", "").lower())
        elif sort_key == "Artista":
            tracks.sort(key=lambda t: t.get("artist", "").lower())
        elif sort_key == "Album":
            tracks.sort(key=lambda t: t.get("album", "").lower())
        elif sort_key == "Genero":
            tracks.sort(key=lambda t: t.get("genre", "").lower())
        elif sort_key == "Duracion":
            tracks.sort(key=lambda t: float(t.get("duration", 0)))
 
        self.view_tracks = tracks
        self._render_library_table()
 
    def _render_library_table(self):
        current_selected = self._get_selected_track_id()
        self.tree.delete(*self.tree.get_children())
        for track in self.view_tracks:
            image = ""
            if self.active_left_panel == "playlist":
                cover = track.get("cover_path", "")
                if cover:
                    try:
                        image = self._load_image(cover, (30, 30))
                    except Exception:
                        image = ""
            self.tree.insert(
                "", "end",
                iid=track["id"],
                text=track.get("title", ""),
                image=image,
                values=(
                    track.get("artist", ""),
                    track.get("album", ""),
                    track.get("genre", ""),
                    self._format_time(track.get("duration", 0)),
                ),
            )
        if current_selected and self.tree.exists(current_selected):
            self.tree.selection_set(current_selected)
            self.tree.focus(current_selected)
 
    def _get_selected_track_id(self):
        sel = self.tree.selection()
        return sel[0] if sel else ""
 
    def _get_selected_track_from_tree(self):
        tid = self._get_selected_track_id()
        return self.library.get(tid)
 
    def _preview_selected_library(self):
        track = self._get_selected_track_from_tree()
        if track:
            self._show_track_info(track)
 
    def _show_track_info(self, track):
        title = track.get("title", "Sin título")
        artist = track.get("artist", "Desconocido")
        album = track.get("album", "Desconocido")
        cover_source = track.get("cover_path", "")
 
        self.track_title_label.config(text=title)
        self.track_artist_label.config(text=f"{artist}  ·  {album}")
        self._set_now_card_track(title, artist, cover_source)
        self.top_preview_title.config(text=title)
        self.top_preview_artist.config(text=f"{artist}  ·  {album}")
 
        if cover_source:
            try:
                img = self._load_image(cover_source, (220, 220))
                self.cover_label.config(image=img)
                self.cover_label.image = img
            except Exception:
                self._set_big_cover_placeholder()
        else:
            self._set_big_cover_placeholder()
 
    def _play_selected_track(self):
        track = self._get_selected_track_from_tree()
        if not track:
            messagebox.showinfo("Reproducción", "Selecciona una canción primero.")
            return
        self._play_track(track)
 
    def _play_track(self, track):
        path = track.get("path", "")
        if not path or not Path(path).exists():
            messagebox.showerror("Archivo", "No se encontró el archivo de audio.")
            return
        if not self.audio_ok:
            messagebox.showerror("Audio", "No se pudo inicializar el audio.")
            return
 
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        pygame.mixer.music.set_volume(self.volume_knob.get() / 100)
 
        self.current_track_id = track["id"]
        self.current_audio_path = path
        self.current_duration = float(track.get("duration", 0))
        self._play_started_at = time.time()
        self._paused_elapsed = 0.0
        self.is_playing = True
        self.is_paused = False
 
        self.current_index = -1
        for idx, item in enumerate(self.view_tracks):
            if item["id"] == track["id"]:
                self.current_index = idx
                break
 
        self.progress.set(0)
        self.current_time_label.config(text="00:00")
        self.total_time_label.config(text=self._format_time(self.current_duration))
        self._show_track_info(track)
        self._set_status(f"Reproduciendo: {track.get('title', '')}", COLORS["ok"])
        self.play_btn.config(text="Pausa", icon="⏸")
        self.play_btn._text = "Pausa"
        self.play_btn._icon = "⏸"
        self.play_btn._draw(self.play_btn._bg_color)
 
    def _toggle_play(self):
        if self.is_playing and not self.is_paused:
            self._toggle_pause()
            return
        if self.is_playing and self.is_paused:
            self._toggle_pause()
            return
        selected = self._get_selected_track_from_tree()
        if selected:
            self._play_track(selected)
            return
        if self.view_tracks:
            self._play_track(self.view_tracks[0])
 
    def _toggle_pause(self):
        if not self.audio_ok or not self.is_playing:
            return
        if self.is_paused:
            pygame.mixer.music.unpause()
            self._play_started_at = time.time()
            self.is_paused = False
            self._set_status("Reproducción reanudada.", COLORS["ok"])
            self.play_btn._text = "Pausa"
            self.play_btn._icon = "⏸"
            self.play_btn._draw(self.play_btn._bg_color)
        else:
            self._paused_elapsed += time.time() - self._play_started_at
            pygame.mixer.music.pause()
            self.is_paused = True
            self._set_status("Pausado.")
            self.play_btn._text = "Play"
            self.play_btn._icon = "▶"
            self.play_btn._draw(self.play_btn._bg_color)
 
    def _stop_song(self):
        if self.audio_ok:
            pygame.mixer.music.stop()
        self.is_playing = False
        self.is_paused = False
        self._paused_elapsed = 0.0
        self.progress.set(0)
        self.current_time_label.config(text="00:00")
        self.play_btn._text = "Play"
        self.play_btn._icon = "▶"
        self.play_btn._draw(self.play_btn._bg_color)
        self._set_status("Detenido.")
 
    def _toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.shuffle_btn._bg_color = COLORS["accent"] if self.shuffle else COLORS["chip"]
        self.shuffle_btn._fg_color = "white" if self.shuffle else COLORS["text"]
        self.shuffle_btn._draw(self.shuffle_btn._bg_color)
        self._set_status("Shuffle activado." if self.shuffle else "Shuffle desactivado.")
 
    def _toggle_loop(self):
        self.loop = not self.loop
        self.loop_btn._bg_color = COLORS["accent"] if self.loop else COLORS["chip"]
        self.loop_btn._fg_color = "white" if self.loop else COLORS["text"]
        self.loop_btn._draw(self.loop_btn._bg_color)
        self._set_status("Loop activado." if self.loop else "Loop desactivado.")
 
    def _next_song(self):
        if not self.view_tracks:
            return
        if self.shuffle:
            idx = random.randrange(len(self.view_tracks))
        else:
            idx = 0 if self.current_index < 0 else (self.current_index + 1) % len(self.view_tracks)
        self.current_index = idx
        track = self.view_tracks[idx]
        if self.tree.exists(track["id"]):
            self.tree.selection_set(track["id"])
            self.tree.focus(track["id"])
        self._play_track(track)
 
    def _prev_song(self):
        if not self.view_tracks:
            return
        idx = len(self.view_tracks) - 1 if self.current_index <= 0 else self.current_index - 1
        self.current_index = idx
        track = self.view_tracks[idx]
        if self.tree.exists(track["id"]):
            self.tree.selection_set(track["id"])
            self.tree.focus(track["id"])
        self._play_track(track)
 
    def _seek_audio(self, percent):
        if not self.is_playing or not self.current_audio_path or self.current_duration <= 0:
            return
        target = (percent / 100) * self.current_duration
        pygame.mixer.music.load(self.current_audio_path)
        pygame.mixer.music.play(start=target)
        pygame.mixer.music.set_volume(self.volume_knob.get() / 100)
        self._paused_elapsed = target
        self._play_started_at = time.time()
        self.is_paused = False
        self.play_btn._text = "Pausa"
        self.play_btn._icon = "⏸"
        self.play_btn._draw(self.play_btn._bg_color)
 
    def _current_seconds(self):
        if not self.is_playing:
            return self._paused_elapsed
        if self.is_paused:
            return self._paused_elapsed
        return min(self._paused_elapsed + (time.time() - self._play_started_at), self.current_duration)
 
    def _update_progress(self):
        if self.is_playing and not self.is_paused:
            sec = self._current_seconds()
            self.current_time_label.config(text=self._format_time(sec))
            if self.current_duration > 0:
                self.progress.set((sec / self.current_duration) * 100)
        self.root.after(250, self._update_progress)
 
    def _check_end(self):
        if self.audio_ok and self.is_playing and not self.is_paused and not pygame.mixer.music.get_busy():
            self.is_playing = False
            if self.loop and self.current_track_id:
                track = self.library.get(self.current_track_id)
                if track:
                    self._play_track(track)
            else:
                self._next_song()
        self.root.after(500, self._check_end)
 
    # ── Spotify ───────────────────────────────────────────────────────────────
 
    def _search_spotify(self):
        query = self._get_real_search_query()
        if not query:
            messagebox.showwarning("Spotify", "Escribí algo para buscar en Spotify.")
            return
        self.last_spotify_query = query
        self.spotify_btn.config(state="disabled")
        self._set_status("Buscando en Spotify...", COLORS["accent"])
        threading.Thread(target=self._spotify_search_worker, args=(query,), daemon=True).start()
 
    def _refresh_spotify(self):
        if not self.last_spotify_query:
            return
        self.spotify_entry.delete(0, "end")
        self.spotify_entry.insert(0, self.last_spotify_query)
        self._search_spotify()
 
    def _spotify_search_worker(self, query):
        try:
            results = self.spotify.buscar_cancion(query, limite=10)
            self.ui_queue.put(("spotify_ok", results, query))
        except Exception as exc:
            self.ui_queue.put(("spotify_err", str(exc)))
 
    def _render_spotify_results(self):
        self.spotify_tree.delete(*self.spotify_tree.get_children())
        self.spotify_result_map = {}
        for idx, track in enumerate(self.spotify_results, start=1):
            iid = f"sp_{idx:03d}"
            cover_source = track.get("cover_url", "")
            try:
                image = self._load_image(cover_source, (36, 36))
            except Exception:
                image = self._load_image("", (36, 36))
 
            self.spotify_tree.insert(
                "", "end",
                iid=iid,
                text=track.get("title", "Desconocido"),
                image=image,
                values=(track.get("artist", "Desconocido"),),
            )
            self.spotify_result_map[iid] = track
 
    def _get_selected_spotify_track(self):
        selection = self.spotify_tree.selection()
        if not selection:
            return None
        return self.spotify_result_map.get(selection[0])
 
    def _on_spotify_tree_selected(self):
        self._preview_selected_spotify()
        track = self._get_selected_spotify_track()
        if not track:
            return
        if self.spotify_auto_play_in_progress:
            return
        self.spotify_auto_play_in_progress = True
 
        if self.active_left_panel == "playlist":
            target_playlist = self._get_selected_playlist_name()
            if target_playlist:
                self._set_status(f"Descargando y agregando a '{target_playlist}'...", COLORS["accent"])
                threading.Thread(
                    target=self._spotify_download_worker, args=(track, True, target_playlist, ""), daemon=True
                ).start()
            else:
                self._set_status("Sin playlist — reproduciendo sin guardar...", COLORS["accent"])
                threading.Thread(
                    target=self._spotify_stream_only_worker, args=(track,), daemon=True
                ).start()
 
        elif self.active_left_panel == "folder":
            sel = self.folder_listbox.curselection()
            if sel:
                target_folder = self.folder_listbox.get(sel[0])
                self._set_status(f"Descargando en '{Path(target_folder).name}'...", COLORS["accent"])
                threading.Thread(
                    target=self._spotify_download_worker, args=(track, True, "", target_folder), daemon=True
                ).start()
            else:
                self._set_status("Sin carpeta — reproduciendo sin guardar...", COLORS["accent"])
                threading.Thread(
                    target=self._spotify_stream_only_worker, args=(track,), daemon=True
                ).start()
 
        else:
            self._set_status("Descargando y reproduciendo...", COLORS["accent"])
            threading.Thread(
                target=self._spotify_download_worker, args=(track, True, "", ""), daemon=True
            ).start()
 
    def _preview_selected_spotify(self):
        track = self._get_selected_spotify_track()
        if not track:
            return
        title = track.get("title", "Sin título")
        artist = track.get("artist", "Desconocido")
        album = track.get("album", "Desconocido")
        self.track_title_label.config(text=title)
        self.track_artist_label.config(text=f"{artist}  ·  {album}")
        cover_source = track.get("cover_url", "")
        self._set_now_card_track(title, artist, cover_source)
        self.top_preview_title.config(text=title)
        self.top_preview_artist.config(text=f"{artist}  ·  {album}")
        if cover_source:
            try:
                img = self._load_image(cover_source, (220, 220))
                self.cover_label.config(image=img)
                self.cover_label.image = img
            except Exception:
                self._set_big_cover_placeholder()
        else:
            self._set_big_cover_placeholder()
 
    def _download_selected_spotify(self):
        track = self._get_selected_spotify_track()
        if not track:
            messagebox.showinfo("Spotify", "Selecciona una canción de Spotify.")
            return
        self._set_status("Descargando desde YouTube...", COLORS["accent"])
        target_playlist = self._get_selected_playlist_name() if self.active_left_panel == "playlist" else ""
        threading.Thread(
            target=self._spotify_download_worker, args=(track, False, target_playlist), daemon=True
        ).start()
 
    def _spotify_stream_only_worker(self, track):
        try:
            local_audio = self.downloader.ensure_audio(track)
            local_cover = self.downloader.ensure_cover(track)
            meta = self._extract_metadata(
                local_audio,
                overrides={
                    "title": track.get("title", ""),
                    "artist": track.get("artist", ""),
                    "album": track.get("album", ""),
                    "genre": track.get("genre", "Desconocido"),
                    "cover_path": local_cover,
                    "source": "spotify_stream_only",
                },
            )
            self.ui_queue.put(("spotify_stream_ok", meta))
        except Exception as exc:
            self.ui_queue.put(("spotify_download_err", str(exc)))
 
    def _spotify_download_worker(self, track, autoplay=False, target_playlist="", target_folder=""):
        try:
            local_audio = self.downloader.ensure_audio(track)
            local_cover = self.downloader.ensure_cover(track)
 
            final_audio = local_audio
            if target_folder:
                dest_dir = Path(target_folder)
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_file = dest_dir / Path(local_audio).name
                if dest_file.resolve() != Path(local_audio).resolve():
                    shutil.copy2(local_audio, dest_file)
                final_audio = str(dest_file)
 
            meta = self._extract_metadata(
                final_audio,
                overrides={
                    "title": track.get("title", ""),
                    "artist": track.get("artist", ""),
                    "album": track.get("album", ""),
                    "genre": track.get("genre", "Desconocido"),
                    "cover_path": local_cover,
                    "source": "spotify_youtube",
                },
            )
            self.library[meta["id"]] = meta
            if target_playlist and target_playlist in self.playlists and meta["id"] not in self.playlists[target_playlist]:
                self.playlists[target_playlist].append(meta["id"])
            self._save_data()
            self.ui_queue.put(("spotify_download_ok", meta, autoplay, target_playlist, target_folder))
        except Exception as exc:
            self.ui_queue.put(("spotify_download_err", str(exc)))
 
    def _process_ui_queue(self):
        try:
            while True:
                item = self.ui_queue.get_nowait()
                kind = item[0]
                if kind == "import_done":
                    imported = item[1]
                    self._refresh_all_views()
                    self._set_status(f"Importación lista: {imported} canciones nuevas.", COLORS["ok"])
                elif kind == "spotify_ok":
                    self.spotify_results = item[1]
                    query = item[2]
                    self.spotify_btn.config(state="normal")
                    self._render_spotify_results()
                    if self.spotify_results:
                        self._set_status(f"Spotify: {len(self.spotify_results)} resultados para '{query}'.", COLORS["ok"])
                    else:
                        self._set_status(f"Sin resultados para '{query}'.", COLORS["warn"])
                elif kind == "spotify_err":
                    self.spotify_btn.config(state="normal")
                    msg = f"Error Spotify: {item[1]}"
                    self._set_status(msg, COLORS["warn"])
                    messagebox.showerror("Error", msg)
                elif kind == "spotify_stream_ok":
                    meta = item[1]
                    self._set_status(f"Reproduciendo: {meta.get('title', '')}", COLORS["accent"])
                    self._play_track(meta)
                    self.spotify_auto_play_in_progress = False
                elif kind == "spotify_download_ok":
                    meta = item[1]
                    autoplay = item[2] if len(item) > 2 else False
                    playlist_name = item[3] if len(item) > 3 else ""
                    folder_name = item[4] if len(item) > 4 else ""
                    self._refresh_all_views()
                    if folder_name:
                        self._set_status(f"Guardada en '{Path(folder_name).name}': {meta.get('title', '')}", COLORS["ok"])
                        self._on_folder_selected()
                    elif playlist_name:
                        self._set_status(f"Agregada a '{playlist_name}': {meta.get('title', '')}", COLORS["ok"])
                        self._refresh_playlist_songs()
                    else:
                        self._set_status(f"Descargada: {meta.get('title', '')}", COLORS["ok"])
                    if autoplay:
                        self._play_track(meta)
                    self.spotify_auto_play_in_progress = False
                elif kind == "spotify_download_err":
                    msg = f"No se pudo descargar: {item[1]}"
                    self._set_status(msg, COLORS["warn"])
                    messagebox.showerror("Error", msg)
                    self.spotify_auto_play_in_progress = False
        except queue.Empty:
            pass
        self.root.after(150, self._process_ui_queue)
 
    @staticmethod
    def _format_time(seconds):
        total = max(int(seconds), 0)
        return f"{total // 60:02d}:{total % 60:02d}"
 
 
if __name__ == "__main__":
    root = tk.Tk()
    app = Reproductor(root)
    root.mainloop()