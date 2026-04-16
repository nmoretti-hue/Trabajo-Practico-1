import os
import sys
import random
import tkinter as tk
from tkinter import ttk, messagebox
import pygame
import time
from mutagen.mp3 import MP3
from spotifiApi import SpotifyBuscar

# ========== CONFIGURACIÓN DE CARPETA ==========
CARPETA = "musica"

# ========== CONFIGURACIÓN DE COLORES ==========
COLORES = {
    "fondo_principal": "#1a1a2e",
    "fondo_encabezado": "#16213e",
    "fondo_lista": "#0f3460",
    "fondo_botones": "#e94560",
    "fondo_boton_hover": "#c73652",
    "texto_principal": "#eaeaea",
    "texto_secundario": "#a0a0b0",
    "texto_volumen": "#eaeaea",
    "borde_lista": "#e94560",
    "acento": "#e94560",
    "acento_claro": "#ff6b8a",
    "progress_bg": "#2a2a4a",
    "progress_fill": "#e94560",
    "volumen_bg": "#2a2a4a",
    "volumen_fill": "#00d4aa",
    "seleccion": "#e94560",
}


def init_audio():
    if sys.platform.startswith("win"):
        os.environ.setdefault("SDL_AUDIODRIVER", "directsound")
    for driver in ["directsound", "dsound", "winmm", "alsa", "pulseaudio", "oss"]:
        if sys.platform.startswith("win"):
            os.environ["SDL_AUDIODRIVER"] = driver
        try:
            pygame.mixer.pre_init(44100, -16, 2, 2048)
            pygame.init()
            pygame.mixer.init()
            return True
        except:
            pygame.quit()
    return False


