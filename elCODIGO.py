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

COLORS = {
    "bg": "#d9d9dc",
    "panel": "#070d1a",
    "panel_alt": "#121a2b",
    "line": "#2a3246",
    "accent": "#ff8a24",
    "accent_soft": "#f7a34f",
    "text": "#f1f5f9",
    "muted": "#9aa4b2",
    "ok": "#22c55e",
    "warn": "#ef4444",
    "chip": "#222a3a",
}

FONT_MAIN = "Segoe UI"


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


class ProgressBar(tk.Canvas):
    def __init__(self, parent, on_seek=None):
        super().__init__(parent, height=24, bg=COLORS["panel"], highlightthickness=0, bd=0)
        self.on_seek = on_seek
        self.maximum = 100
        self.value = 0
        self.dragging = False
        self.bind("<Configure>", self.redraw)
        self.bind("<Button-1>", self._click)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.redraw()

    def redraw(self, _event=None):
        self.delete("all")
        width = max(self.winfo_width(), 20)
        y = 12
        self.create_line(10, y, width - 10, y, fill=COLORS["line"], width=8, capstyle="round")
        ratio = 0 if self.maximum <= 0 else self.value / self.maximum
        fill_x = 10 + (width - 20) * ratio
        self.create_line(10, y, fill_x, y, fill=COLORS["accent"], width=8, capstyle="round")
        self.create_oval(fill_x - 7, y - 7, fill_x + 7, y + 7, fill=COLORS["text"], outline="")

    def _value_from_x(self, x):
        width = max(self.winfo_width(), 20)
        ratio = min(max((x - 10) / (width - 20), 0), 1)
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
        self.root.title("Reproductor de Musica - Tkinter")
        self.root.geometry("1320x820")
        self.root.minsize(1080, 680)
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
        self.main_cover_size = (280, 280)

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
            background=COLORS["panel_alt"],
            fieldbackground=COLORS["panel_alt"],
            foreground=COLORS["text"],
            rowheight=54,
            bordercolor=COLORS["line"],
            lightcolor=COLORS["line"],
            darkcolor=COLORS["line"],
        )
        style.configure(
            "Treeview.Heading",
            background=COLORS["panel"],
            foreground=COLORS["muted"],
            relief="flat",
            borderwidth=0,
        )
        style.map(
            "Treeview",
            background=[("selected", "#273148")],
            foreground=[("selected", "#ffffff")],
        )

    def _build_ui(self):
        wrapper = tk.Frame(self.root, bg=COLORS["bg"])
        wrapper.pack(fill="both", expand=True, padx=26, pady=22)

        app = tk.Frame(wrapper, bg=COLORS["panel"], highlightthickness=1, highlightbackground=COLORS["line"])
        app.pack(fill="both", expand=True)

        topbar = tk.Frame(app, bg=COLORS["panel"])
        topbar.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(topbar, text="  ", bg="#ff5f57", width=2).pack(side="left", padx=(0, 6))
        tk.Label(topbar, text="  ", bg="#febc2e", width=2).pack(side="left", padx=(0, 6))
        tk.Label(topbar, text="  ", bg="#28c840", width=2).pack(side="left")

        body = tk.Frame(app, bg=COLORS["panel"])
        body.pack(fill="both", expand=True, padx=10, pady=(2, 10))

        sidebar = tk.Frame(body, bg=COLORS["panel_alt"], width=280)
        sidebar.pack(side="left", fill="y", padx=(14, 12), pady=14)
        sidebar.pack_propagate(False)

        content = tk.Frame(body, bg=COLORS["panel"])
        content.pack(side="left", fill="both", expand=True, padx=(0, 14), pady=14)

        self._build_left(sidebar)
        self._build_center(content)
        self._show_left_panel("songs")

    def _build_left(self, parent):
        parent.configure(highlightthickness=1, highlightbackground=COLORS["line"])

        brand = tk.Frame(parent, bg=COLORS["panel_alt"])
        brand.pack(fill="x", padx=14, pady=(10, 10))
        tk.Label(brand, text="RhythmoTune", font=(FONT_MAIN, 18, "bold"), bg=COLORS["panel_alt"], fg=COLORS["accent"]).pack(anchor="w")

        nav = tk.Frame(parent, bg=COLORS["panel_alt"])
        nav.pack(fill="x", padx=14, pady=(0, 10))
        self.menu_spotify_btn = self._make_btn(nav, "Canciones", lambda: self._show_left_panel("songs"))
        self.menu_spotify_btn.pack(fill="x", pady=(0, 6))
        self.menu_folder_btn = self._make_btn(nav, "Carpeta", lambda: self._show_left_panel("folder"))
        self.menu_folder_btn.pack(fill="x", pady=(0, 6))
        self.menu_playlist_btn = self._make_btn(nav, "Playlist", lambda: self._show_left_panel("playlist"))
        self.menu_playlist_btn.pack(fill="x")

        self.left_panel_container = tk.Frame(parent, bg=COLORS["panel_alt"])
        self.left_panel_container.pack(fill="both", expand=True, padx=14, pady=(4, 8))
        self.left_panel_container.pack_propagate(False)

        self.songs_panel = tk.Frame(self.left_panel_container, bg=COLORS["panel_alt"])
        self.folder_panel = tk.Frame(self.left_panel_container, bg=COLORS["panel_alt"])
        self.playlist_panel = tk.Frame(self.left_panel_container, bg=COLORS["panel_alt"])

        tk.Label(
            self.songs_panel,
            text="Modo Canciones\nUsa el buscador superior para buscar en Spotify.",
            font=(FONT_MAIN, 10),
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

        self.import_btn = self._make_btn(self.folder_panel, "Agregar carpeta", self._import_folder, accent=True)
        self.import_btn.pack(fill="x", pady=(0, 8))
        tk.Label(self.folder_panel, text="Carpetas", font=(FONT_MAIN, 10, "bold"), bg=COLORS["panel_alt"], fg=COLORS["text"]).pack(anchor="w")
        self.folder_listbox = tk.Listbox(
            self.folder_panel,
            height=5,
            bg=COLORS["chip"],
            fg=COLORS["text"],
            selectbackground=COLORS["accent"],
            selectforeground="white",
            borderwidth=0,
            relief="flat",
            activestyle="none",
        )
        self.folder_listbox.pack(fill="x", pady=(6, 10))
        self.folder_listbox.bind("<<ListboxSelect>>", lambda _e: self._on_folder_selected())

        row = tk.Frame(self.playlist_panel, bg=COLORS["panel_alt"])
        row.pack(fill="x", pady=(0, 8))
        self.new_playlist_btn = self._make_chip(row, "Crear playlist", self._create_playlist)
        self.new_playlist_btn.pack(side="left", padx=(0, 6))
        self.del_playlist_btn = self._make_chip(row, "Borrar", self._delete_playlist)
        self.del_playlist_btn.pack(side="left")
        self.playlist_listbox = tk.Listbox(
            self.playlist_panel,
            height=8,
            bg=COLORS["chip"],
            fg=COLORS["text"],
            selectbackground=COLORS["accent"],
            selectforeground="white",
            borderwidth=0,
            relief="flat",
            activestyle="none",
        )
        self.playlist_listbox.pack(fill="both", expand=True)
        self.playlist_listbox.bind("<<ListboxSelect>>", lambda _e: self._on_playlist_selected())
        tk.Label(
            self.playlist_panel,
            text="Selecciona playlist y luego una canción de Spotify para agregar.",
            font=(FONT_MAIN, 9),
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
        ).pack(anchor="w", pady=(8, 0))

        self.now_card = tk.Frame(parent, bg=COLORS["chip"], highlightthickness=1, highlightbackground=COLORS["line"])
        self.now_cover_label = tk.Label(self.now_card, bg=COLORS["chip"])
        self.now_cover_label.pack(pady=(10, 6))
        self.now_title_label = tk.Label(self.now_card, text="Sin cancion", font=(FONT_MAIN, 11, "bold"), bg=COLORS["chip"], fg=COLORS["text"], wraplength=220, justify="center")
        self.now_title_label.pack(fill="x", padx=10)
        self.now_artist_label = tk.Label(self.now_card, text="Selecciona una cancion", font=(FONT_MAIN, 9), bg=COLORS["chip"], fg=COLORS["muted"], wraplength=220, justify="center")
        self.now_artist_label.pack(fill="x", padx=10, pady=(2, 10))

        self._set_now_card_placeholder()

    def _show_left_panel(self, panel_name):
        self.songs_panel.pack_forget()
        self.folder_panel.pack_forget()
        self.playlist_panel.pack_forget()

        self.menu_spotify_btn.config(bg=COLORS["chip"], fg=COLORS["text"])
        self.menu_folder_btn.config(bg=COLORS["chip"], fg=COLORS["text"])
        self.menu_playlist_btn.config(bg=COLORS["chip"], fg=COLORS["text"])

        self.active_left_panel = panel_name
        if panel_name == "songs":
            self.songs_panel.pack(fill="both", expand=True)
            self.menu_spotify_btn.config(bg=COLORS["accent"], fg="white")
            self._set_spotify_popup_visible(True)
            self.local_results_frame.pack_forget()
            self.spotify_results_frame.pack(fill="both", expand=True)
            self.mode_download_btn.pack_forget()
        elif panel_name == "playlist":
            self.playlist_panel.pack(fill="both", expand=True)
            self.menu_playlist_btn.config(bg=COLORS["accent"], fg="white")
            self._set_spotify_popup_visible(True)
            self.spotify_results_frame.pack_forget()
            self.local_results_frame.pack(fill="both", expand=True)
            self.mode_download_btn.pack_forget()
            self._apply_filter()
        else:
            self.folder_panel.pack(fill="both", expand=True)
            self.menu_folder_btn.config(bg=COLORS["accent"], fg="white")
            self._set_spotify_popup_visible(True)
            self.spotify_results_frame.pack_forget()
            self.local_results_frame.pack(fill="both", expand=True)
            self.mode_download_btn.pack(pady=(0, 8))
            self._refresh_folder_lists()
            self._apply_filter()

    def _build_center(self, parent):
        # Barra superior centrada + preview a la derecha
        top = tk.Frame(parent, bg=COLORS["panel"])
        top.pack(fill="x", pady=(0, 10))

        center_search = tk.Frame(top, bg=COLORS["panel"])
        center_search.pack(side="left", fill="x", expand=True)
        search_wrap = tk.Frame(center_search, bg=COLORS["chip"], width=540, height=66, highlightthickness=1, highlightbackground=COLORS["line"])
        search_wrap.pack(pady=2)
        search_wrap.pack_propagate(False)
        self.spotify_entry = tk.Entry(
            search_wrap, bg=COLORS["chip"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", bd=0, font=(FONT_MAIN, 14)
        )
        self.spotify_entry.pack(side="left", fill="x", expand=True, padx=(14, 8), ipady=10)
        self.spotify_entry.bind("<Return>", lambda _e: self._search_spotify())
        self.spotify_btn = self._make_chip(search_wrap, "Buscar", self._search_spotify)
        self.spotify_btn.pack(side="right", padx=10, pady=10)

        preview_top = tk.Frame(top, bg=COLORS["panel_alt"], highlightthickness=1, highlightbackground=COLORS["line"], width=310, height=82)
        preview_top.pack(side="right", padx=(10, 0))
        preview_top.pack_propagate(False)
        self.top_preview_image = tk.Label(preview_top, bg=COLORS["panel_alt"])
        self.top_preview_image.pack(side="left", padx=10, pady=8)
        # Compatibilidad con funciones existentes que actualizan cover_label
        self.cover_label = self.top_preview_image
        text_wrap = tk.Frame(preview_top, bg=COLORS["panel_alt"])
        text_wrap.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=8)
        self.top_preview_title = tk.Label(text_wrap, text="Sin cancion", font=(FONT_MAIN, 11, "bold"), bg=COLORS["panel_alt"], fg=COLORS["text"], anchor="w")
        self.top_preview_title.pack(fill="x")
        self.top_preview_artist = tk.Label(text_wrap, text="?", font=(FONT_MAIN, 9), bg=COLORS["panel_alt"], fg=COLORS["muted"], anchor="w")
        self.top_preview_artist.pack(fill="x", pady=(2, 0))

        # Lista principal (segun modo)
        self.results_container = tk.Frame(parent, bg=COLORS["panel_alt"], highlightthickness=1, highlightbackground=COLORS["line"])
        self.results_container.pack(fill="both", expand=True, pady=(0, 10))

        self.spotify_results_frame = tk.Frame(self.results_container, bg=COLORS["panel_alt"])
        self.local_results_frame = tk.Frame(self.results_container, bg=COLORS["panel_alt"])

        spotify_results_wrap = tk.Frame(self.spotify_results_frame, bg=COLORS["panel_alt"])
        spotify_results_wrap.pack(fill="both", expand=True, padx=10, pady=10)
        self.spotify_tree = ttk.Treeview(spotify_results_wrap, columns=("artist", "album"), show="tree headings", height=9)
        self.spotify_tree.heading("#0", text="Cancion")
        self.spotify_tree.heading("artist", text="Artista")
        self.spotify_tree.heading("album", text="Album")
        self.spotify_tree.column("#0", width=360)
        self.spotify_tree.column("artist", width=220)
        self.spotify_tree.column("album", width=220)
        self.spotify_tree.pack(side="left", fill="both", expand=True)
        self.spotify_tree.bind("<<TreeviewSelect>>", lambda _e: self._on_spotify_tree_selected())
        sp_scroll = ttk.Scrollbar(spotify_results_wrap, orient="vertical", command=self.spotify_tree.yview)
        sp_scroll.pack(side="right", fill="y")
        self.spotify_tree.configure(yscrollcommand=sp_scroll.set)

        local_wrap = tk.Frame(self.local_results_frame, bg=COLORS["panel_alt"])
        local_wrap.pack(fill="both", expand=True, padx=10, pady=10)
        cols = ("artist", "album", "genre", "duration")
        self.tree = ttk.Treeview(local_wrap, columns=cols, show="tree headings", height=9)
        self.tree.heading("#0", text="Cancion")
        self.tree.heading("artist", text="Artista")
        self.tree.heading("album", text="Album")
        self.tree.heading("genre", text="Genero")
        self.tree.heading("duration", text="Duracion")
        self.tree.column("#0", width=340)
        self.tree.column("artist", width=180)
        self.tree.column("album", width=190)
        self.tree.column("genre", width=120)
        self.tree.column("duration", width=90, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _e: self._play_selected_track())
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._preview_selected_library())
        ybar = ttk.Scrollbar(local_wrap, orient="vertical", command=self.tree.yview)
        ybar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=ybar.set)

        self.mode_download_btn = self._make_btn(self.local_results_frame, "Descargar", self._download_current_to_folder, accent=True)

        # Compat con filtros existentes
        self.search_entry = tk.Entry(parent)
        self.search_field_var = tk.StringVar(value="Cancion")
        self.search_field_combo = ttk.Combobox(parent, textvariable=self.search_field_var, state="readonly", values=["Cancion", "Artista", "Album", "Genero", "Playlist"])
        self.sort_var = tk.StringVar(value="Cancion")
        self.sort_combo = ttk.Combobox(parent, textvariable=self.sort_var, state="readonly", values=["Cancion", "Artista", "Album", "Genero", "Duracion"])

        # Controles inferiores centrados
        bottom = tk.Frame(parent, bg=COLORS["panel_alt"], highlightthickness=1, highlightbackground=COLORS["line"])
        bottom.pack(fill="x")

        vol_wrap = tk.Frame(bottom, bg=COLORS["panel_alt"], width=90)
        vol_wrap.pack(side="left", fill="y", padx=12, pady=8)
        tk.Label(vol_wrap, text="Vol", font=(FONT_MAIN, 10, "bold"), bg=COLORS["panel_alt"], fg=COLORS["text"]).pack()
        self.volume_scale = tk.Scale(
            vol_wrap,
            from_=0,
            to=100,
            orient="vertical",
            command=self._set_volume,
            showvalue=False,
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            troughcolor=COLORS["line"],
            activebackground=COLORS["accent"],
            relief="flat",
            highlightthickness=0,
            length=120,
            width=10,
        )
        self.volume_scale.set(70)
        self.volume_scale.pack()

        center_controls = tk.Frame(bottom, bg=COLORS["panel_alt"])
        center_controls.pack(side="left", fill="x", expand=True, padx=8, pady=8)
        self.status_label = tk.Label(center_controls, text="Listo", font=(FONT_MAIN, 10, "bold"), bg=COLORS["panel_alt"], fg=COLORS["accent_soft"])
        self.status_label.pack(anchor="center")

        self.progress = ProgressBar(center_controls, on_seek=self._seek_audio)
        self.progress.configure(bg=COLORS["panel_alt"], height=26)
        self.progress.pack(fill="x", padx=120, pady=(2, 2))

        times = tk.Frame(center_controls, bg=COLORS["panel_alt"])
        times.pack(fill="x", padx=120)
        self.current_time_label = tk.Label(times, text="00:00", font=("Consolas", 10), bg=COLORS["panel_alt"], fg=COLORS["text"])
        self.current_time_label.pack(side="left")
        self.total_time_label = tk.Label(times, text="00:00", font=("Consolas", 10), bg=COLORS["panel_alt"], fg=COLORS["muted"])
        self.total_time_label.pack(side="right")

        controls_row = tk.Frame(center_controls, bg=COLORS["panel_alt"])
        controls_row.pack(pady=(8, 0))
        self.prev_btn = self._make_btn(controls_row, "Anterior", self._prev_song)
        self.prev_btn.pack(side="left", padx=4)
        self.stop_btn = self._make_btn(controls_row, "Stop", self._stop_song)
        self.stop_btn.pack(side="left", padx=4)
        self.play_btn = self._make_btn(controls_row, "Play", self._toggle_play, accent=True)
        self.play_btn.pack(side="left", padx=8)
        self.next_btn = self._make_btn(controls_row, "Siguiente", self._next_song)
        self.next_btn.pack(side="left", padx=4)
        self.shuffle_btn = self._make_btn(controls_row, "Shuffle", self._toggle_shuffle)
        self.shuffle_btn.pack(side="left", padx=4)
        self.loop_btn = self._make_btn(controls_row, "Loop", self._toggle_loop)
        self.loop_btn.pack(side="left", padx=4)
        self.add_to_playlist_btn = self._make_btn(controls_row, "Agregar", self._add_selected_to_playlist)
        self.add_to_playlist_btn.pack(side="left", padx=4)

        self.pause_btn = self.play_btn

        self._set_cover_placeholder("?")

    def _make_btn(self, parent, text, command, accent=False):
        return tk.Button(
            parent,
            text=text,
            command=command,
            font=(FONT_MAIN, 10, "bold"),
            bg=COLORS["accent"] if accent else COLORS["chip"],
            fg="white" if accent else COLORS["text"],
            activebackground=COLORS["accent_soft"] if accent else COLORS["panel_alt"],
            activeforeground="white" if accent else COLORS["text"],
            relief="flat",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=COLORS["line"],
            padx=12,
            pady=9,
            cursor="hand2",
        )

    def _make_chip(self, parent, text, command):
        return tk.Button(
            parent,
            text=text,
            command=command,
            font=(FONT_MAIN, 9, "bold"),
            bg=COLORS["chip"],
            fg=COLORS["text"],
            activebackground=COLORS["panel_alt"],
            activeforeground=COLORS["text"],
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=6,
            cursor="hand2",
        )

    def _set_status(self, text, color=None):
        self.status_label.config(text=text, fg=color or COLORS["accent_soft"])

    def _set_cover_placeholder(self, text):
        size = self.main_cover_size[0]
        image = Image.new("RGB", (size, size), COLORS["panel_alt"])
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=24, fill=COLORS["panel_alt"])
        draw.ellipse((size // 2 - 44, size // 2 - 54, size // 2 + 44, size // 2 + 34), fill=COLORS["accent"])
        draw.text((size // 2 - 46, size - 34), text[:12], fill=COLORS["text"])
        photo = ImageTk.PhotoImage(image)
        self.cover_label.config(image=photo)
        self.cover_label.image = photo
        small = Image.new("RGB", (52, 52), COLORS["chip"])
        d2 = ImageDraw.Draw(small)
        d2.ellipse((10, 10, 42, 42), fill=COLORS["accent"])
        sp = ImageTk.PhotoImage(small)
        self.top_preview_image.config(image=sp)
        self.top_preview_image.image = sp
        self.top_preview_title.config(text="Sin cancion")
        self.top_preview_artist.config(text="?")

    def _set_now_card_placeholder(self):
        image = Image.new("RGB", (96, 96), COLORS["panel"])
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, 95, 95), radius=14, fill=COLORS["panel"])
        draw.ellipse((26, 20, 70, 64), fill=COLORS["accent"])
        photo = ImageTk.PhotoImage(image)
        self.now_cover_label.config(image=photo)
        self.now_cover_label.image = photo
        self.now_title_label.config(text="Sin cancion")
        self.now_artist_label.config(text="Selecciona una cancion")

    def _set_now_card_track(self, title, artist, cover_source=""):
        self.now_title_label.config(text=title or "Sin cancion")
        self.now_artist_label.config(text=artist or "Desconocido")
        if cover_source:
            try:
                img = self._load_image(cover_source, (96, 96))
                self.now_cover_label.config(image=img)
                self.now_cover_label.image = img
                return
            except Exception:
                pass
        image = Image.new("RGB", (96, 96), COLORS["panel"])
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, 95, 95), radius=14, fill=COLORS["panel"])
        draw.ellipse((26, 20, 70, 64), fill=COLORS["accent"])
        photo = ImageTk.PhotoImage(image)
        self.now_cover_label.config(image=photo)
        self.now_cover_label.image = photo

    def _set_spotify_popup_visible(self, visible):
        if hasattr(self, "spotify_popup_holder"):
            self.spotify_popup_holder.configure(height=230 if visible else 0)
            return
        # Compatibilidad: en layouts nuevos sin spotify_popup_holder
        if hasattr(self, "spotify_entry"):
            self.spotify_entry.configure(state="normal" if visible else "disabled")
        if hasattr(self, "spotify_btn"):
            self.spotify_btn.configure(state="normal" if visible else "disabled")

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
        if not sel:
            return
        self._apply_filter()

    def _play_selected_folder_song(self):
        pass

    def _download_current_to_folder(self):
        if self.active_left_panel != "folder":
            return
        if not self.current_audio_path or not Path(self.current_audio_path).exists():
            messagebox.showinfo("Descargar", "No hay cancion reproduciendose para descargar.")
            return
        sel = self.folder_listbox.curselection()
        if not sel:
            messagebox.showinfo("Descargar", "Selecciona una carpeta destino.")
            return
        target_folder = Path(self.folder_listbox.get(sel[0]))
        if not target_folder.exists():
            messagebox.showerror("Descargar", "La carpeta seleccionada no existe.")
            return
        src = Path(self.current_audio_path)
        target = target_folder / src.name
        try:
            if src.resolve() == target.resolve():
                self._set_status("La cancion ya esta en esta carpeta.", COLORS["muted"])
                return
        except Exception:
            pass
        shutil.copy2(src, target)
        self._set_status(f"Cancion descargada en {target_folder}", COLORS["ok"])

    def _clear_search_placeholder(self):
        if self.spotify_entry.get().strip().lower() == "search for a song":
            self.spotify_entry.delete(0, "end")

    def _load_image(self, source, size):
        key = f"{source}|{size}"
        if key in self.image_cache:
            return self.image_cache[key]
        if not source:
            image = Image.new("RGB", size, COLORS["panel_alt"])
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

    def _get_selected_playlist_name(self):
        selection = self.playlist_listbox.curselection()
        if not selection:
            return ""
        return self.playlist_listbox.get(selection[0])

    def _on_playlist_selected(self):
        self.current_playlist_name = self._get_selected_playlist_name()
        self._apply_filter()
        if self.current_playlist_name:
            self._set_status(f"Mostrando playlist: {self.current_playlist_name}", COLORS["ok"])

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
            messagebox.showinfo("Playlist", "Selecciona una cancion en la tabla.")
            return
        options = sorted(self.playlists.keys(), key=str.lower)
        if not options:
            messagebox.showinfo("Playlist", "Crea una playlist primero.")
            return
        name = simpledialog.askstring("Agregar a playlist", f"Playlists disponibles: {', '.join(options)}\nEscribe el nombre exacto:")
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
        folder = filedialog.askdirectory(title="Selecciona carpeta con musica")
        if not folder:
            return
        self._set_status("Importando carpeta...", COLORS["accent_soft"])
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
                "",
                "end",
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
        title = track.get("title", "Sin titulo")
        artist = track.get("artist", "Desconocido")
        album = track.get("album", "Desconocido")
        cover_source = track.get("cover_path", "")
        self.track_title_label.config(text=title)
        self.track_artist_label.config(text=f"{artist}  |  {album}")
        self._set_now_card_track(title, artist, cover_source)
        self.top_preview_title.config(text=title)
        self.top_preview_artist.config(text=artist)
        if cover_source:
            try:
                img_big = self._load_image(cover_source, self.main_cover_size)
                self.cover_label.config(image=img_big)
                self.cover_label.image = img_big
                img_small = self._load_image(cover_source, (52, 52))
                self.top_preview_image.config(image=img_small)
                self.top_preview_image.image = img_small
            except Exception:
                self._set_cover_placeholder("Sin portada")
        else:
            self._set_cover_placeholder("Sin portada")

    def _play_selected_track(self):
        track = self._get_selected_track_from_tree()
        if not track:
            messagebox.showinfo("Reproduccion", "Selecciona una cancion primero.")
            return
        self._play_track(track)

    def _play_track(self, track):
        path = track.get("path", "")
        if not path or not Path(path).exists():
            messagebox.showerror("Archivo", "No se encontro el archivo de audio.")
            return
        if not self.audio_ok:
            messagebox.showerror("Audio", "No se pudo inicializar el audio.")
            return

        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        pygame.mixer.music.set_volume(self.volume_scale.get() / 100)

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
        self.play_btn.config(text="Pausa")

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
            self._set_status("Reproduccion reanudada.", COLORS["ok"])
            self.play_btn.config(text="Pausa")
        else:
            self._paused_elapsed += time.time() - self._play_started_at
            pygame.mixer.music.pause()
            self.is_paused = True
            self._set_status("Reproduccion pausada.")
            self.play_btn.config(text="Play")

    def _stop_song(self):
        if self.audio_ok:
            pygame.mixer.music.stop()
        self.is_playing = False
        self.is_paused = False
        self._paused_elapsed = 0.0
        self.progress.set(0)
        self.current_time_label.config(text="00:00")
        self.play_btn.config(text="Play")
        self._set_status("Reproduccion detenida.")

    def _toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.shuffle_btn.config(bg=COLORS["accent"] if self.shuffle else COLORS["chip"])
        self._set_status("Shuffle activado." if self.shuffle else "Shuffle desactivado.")

    def _toggle_loop(self):
        self.loop = not self.loop
        self.loop_btn.config(bg=COLORS["accent"] if self.loop else COLORS["chip"])
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
        self.tree.selection_set(track["id"])
        self.tree.focus(track["id"])
        self._play_track(track)

    def _prev_song(self):
        if not self.view_tracks:
            return
        idx = len(self.view_tracks) - 1 if self.current_index <= 0 else self.current_index - 1
        self.current_index = idx
        track = self.view_tracks[idx]
        self.tree.selection_set(track["id"])
        self.tree.focus(track["id"])
        self._play_track(track)

    def _set_volume(self, value):
        if self.audio_ok:
            pygame.mixer.music.set_volume(float(value) / 100)

    def _seek_audio(self, percent):
        if not self.is_playing or not self.current_audio_path or self.current_duration <= 0:
            return
        target = (percent / 100) * self.current_duration
        pygame.mixer.music.load(self.current_audio_path)
        pygame.mixer.music.play(start=target)
        pygame.mixer.music.set_volume(self.volume_scale.get() / 100)
        self._paused_elapsed = target
        self._play_started_at = time.time()
        self.is_paused = False
        self.play_btn.config(text="Pausa")

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

    def _search_spotify(self):
        query = self.spotify_entry.get().strip()
        if self.active_left_panel == "folder":
            self._apply_filter_folder_query(query)
            return
        if not query:
            messagebox.showwarning("Spotify", "Escribe una busqueda para Spotify.")
            return
        self.last_spotify_query = query
        self.spotify_btn.config(state="disabled")
        self._set_status("Buscando en Spotify...", COLORS["accent_soft"])
        threading.Thread(target=self._spotify_search_worker, args=(query,), daemon=True).start()

    def _apply_filter_folder_query(self, query):
        if self.active_left_panel != "folder":
            return
        selected = self.folder_listbox.curselection() if hasattr(self, "folder_listbox") else ()
        if not selected:
            self.view_tracks = []
            self._render_library_table()
            return
        folder = self.folder_listbox.get(selected[0])
        tracks = [t for t in self.library.values() if str(Path(t.get("path", "")).parent) == folder]
        q = query.strip().lower()
        if q:
            tracks = [t for t in tracks if q in t.get("title", "").lower() or q in t.get("artist", "").lower()]
        tracks.sort(key=lambda t: t.get("title", "").lower())
        self.view_tracks = tracks
        self._render_library_table()

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
                "",
                "end",
                iid=iid,
                text=track.get("title", "Desconocido"),
                image=image,
                values=(
                    track.get("artist", "Desconocido"),
                    track.get("album", "Desconocido"),
                ),
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
            self._set_status("Descargando para agregar a playlist...", COLORS["accent_soft"])
            threading.Thread(target=self._spotify_download_worker, args=(track, False, target_playlist), daemon=True).start()
        else:
            self._set_status("Descargando y reproduciendo seleccion de Spotify...", COLORS["accent_soft"])
            threading.Thread(target=self._spotify_download_worker, args=(track, True, ""), daemon=True).start()

    def _preview_selected_spotify(self):
        track = self._get_selected_spotify_track()
        if not track:
            return
        title = track.get("title", "Sin titulo")
        artist = track.get("artist", "Desconocido")
        self.track_title_label.config(text=title)
        self.track_artist_label.config(text=f"{artist}  |  {track.get('album', 'Desconocido')}")
        cover_source = track.get("cover_url", "")
        self._set_now_card_track(title, artist, cover_source)
        self.top_preview_title.config(text=title)
        self.top_preview_artist.config(text=artist)
        if cover_source:
            try:
                img_big = self._load_image(cover_source, self.main_cover_size)
                self.cover_label.config(image=img_big)
                self.cover_label.image = img_big
                img_small = self._load_image(cover_source, (52, 52))
                self.top_preview_image.config(image=img_small)
                self.top_preview_image.image = img_small
            except Exception:
                self._set_cover_placeholder("Spotify")

    def _download_selected_spotify(self):
        track = self._get_selected_spotify_track()
        if not track:
            messagebox.showinfo("Spotify", "Selecciona una cancion de Spotify.")
            return
        self._set_status("Descargando desde YouTube...", COLORS["accent_soft"])
        target_playlist = self._get_selected_playlist_name() if self.active_left_panel == "playlist" else ""
        threading.Thread(target=self._spotify_download_worker, args=(track, False, target_playlist), daemon=True).start()

    def _spotify_download_worker(self, track, autoplay=False, target_playlist=""):
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
                    "source": "spotify_youtube",
                },
            )
            self.library[meta["id"]] = meta
            if target_playlist and target_playlist in self.playlists and meta["id"] not in self.playlists[target_playlist]:
                self.playlists[target_playlist].append(meta["id"])
            self._save_data()
            self.ui_queue.put(("spotify_download_ok", meta, autoplay, target_playlist))
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
                    self._set_status(f"Importacion lista: {imported} canciones nuevas.", COLORS["ok"])
                elif kind == "spotify_ok":
                    self.spotify_results = item[1]
                    query = item[2]
                    self.spotify_btn.config(state="normal")
                    self._render_spotify_results()
                    if self.spotify_results:
                        self._set_status(f"Spotify: {len(self.spotify_results)} resultados para '{query}'.", COLORS["ok"])
                    else:
                        self._set_status(f"No se encontraron resultados para '{query}'.", COLORS["warn"])
                elif kind == "spotify_err":
                    self.spotify_btn.config(state="normal")
                    msg = f"Error buscando en Spotify: {item[1]}"
                    self._set_status(msg, COLORS["warn"])
                    messagebox.showerror("Error", msg)
                elif kind == "spotify_download_ok":
                    meta = item[1]
                    autoplay = item[2] if len(item) > 2 else False
                    playlist_name = item[3] if len(item) > 3 else ""
                    self._refresh_all_views()
                    if playlist_name:
                        self._set_status(f"Agregada a '{playlist_name}': {meta.get('title', '')}", COLORS["ok"])
                    else:
                        self._set_status(f"Descargada: {meta.get('title', '')}", COLORS["ok"])
                    if autoplay:
                        self._play_track(meta)
                    self.spotify_auto_play_in_progress = False
                elif kind == "spotify_download_err":
                    msg = f"No se pudo descargar desde YouTube: {item[1]}"
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