class BarraProgreso(tk.Canvas):
    """Barra de progreso personalizada y estética"""

    def __init__(self, parent, **kwargs):
        self.height = kwargs.pop("height", 6)
        self.color_bg = kwargs.pop("color_bg", "#2a2a4a")
        self.color_fill = kwargs.pop("color_fill", "#e94560")
        self.color_thumb = kwargs.pop("color_thumb", "#ffffff")
        self.on_seek = kwargs.pop("on_seek", None)

        super().__init__(parent, height=self.height + 20,
                         bg=COLORES["fondo_principal"],
                         highlightthickness=0, **kwargs)

        self._valor = 0
        self._maximo = 100
        self._arrastrando = False

        self.bind("<Button-1>", self._click)
        self.bind("<B1-Motion>", self._arrastrar)
        self.bind("<ButtonRelease-1>", self._soltar)
        self.bind("<Configure>", self._redibujar)
        self.bind("<Enter>", self._hover_in)
        self.bind("<Leave>", self._hover_out)

        self._hover = False
        self._redibujar()

    def _hover_in(self, e):
        self._hover = True
        self._redibujar()

    def _hover_out(self, e):
        self._hover = False
        self._redibujar()

    def _redibujar(self, e=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 2:
            return

        cy = h // 2
        radio = self.height // 2
        thumb_r = 7 if self._hover or self._arrastrando else 5

        self._dibujar_rect_redondeado(4, cy - radio, w - 4, cy + radio,
                                      radio, self.color_bg)

        progreso = self._valor / max(self._maximo, 1)
        fill_x = 4 + (w - 8) * progreso

        if fill_x > 4 + radio:
            self._dibujar_rect_redondeado(4, cy - radio, fill_x, cy + radio,
                                          radio, self.color_fill)

        tx = 4 + (w - 8) * progreso
        self.create_oval(tx - thumb_r - 1, cy - thumb_r - 1,
                         tx + thumb_r + 1, cy + thumb_r + 1,
                         fill="#333333", outline="")
        self.create_oval(tx - thumb_r, cy - thumb_r,
                         tx + thumb_r, cy + thumb_r,
                         fill=self.color_thumb, outline=self.color_fill,
                         width=2)
        self.create_oval(tx - thumb_r + 2, cy - thumb_r + 2,
                         tx - 1, cy + 1,
                         fill="#e0e0e0", outline="")

    def _dibujar_rect_redondeado(self, x1, y1, x2, y2, r, color):
        if x2 - x1 < 2 * r:
            r = (x2 - x1) // 2
        if r < 1:
            return
        self.create_arc(x1, y1, x1 + 2 * r, y2,
                        start=90, extent=180, fill=color, outline="")
        self.create_arc(x2 - 2 * r, y1, x2, y2,
                        start=270, extent=180, fill=color, outline="")
        self.create_rectangle(x1 + r, y1, x2 - r, y2,
                              fill=color, outline="")

    def _calcular_valor(self, x):
        w = self.winfo_width()
        ratio = max(0, min(1, (x - 4) / max(w - 8, 1)))
        return ratio * self._maximo

    def _click(self, e):
        self._arrastrando = True
        self._valor = self._calcular_valor(e.x)
        self._redibujar()

    def _arrastrar(self, e):
        if self._arrastrando:
            self._valor = self._calcular_valor(e.x)
            self._redibujar()

    def _soltar(self, e):
        self._arrastrando = False
        self._valor = self._calcular_valor(e.x)
        self._redibujar()
        if self.on_seek:
            self.on_seek(self._valor)

    def set(self, valor):
        if not self._arrastrando:
            self._valor = max(0, min(self._maximo, valor))
            self._redibujar()

    def get(self):
        return self._valor

    def configure_max(self, maximo):
        self._maximo = maximo


class BarraVolumen(tk.Canvas):
    """Barra de volumen vertical personalizada"""

    def __init__(self, parent, **kwargs):
        self.width_bar = kwargs.pop("width_bar", 6)
        self.color_bg = kwargs.pop("color_bg", "#2a2a4a")
        self.color_fill = kwargs.pop("color_fill", "#00d4aa")
        self.color_thumb = kwargs.pop("color_thumb", "#ffffff")
        self.on_change = kwargs.pop("on_change", None)

        super().__init__(parent, width=40, height=120,
                         bg=COLORES["fondo_encabezado"],
                         highlightthickness=0, **kwargs)

        self._valor = 0.7
        self._arrastrando = False
        self._hover = False

        self.bind("<Button-1>", self._click)
        self.bind("<B1-Motion>", self._arrastrar)
        self.bind("<ButtonRelease-1>", self._soltar)
        self.bind("<Configure>", self._redibujar)
        self.bind("<Enter>", self._hover_in)
        self.bind("<Leave>", self._hover_out)
        self.bind("<MouseWheel>", self._scroll)

        self._redibujar()

    def _hover_in(self, e):
        self._hover = True
        self._redibujar()

    def _hover_out(self, e):
        self._hover = False
        self._redibujar()

    def _scroll(self, e):
        delta = 0.05 if e.delta > 0 else -0.05
        self._valor = max(0, min(1, self._valor + delta))
        self._redibujar()
        if self.on_change:
            self.on_change(self._valor)

    def _redibujar(self, e=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 2 or h < 2:
            return

        cx = w // 2
        radio = self.width_bar // 2
        thumb_r = 8 if self._hover or self._arrastrando else 6
        padding = 10

        self._dibujar_rect_redondeado(cx - radio, padding,
                                      cx + radio, h - padding,
                                      radio, self.color_bg)

        fill_h = (h - 2 * padding) * self._valor
        fill_y = h - padding - fill_h

        if fill_h > radio * 2:
            self._dibujar_rect_redondeado(cx - radio, fill_y,
                                          cx + radio, h - padding,
                                          radio, self.color_fill)

        ty = h - padding - (h - 2 * padding) * self._valor
        ty = max(padding + thumb_r, min(h - padding - thumb_r, ty))

        self.create_oval(cx - thumb_r, ty - thumb_r,
                         cx + thumb_r, ty + thumb_r,
                         fill="#000000", outline="")
        self.create_oval(cx - thumb_r + 1, ty - thumb_r + 1,
                         cx + thumb_r - 1, ty + thumb_r - 1,
                         fill=self.color_thumb,
                         outline=self.color_fill, width=2)

    def _dibujar_rect_redondeado(self, x1, y1, x2, y2, r, color):
        if y2 - y1 < 2 * r:
            r = max(1, (y2 - y1) // 2)
        if r < 1:
            return
        self.create_arc(x1, y1, x2, y1 + 2 * r,
                        start=0, extent=180, fill=color, outline="")
        self.create_arc(x1, y2 - 2 * r, x2, y2,
                        start=180, extent=180, fill=color, outline="")
        self.create_rectangle(x1, y1 + r, x2, y2 - r,
                              fill=color, outline="")

    def _calcular_valor(self, y):
        h = self.winfo_height()
        padding = 10
        ratio = 1 - (y - padding) / max(h - 2 * padding, 1)
        return max(0, min(1, ratio))

    def _click(self, e):
        self._arrastrando = True
        self._valor = self._calcular_valor(e.y)
        self._redibujar()
        if self.on_change:
            self.on_change(self._valor)

    def _arrastrar(self, e):
        if self._arrastrando:
            self._valor = self._calcular_valor(e.y)
            self._redibujar()
            if self.on_change:
                self.on_change(self._valor)

    def _soltar(self, e):
        self._arrastrando = False

    def set(self, valor):
        self._valor = max(0, min(1, valor))
        self._redibujar()

    def get(self):
        return self._valor


class Reproductor:
    def __init__(self, root):
        self.root = root
        self.root.title("Reproductor de Música")
        self.root.geometry("960x680")
        self.root.resizable(True, True)
        self.root.minsize(800, 550)  # Tamaño mínimo para evitar perder elementos
        self.root.configure(bg=COLORES["fondo_principal"])

        self.audio_ok = init_audio()
        self.songs = []
        self.index = 0
        self.loop = False
        self.shuffle = False
        self.playing = False
        self.paused = False
        self.current_song = None

        self.duration = 0

        # ══════════════════════════════════════════════
        #  NUEVO SISTEMA DE TIEMPO: usar time.time()
        #  en vez de depender de get_pos() de pygame
        # ══════════════════════════════════════════════
        self._play_start_time = 0.0    # time.time() cuando se hizo play/unpause
        self._accumulated_time = 0.0   # segundos acumulados antes de la última pausa

        # Inicializar buscador de Spotify con credenciales
        CLIENT_ID = "b5ed64e785c2431b8e80928e46961eb2"
        CLIENT_SECRET = "79e150930df44de0b41f5c710d7330fb"
        self.spotify = SpotifyBuscar(CLIENT_ID, CLIENT_SECRET)
        self.resultados_spotify = []

        self._crear_interfaz()

    # ─────────────────────────────────────────────
    #  CONSTRUCCIÓN DE LA INTERFAZ
    # ─────────────────────────────────────────────

    def _crear_interfaz(self):
        self._crear_layout()
        self.load_songs()

        if self.audio_ok:
            pygame.mixer.music.set_volume(0.7)
        else:
            messagebox.showwarning("Audio", "No se pudo inicializar el audio.")

        self.root.after(500, self.check_end)
        self.update_progress()

    def _crear_layout(self):
        main = tk.Frame(self.root, bg=COLORES["fondo_principal"])
        main.pack(fill="both", expand=True, padx=15, pady=15)

        # Columna izquierda: Playlist
        left = tk.Frame(main, bg=COLORES["fondo_encabezado"], width=260)
        left.pack(side="left", fill="y", padx=(0, 15))
        left.pack_propagate(False)
        self._crear_playlist(left)

        # Columna derecha
        right = tk.Frame(main, bg=COLORES["fondo_principal"])
        right.pack(side="left", fill="both", expand=True)

        self._crear_centro_cancion(right)
        tk.Frame(right, bg=COLORES["acento"], height=1).pack(fill="x", pady=(0, 12))
        self._crear_barra_progreso(right)
        tk.Frame(right, bg="#2a2a4a", height=1).pack(fill="x", pady=(12, 0))
        self._crear_controles(right)

    def _crear_playlist(self, parent):
        header = tk.Frame(parent, bg=COLORES["acento"], height=45)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text="♫  PLAYLIST",
                 font=("Arial", 12, "bold"),
                 bg=COLORES["acento"],
                 fg="white").pack(expand=True)

        # Barra de búsqueda
        search_frame = tk.Frame(parent, bg=COLORES["fondo_encabezado"])
        search_frame.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(search_frame, text="🔍 Buscar:",
                 font=("Arial", 9),
                 bg=COLORES["fondo_encabezado"],
                 fg=COLORES["texto_principal"]).pack(side="left", padx=(0, 5))

        self.search_entry = tk.Entry(search_frame,
                                     font=("Arial", 9),
                                     bg=COLORES["fondo_lista"],
                                     fg=COLORES["texto_principal"],
                                     insertbackground=COLORES["acento"],
                                     relief="flat",
                                     borderwidth=1)
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<Return>", lambda e: self._buscar_spotify())

        self.lbl_contador = tk.Label(
            parent, text="0 canciones",
            font=("Arial", 9),
            bg=COLORES["fondo_encabezado"],
            fg=COLORES["texto_secundario"],
        )
        self.lbl_contador.pack(pady=(0, 4))

        frame_lb = tk.Frame(parent, bg=COLORES["fondo_encabezado"])
        frame_lb.pack(fill="both", expand=True, padx=8, pady=(0, 10))

        scroll = tk.Scrollbar(frame_lb)
        scroll.pack(side="right", fill="y")

        self.listbox = tk.Listbox(
            frame_lb,
            font=("Arial", 10),
            bg=COLORES["fondo_lista"],
            fg=COLORES["texto_principal"],
            selectbackground=COLORES["seleccion"],
            selectforeground="white",
            activestyle="none",
            relief="flat",
            borderwidth=0,
            yscrollcommand=scroll.set,
            cursor="hand2",
        )
        self.listbox.pack(fill="both", expand=True)
        scroll.config(command=self.listbox.yview)
        self.listbox.bind("<Double-Button-1>", lambda e: self.play_song())

    def _crear_centro_cancion(self, parent):
        self.centro = tk.Frame(parent, bg=COLORES["fondo_principal"])
        self.centro.pack(fill="both", expand=True)

        self.lbl_icono = tk.Label(
            self.centro, text="♪",
            font=("Arial", 60),
            bg=COLORES["fondo_principal"],
            fg=COLORES["acento"],
        )
        self.lbl_icono.pack(expand=True, pady=(20, 5))

        self.title_label = tk.Label(
            self.centro,
            text="Sin canción",
            font=("Arial", 22, "bold"),
            bg=COLORES["fondo_principal"],
            fg=COLORES["texto_principal"],
            wraplength=500,
            justify="center",
        )
        self.title_label.pack(expand=True, pady=(0, 5))

        self.status_label = tk.Label(
            self.centro,
            text="Selecciona una canción",
            font=("Arial", 11, "italic"),
            bg=COLORES["fondo_principal"],
            fg=COLORES["texto_secundario"],
        )
        self.status_label.pack(expand=True, pady=(0, 20))

    def _crear_barra_progreso(self, parent):
        frame = tk.Frame(parent, bg=COLORES["fondo_principal"])
        frame.pack(fill="x", padx=20, pady=(0, 5))

        time_row = tk.Frame(frame, bg=COLORES["fondo_principal"])
        time_row.pack(fill="x", pady=(0, 4))

        self.lbl_tiempo_actual = tk.Label(
            time_row, text="00:00",
            font=("Consolas", 10, "bold"),
            bg=COLORES["fondo_principal"],
            fg=COLORES["acento"],
        )
        self.lbl_tiempo_actual.pack(side="left")

        self.lbl_tiempo_total = tk.Label(
            time_row, text="00:00",
            font=("Consolas", 10),
            bg=COLORES["fondo_principal"],
            fg=COLORES["texto_secundario"],
        )
        self.lbl_tiempo_total.pack(side="right")

        self.progress = BarraProgreso(
            frame,
            color_bg=COLORES["progress_bg"],
            color_fill=COLORES["progress_fill"],
            color_thumb="#ffffff",
            on_seek=self._seek,
            height=8,
        )
        self.progress.pack(fill="x", pady=(0, 2))

    def _seek(self, valor_porcentaje):
        """Salta a la posición indicada por la barra (0-100)."""
        if not self.audio_ok or self.duration <= 0:
            return

        segundos_destino = (valor_porcentaje / 100.0) * self.duration

        try:
            # ═══ CAMBIO CLAVE: NO usar loops=-1 en play() ═══
            # Reproducir sin loop, el loop lo manejamos manualmente en check_end
            pygame.mixer.music.play(start=segundos_destino)
            pygame.mixer.music.set_volume(self.volume.get())

            # ═══ Resetear el sistema de tiempo ═══
            self._accumulated_time = segundos_destino
            self._play_start_time = time.time()
            self.playing = True
            self.paused = False

        except Exception as e:
            print("Error en seek:", e)

    def _crear_controles(self, parent):
        frame = tk.Frame(parent, bg=COLORES["fondo_principal"])
        frame.pack(fill="x", pady=15, padx=10)

        left = tk.Frame(frame, bg=COLORES["fondo_principal"])
        left.pack(side="left", fill="y")

        self.btn_shuffle = self._boton_toggle(left, "🔀", "Shuffle",
                                              self.toggle_shuffle)
        self.btn_shuffle.pack(pady=4)
        self.btn_loop = self._boton_toggle(left, "🔁", "Loop",
                                           self.toggle_loop)
        self.btn_loop.pack(pady=4)

        center = tk.Frame(frame, bg=COLORES["fondo_principal"])
        center.pack(side="left", expand=True)

        btn_cfg = dict(
            bg=COLORES["fondo_principal"],
            activebackground=COLORES["fondo_principal"],
            relief="flat", borderwidth=0,
            highlightthickness=0,
            cursor="hand2",
        )

        try:
            self.prev_image = tk.PhotoImage(file="imagenes/3.png")
            self.prev_btn = tk.Button(center, image=self.prev_image,
                                      command=self.prev_song, **btn_cfg)
        except Exception:
            self.prev_btn = tk.Button(center, text="⏮",
                                      font=("Arial", 18),
                                      command=self.prev_song,
                                      fg="white", **btn_cfg)
        self.prev_btn.pack(side="left", padx=20)

        try:
            self.play_image = tk.PhotoImage(file="imagenes/1.png")
            self.pause_image = tk.PhotoImage(file="imagenes/2.png")
            self.toggle_btn = tk.Button(center, image=self.play_image,
                                        command=self.toggle_play, **btn_cfg)
        except Exception:
            self.play_image = None
            self.pause_image = None
            self.toggle_btn = tk.Button(center, text="▶",
                                        font=("Arial", 28, "bold"),
                                        command=self.toggle_play,
                                        fg=COLORES["acento"], **btn_cfg)
        self.toggle_btn.pack(side="left", padx=20)

        try:
            self.next_image = tk.PhotoImage(file="imagenes/4.png")
            self.next_btn = tk.Button(center, image=self.next_image,
                                      command=self.next_song, **btn_cfg)
        except Exception:
            self.next_btn = tk.Button(center, text="⏭",
                                      font=("Arial", 18),
                                      command=self.next_song,
                                      fg="white", **btn_cfg)
        self.next_btn.pack(side="left", padx=20)

        right = tk.Frame(frame, bg=COLORES["fondo_encabezado"],
                         padx=10, pady=10)
        right.pack(side="right", fill="y")

        tk.Label(right, text="🔊",
                 font=("Arial", 14),
                 bg=COLORES["fondo_encabezado"],
                 fg=COLORES["volumen_fill"]).pack()

        self.volume = BarraVolumen(
            right,
            color_bg=COLORES["volumen_bg"],
            color_fill=COLORES["volumen_fill"],
            on_change=self.set_volume,
        )
        self.volume.pack(pady=4)

        self.lbl_vol = tk.Label(
            right, text="70%",
            font=("Arial", 9),
            bg=COLORES["fondo_encabezado"],
            fg=COLORES["texto_secundario"],
        )
        self.lbl_vol.pack()

    def _boton_toggle(self, parent, icono, texto, comando):
        btn = tk.Button(
            parent,
            text=f"{icono} {texto}",
            font=("Arial", 9, "bold"),
            command=lambda b=None: self._on_toggle(btn, comando),
            bg=COLORES["fondo_encabezado"],
            fg=COLORES["texto_secundario"],
            activebackground=COLORES["acento"],
            activeforeground="white",
            relief="flat",
            padx=10, pady=4,
            borderwidth=0,
            highlightthickness=0,
            cursor="hand2",
            width=10,
        )
        return btn

    def _on_toggle(self, btn, comando):
        comando()
        activo = self.shuffle if comando == self.toggle_shuffle else self.loop
        if activo:
            btn.config(bg=COLORES["acento"], fg="white")
        else:
            btn.config(bg=COLORES["fondo_encabezado"],
                       fg=COLORES["texto_secundario"])

    # ─────────────────────────────────────────────
    #  LÓGICA DE REPRODUCCIÓN
    # ─────────────────────────────────────────────

    def load_songs(self):
        """Inicializa la playlist como vacía (ahora usamos Spotify)"""
        self.songs = []
        self.resultados_spotify = []
        self.listbox.delete(0, "end")
        
        self.lbl_contador.config(text="0 canciones")
        self.status_label.config(text="Busca canciones en Spotify")

    def _buscar_spotify(self):
        """Busca canciones en Spotify usando el texto del Entry"""
        query = self.search_entry.get().strip()
        
        if not query:
            messagebox.showwarning("Búsqueda vacía", "Ingresa un término de búsqueda")
            return
        
        try:
            self.status_label.config(text="🔍 Buscando en Spotify...")
            self.root.update()
            
            # Buscar usando la API de Spotify (sin token - resultados limitados)
            # Para usar la API completa, necesitarías autenticarte
            resultados = self._buscar_spotify_alternativo(query)
            
            if resultados:
                self.resultados_spotify = resultados
                self._mostrar_resultados_spotify(resultados)
                self.status_label.config(text=f"✓ {len(resultados)} canciones encontradas")
            else:
                messagebox.showinfo("Sin resultados", 
                    "No se encontraron canciones. Nota: Necesitas credenciales de Spotify para búsqueda completa.\n\n"
                    "Para usar la búsqueda completa:\n"
                    "1. Ve a https://developer.spotify.com\n"
                    "2. Crea una aplicación\n"
                    "3. Obtén tu Client ID y Client Secret")
                self.status_label.config(text="Sin resultados")
                
        except Exception as e:
            messagebox.showerror("Error", f"Error en búsqueda: {str(e)}")
            self.status_label.config(text="Error en búsqueda")
    
    def _buscar_spotify_alternativo(self, query):
        """
        Búsqueda alternativa de Spotify sin requerir token.
        Retorna resultados formateados.
        Para usar la API real, necesitarías credenciales.
        """
        try:
            import requests
            
            # Intento de búsqueda usando requests de forma pública
            # Nota: Esto tiene limitaciones. Para producción, usar OAuth2
            
            # Simulamos resultados o usamos una alternativa
            # En este caso, retornamos una lista vacía ya que sin token
            # no podemos acceder a la API pública de Spotify
            
            # Para que funcione, necesitarías:
            # 1. Registrarte en https://developer.spotify.com
            # 2. Crear una aplicación
            # 3. Usar tu Client ID y Secret
            
            return []
            
        except Exception as e:
            print(f"Error en búsqueda alternativa: {e}")
            return []
    
    def _mostrar_resultados_spotify(self, resultados):
        """Muestra los resultados de Spotify en la listbox"""
        self.listbox.delete(0, "end")
        
        for i, cancion in enumerate(resultados):
            nombre = cancion.get('nombre', 'Desconocido')
            artista = cancion.get('artista', 'Desconocido')
            
            # Mostrar formato: "01. Nombre - Artista"
            texto = f"  {i + 1:02d}.  {nombre} - {artista}"
            self.listbox.insert("end", texto)
        
        total = len(resultados)
        self.lbl_contador.config(
            text=f"{total} canción{'es' if total != 1 else ''}")
        
        self.songs = resultados

    def play_song(self, use_selection=True):
        if not self.songs:
            messagebox.showinfo("Playlist vacía", "Busca canciones en Spotify primero")
            return

        if use_selection:
            sel = self.listbox.curselection()
            if sel:
                self.index = sel[0]

        cancion = self.songs[self.index]

        try:
            # Si es un resultado de Spotify (diccionario)
            if isinstance(cancion, dict):
                nombre = cancion.get('nombre', 'Desconocido')
                artista = cancion.get('artista', 'Desconocido')
                preview_url = cancion.get('preview', '')
                
                # Si hay URL de previa disponible
                if preview_url and preview_url.startswith('http'):
                    # Intentar reproducir la previa de 30 segundos
                    try:
                        import urllib.request
                        urllib.request.urlopen(preview_url, timeout=5)
                        
                        pygame.mixer.music.load(preview_url)
                        pygame.mixer.music.play()
                        pygame.mixer.music.set_volume(self.volume.get())
                        
                        self.playing = True
                        self.paused = False
                        self.current_song = cancion
                        self.duration = 30  # Las previas de Spotify son de ~30 segundos
                        
                    except Exception as e:
                        # Si no se puede reproducir la previa, abrir en Spotify
                        import webbrowser
                        url_spotify = cancion.get('url', '')
                        if url_spotify:
                            webbrowser.open(url_spotify)
                            messagebox.showinfo("Abriendo en Spotify", 
                                f"No se puede reproducir localmente.\n\n"
                                f"Abriendo en Spotify:\n{nombre} - {artista}")
                        else:
                            messagebox.showwarning("Error", 
                                f"No se puede reproducir:\n{nombre}\n\n"
                                f"Necesitas credenciales completas de Spotify")
                        return
                else:
                    # Sin preview disponible
                    messagebox.showinfo("Sin vista previa", 
                        f"No hay vista previa disponible para:\n{nombre} - {artista}\n\n"
                        f"Abre Spotify en tu navegador para escuchar la canción completa")
                    return
                
                # Inicializar sistema de tiempo
                self._accumulated_time = 0.0
                self._play_start_time = time.time()
                
                # Actualizar UI
                self.title_label.config(text=f"{nombre} - {artista}")
                self.lbl_tiempo_total.config(text=self.format_time(self.duration))
                self.lbl_tiempo_actual.config(text="00:00")
                self.progress.set(0)
                self.status_label.config(text="▶  Reproduciendo previa de Spotify")
                self.lbl_icono.config(fg=COLORES["acento"])
                
            else:
                # Es un archivo local (por compatibilidad)
                if not self.audio_ok:
                    self.audio_ok = init_audio()
                    if not self.audio_ok:
                        return
                
                pygame.mixer.music.load(cancion)
                pygame.mixer.music.play()
                pygame.mixer.music.set_volume(self.volume.get())
                
                self.playing = True
                self.paused = False
                self.current_song = cancion
                
                audio = MP3(cancion)
                self.duration = audio.info.length
                
                self._accumulated_time = 0.0
                self._play_start_time = time.time()
                
                nombre_limpio = os.path.splitext(os.path.basename(cancion))[0]
                self.title_label.config(text=nombre_limpio)
                self.lbl_tiempo_total.config(text=self.format_time(self.duration))
                self.lbl_tiempo_actual.config(text="00:00")
                self.progress.set(0)
                self.status_label.config(text="▶  Reproduciendo")
                self.lbl_icono.config(fg=COLORES["acento"])
            
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(self.index)
            self.listbox.see(self.index)
            
            self.update_button_image()

        except Exception as e:
            messagebox.showerror("Error", f"Error al reproducir: {str(e)}")
            print("Error al reproducir:", e)

    def _get_current_seconds(self):
        """
        ═══ NUEVO MÉTODO: calcula el tiempo usando time.time() ═══
        
        Esto es INDEPENDIENTE de pygame.mixer.music.get_pos()
        que tiene bugs con pause/unpause y loops.
        """
        if not self.playing:
            return self._accumulated_time

        if self.paused:
            return self._accumulated_time

        # Tiempo = lo acumulado antes + lo que lleva sonando ahora
        elapsed = time.time() - self._play_start_time
        current = self._accumulated_time + elapsed

        return min(current, self.duration)

    def update_button_image(self):
        if not hasattr(self, "toggle_btn"):
            return
        if self.play_image and self.pause_image:
            img = self.pause_image if (
                self.playing and not self.paused) else self.play_image
            self.toggle_btn.config(image=img)
        else:
            if self.playing and not self.paused:
                self.toggle_btn.config(text="⏸", fg=COLORES["acento"])
            else:
                self.toggle_btn.config(text="▶", fg=COLORES["acento"])

    def toggle_play(self):
        if not self.songs:
            return
        if self.playing:
            self.toggle_pause()
        else:
            self.play_song()

    def toggle_pause(self):
        if not self.audio_ok or not self.playing:
            return

        if self.paused:
            # ═══ REANUDAR ═══
            pygame.mixer.music.unpause()
            # Reiniciar el cronómetro desde ahora
            self._play_start_time = time.time()
            # _accumulated_time ya tiene el tiempo correcto (se guardó al pausar)
            self.paused = False
            self.status_label.config(text="▶  Reproduciendo")
        else:
            # ═══ PAUSAR ═══
            # Guardar cuánto tiempo llevamos en total
            elapsed = time.time() - self._play_start_time
            self._accumulated_time += elapsed
            pygame.mixer.music.pause()
            self.paused = True
            self.status_label.config(text="⏸  Pausado")

        self.update_button_image()

    def stop_song(self):
        if not self.audio_ok:
            return
        pygame.mixer.music.stop()
        self.playing = False
        self.paused = False
        self._accumulated_time = 0.0
        self.update_button_image()
        self.progress.set(0)
        self.lbl_tiempo_actual.config(text="00:00")
        self.status_label.config(text="⏹  Detenido")

    def next_song(self):
        if not self.songs:
            return
        if self.shuffle:
            nuevo = random.randrange(len(self.songs))
            while nuevo == self.index and len(self.songs) > 1:
                nuevo = random.randrange(len(self.songs))
            self.index = nuevo
        else:
            self.index = (self.index + 1) % len(self.songs)
        self.play_song(use_selection=False)

    def prev_song(self):
        if not self.songs:
            return
        self.index = (self.index - 1) % len(self.songs)
        self.play_song(use_selection=False)

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle

    def toggle_loop(self):
        self.loop = not self.loop

    def set_volume(self, val):
        if self.audio_ok:
            pygame.mixer.music.set_volume(float(val))
        if hasattr(self, "lbl_vol"):
            self.lbl_vol.config(text=f"{int(float(val) * 100)}%")

    def format_time(self, s):
        s = max(0, int(s))
        return f"{s // 60:02d}:{s % 60:02d}"

    def update_progress(self):
        """Se ejecuta cada 250ms y actualiza barra + etiquetas de tiempo"""
        if self.playing and not self.paused:
            current = self._get_current_seconds()
            current = min(current, self.duration)

            if self.duration > 0:
                porcentaje = (current / self.duration) * 100
                self.progress.set(porcentaje)
                self.lbl_tiempo_actual.config(text=self.format_time(current))

        # ═══ Actualizar más frecuentemente para mejor respuesta ═══
        self.root.after(250, self.update_progress)

    def check_end(self):
        """Detecta cuando la canción terminó y avanza/repite"""
        if (self.audio_ok
                and self.playing
                and not self.paused
                and not pygame.mixer.music.get_busy()):

            # ═══ CAMBIO: manejar loop manualmente ═══
            if self.loop:
                # Repetir la misma canción
                self.play_song(use_selection=False)
            else:
                self.next_song()

        self.root.after(500, self.check_end)


# ─────────────────────────────────────────────
root = tk.Tk()
app = Reproductor(root)
root.mainloop()