
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
from mutagen import File as ArchivoMutagen
from mutagen.mp3 import MP3
from PIL import Image, ImageDraw, ImageTk

from spotifiApi import SpotifyBuscar


# Rutas y carpetas base
# Define dónde vive el programa y crea las carpetas necesarias para guardar
# la música descargada y las portadas de los álbumes en caché.

DIRECTORIO_BASE = Path(__file__).resolve().parent
DIRECTORIO_MUSICA = DIRECTORIO_BASE / "musica"
DIRECTORIO_CACHE_PORTADAS = DIRECTORIO_BASE / "cache" / "portadas"
ARCHIVO_DATOS = DIRECTORIO_BASE / "playlist.json"

DIRECTORIO_MUSICA.mkdir(exist_ok=True)
DIRECTORIO_CACHE_PORTADAS.mkdir(parents=True, exist_ok=True)

EXTENSIONES_AUDIO = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}


# Paleta de colores Dark Luxury Audio 
# Diccionario con todos los colores de la interfaz. Cada clave es un nombre
# semántico (fondo, panel, acento dorado, texto, etc.) para usarlos de forma
# consistente en todos los widgets sin escribir códigos hex sueltos.

COLORES = {
    "fondo":           "#0D0D0F",   # fondo principal
    "panel":           "#14141A",   # panel oscuro
    "panel_alt":       "#1C1C24",   # panel alternativo
    "superficie":      "#22222E",   # superficie elevada
    "linea":           "#2E2E3A",   # bordes sutiles
    "acento":          "#C8974A",   # dorado cálido principal
    "acento_suave":    "#A87840",   # dorado oscuro
    "acento_brillo":   "#E8B86D",   # dorado claro / hover
    "texto":           "#F0EDE8",   # blanco cálido
    "texto2":          "#B8B4AC",   # texto secundario
    "apagado":         "#5A5865",   # texto apagado
    "ok":              "#4CC98A",   # verde esmeralda
    "advertencia":     "#E8875A",   # naranja advertencia
    "chip":            "#282835",   # chip/tag
    "chip_hover":      "#323240",   # chip hover
    "scrollbar":       "#2A2A36",   # track del scrollbar
    "progreso_fondo":  "#1E1E28",   # fondo barra de progreso
}

FUENTE_PRINCIPAL = "Segoe UI"
FUENTE_MONO = "Consolas"


# Función auxiliar: convertir texto a slug
# Limpia un texto para usarlo como nombre de archivo seguro: elimina caracteres
# especiales, convierte a minúsculas y reemplaza espacios con guiones.

def slugificar(texto):
    limpio = re.sub(r"[^a-zA-Z0-9]+", "-", str(texto).strip().lower())
    return limpio.strip("-") or "audio"


# Inicialización del sistema de audio
# Intenta iniciar pygame.mixer con diferentes drivers de audio. En Windows
# prueba directsound, dsound y winmm. Devuelve True si el audio quedó listo.

def inicializar_audio():
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


# Función auxiliar: rectángulo redondeado como imagen
# Crea una imagen PIL con un rectángulo de esquinas redondeadas y la devuelve
# como PhotoImage de Tkinter. Se usa para los botones y las portadas.

def imagen_rect_redondeado(ancho, alto, radio, relleno, borde=None, grosor_borde=1):
    ancho, alto, radio = int(ancho), int(alto), int(radio)
    img = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(img)
    dibujo.rounded_rectangle((0, 0, ancho - 1, alto - 1), radius=radio, fill=relleno)
    if borde:
        dibujo.rounded_rectangle(
            (grosor_borde // 2, grosor_borde // 2,
             ancho - 1 - grosor_borde // 2, alto - 1 - grosor_borde // 2),
            radius=radio, outline=borde, width=grosor_borde
        )
    return ImageTk.PhotoImage(img)


# Widget: Botón con esquinas redondeadas
# Implementa un botón personalizado usando Frame + Canvas. Los botones normales
# de Tkinter no soportan esquinas redondeadas, así que se dibuja manualmente
# la forma y el texto, y se simulan los estados hover y presionado.

class BotonRedondeado(tk.Frame):

    def __init__(self, padre, texto, comando, ancho=110, alto=36,
                 radio=18, color_fondo=None, color_texto=None,
                 color_hover=None, fuente=None, acento=False, icono=None):
        self._color_fondo = color_fondo or (COLORES["acento"] if acento else COLORES["chip"])
        self._color_texto = color_texto or ("white" if acento else COLORES["texto"])
        self._color_hover = color_hover or (COLORES["acento_brillo"] if acento else COLORES["chip_hover"])
        self._texto = texto
        self._icono = icono
        self._comando = comando
        self._fuente = fuente or (FUENTE_PRINCIPAL, 10, "bold")
        self._presionado = False
        self._ancho = int(ancho)
        self._alto = int(alto)
        self._radio = int(radio)

        fondo_padre = COLORES["panel"]
        try:
            fondo_padre = padre.cget("bg")
        except Exception:
            pass

        super().__init__(padre, width=ancho, height=alto,
                         bg=fondo_padre, bd=0, highlightthickness=0)
        self.pack_propagate(False)

        self._canvas = tk.Canvas(
            self, width=ancho, height=alto,
            bg=fondo_padre, highlightthickness=0, bd=0
        )
        self._canvas.place(x=0, y=0, width=ancho, height=alto)

        self._dibujar(self._color_fondo)

        for w in (self, self._canvas):
            w.bind("<Enter>", self._al_entrar)
            w.bind("<Leave>", self._al_salir)
            w.bind("<Button-1>", self._al_presionar)
            w.bind("<ButtonRelease-1>", self._al_soltar)

    def _dibujar(self, color):
        self._canvas.delete("all")
        img = imagen_rect_redondeado(self._ancho, self._alto, self._radio, color)
        self._img_fondo = img
        self._canvas.create_image(0, 0, anchor="nw", image=img)
        mostrar = (self._icono + "  " + self._texto) if self._icono else self._texto
        self._canvas.create_text(
            self._ancho // 2, self._alto // 2,
            text=mostrar, fill=self._color_texto,
            font=self._fuente, anchor="center"
        )

    def _al_entrar(self, _e):
        self._dibujar(self._color_hover)

    def _al_salir(self, _e):
        self._dibujar(self._color_fondo if not self._presionado else self._color_hover)

    def _al_presionar(self, _e):
        self._presionado = True
        self._dibujar(self._color_hover)

    def _al_soltar(self, _e):
        self._presionado = False
        self._dibujar(self._color_hover)
        if self._comando:
            self._comando()

    def config_colores(self, color_fondo=None, color_texto=None):
        if color_fondo:
            self._color_fondo = color_fondo
        if color_texto:
            self._color_texto = color_texto
        self._dibujar(self._color_fondo)

    def config(self, **kwargs):
        if "bg" in kwargs:
            self._color_fondo = kwargs["bg"]
        if "text" in kwargs:
            self._texto = kwargs["text"]
        self._dibujar(self._color_fondo)


# Widget: Barra de progreso
# Barra horizontal personalizada que muestra el avance de la canción. Soporta
# clic y arrastre para saltar a cualquier punto, y cambia de tamaño al hacer
# hover para mejor usabilidad.

class BarraProgreso(tk.Frame):

    def __init__(self, padre, al_buscar=None):
        fondo_padre = COLORES["panel"]
        try:
            fondo_padre = padre.cget("bg")
        except Exception:
            pass

        super().__init__(padre, height=28, bg=fondo_padre,
                         bd=0, highlightthickness=0)

        self.al_buscar = al_buscar
        self.maximo = 100
        self.valor = 0
        self.arrastrando = False
        self._hover = False

        self._canvas = tk.Canvas(
            self, height=28, bg=fondo_padre,
            highlightthickness=0, bd=0
        )
        self._canvas.pack(fill="both", expand=True)

        for w in (self, self._canvas):
            w.bind("<Button-1>", self._clic)
            w.bind("<B1-Motion>", self._arrastrar)
            w.bind("<ButtonRelease-1>", self._soltar)
            w.bind("<Enter>", lambda _e: self._set_hover(True))
            w.bind("<Leave>", lambda _e: self._set_hover(False))

        self._canvas.bind("<Configure>", self.redibujar)

    def _set_hover(self, val):
        self._hover = val
        self.redibujar()

    def redibujar(self, _evento=None):
        self._canvas.delete("all")
        ancho = max(self._canvas.winfo_width(), 20)
        cy = 14
        alto_track = 4 if not self._hover else 6
        radio_thumb = 6 if not self._hover else 8

        x0, x1 = 14, ancho - 14
        y0 = cy - alto_track // 2
        y1 = cy + alto_track // 2

        self._crear_rect_redondeado(x0, y0, x1, y1, alto_track // 2, COLORES["progreso_fondo"])

        ratio = 0 if self.maximo <= 0 else self.valor / self.maximo
        fill_x = x0 + (x1 - x0) * ratio
        if fill_x > x0:
            self._crear_rect_redondeado(x0, y0, fill_x, y1, alto_track // 2, COLORES["acento"])

        self._canvas.create_oval(
            fill_x - radio_thumb, cy - radio_thumb,
            fill_x + radio_thumb, cy + radio_thumb,
            fill=COLORES["acento_brillo"] if self._hover else COLORES["acento"],
            outline=COLORES["panel_alt"], width=2
        )

    def _crear_rect_redondeado(self, x0, y0, x1, y1, r, color):
        r = min(r, max((y1 - y0) // 2, 1), max((x1 - x0) // 2, 1))
        if r <= 0:
            self._canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline=color)
            return
        self._canvas.create_arc(x0, y0, x0 + 2*r, y1, start=90, extent=180, fill=color, outline=color)
        self._canvas.create_arc(x1 - 2*r, y0, x1, y1, start=270, extent=180, fill=color, outline=color)
        self._canvas.create_rectangle(x0 + r, y0, x1 - r, y1, fill=color, outline=color)

    def _valor_desde_x(self, x):
        ancho = max(self._canvas.winfo_width(), 20)
        ratio = min(max((x - 14) / (ancho - 28), 0), 1)
        return ratio * self.maximo

    def _clic(self, evento):
        self.arrastrando = True
        self.valor = self._valor_desde_x(evento.x)
        self.redibujar()

    def _arrastrar(self, evento):
        if self.arrastrando:
            self.valor = self._valor_desde_x(evento.x)
            self.redibujar()

    def _soltar(self, evento):
        self.arrastrando = False
        self.valor = self._valor_desde_x(evento.x)
        self.redibujar()
        if self.al_buscar:
            self.al_buscar(self.valor)

    def set(self, valor):
        if not self.arrastrando:
            self.valor = min(max(valor, 0), self.maximo)
            self.redibujar()


# Widget: Perilla de volumen vertical
# Control de volumen implementado como barra vertical con thumb arrastrable.
# También responde a la rueda del mouse para subir/bajar el volumen con scroll.

class PerillaVolumen(tk.Frame):

    def __init__(self, padre, comando=None, inicial=70):
        self._valor = inicial
        self._comando = comando
        self._arrastrando = False

        fondo_padre = COLORES["panel"]
        try:
            fondo_padre = padre.cget("bg")
        except Exception:
            pass

        super().__init__(padre, width=28, height=110,
                         bg=fondo_padre, bd=0, highlightthickness=0)
        self.pack_propagate(False)

        self._canvas = tk.Canvas(
            self, width=28, height=110,
            bg=fondo_padre, highlightthickness=0, bd=0
        )
        self._canvas.place(x=0, y=0, width=28, height=110)

        for w in (self, self._canvas):
            w.bind("<Button-1>", self._al_clic)
            w.bind("<B1-Motion>", self._al_arrastrar)
            w.bind("<ButtonRelease-1>", self._al_soltar)
            w.bind("<MouseWheel>", self._al_scroll)

        self._dibujar()

    def _dibujar(self):
        self._canvas.delete("all")
        cx = 14
        top_track = 8
        bot_track = 102
        ancho_track = 6
        x0 = cx - ancho_track // 2
        x1 = cx + ancho_track // 2

        self._crear_vrect(x0, top_track, x1, bot_track, 3, COLORES["progreso_fondo"])

        fill_y = bot_track - (bot_track - top_track) * self._valor / 100
        if fill_y < bot_track:
            self._crear_vrect(x0, fill_y, x1, bot_track, 3, COLORES["acento"])

        r = 7
        self._canvas.create_oval(
            cx - r, fill_y - r, cx + r, fill_y + r,
            fill=COLORES["acento_brillo"], outline=COLORES["panel_alt"], width=2
        )

    def _crear_vrect(self, x0, y0, x1, y1, r, color):
        r = min(r, (x1 - x0) // 2, max((y1 - y0) // 2, 1))
        self._canvas.create_arc(x0, y0, x1, y0 + 2*r, start=0, extent=180, fill=color, outline=color)
        self._canvas.create_arc(x0, y1 - 2*r, x1, y1, start=180, extent=180, fill=color, outline=color)
        self._canvas.create_rectangle(x0, y0 + r, x1, y1 - r, fill=color, outline=color)

    def _valor_desde_y(self, y):
        top, bot = 8, 102
        ratio = 1 - min(max((y - top) / (bot - top), 0), 1)
        return ratio * 100

    def _al_clic(self, e):
        self._arrastrando = True
        self._valor = self._valor_desde_y(e.y)
        self._dibujar()
        if self._comando:
            self._comando(self._valor)

    def _al_arrastrar(self, e):
        if self._arrastrando:
            self._valor = self._valor_desde_y(e.y)
            self._dibujar()
            if self._comando:
                self._comando(self._valor)

    def _al_soltar(self, _e):
        self._arrastrando = False

    def _al_scroll(self, e):
        delta = 5 if e.delta > 0 else -5
        self._valor = min(max(self._valor + delta, 0), 100)
        self._dibujar()
        if self._comando:
            self._comando(self._valor)

    def get(self):
        return self._valor

    def set(self, valor):
        self._valor = min(max(valor, 0), 100)
        self._dibujar()


# Clase: Descargador de Spotify via YouTube
# Se encarga de bajar audio (MP3) y portadas para canciones encontradas en
# Spotify. El audio se obtiene de YouTube a través de yt-dlp, y la portada
# se descarga directamente desde la URL que devuelve la API de Spotify.

class DescargadorSpotify:
    def __init__(self):
        self.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    def _construir_rutas(self, pista):
        texto = f"{pista.get('title', '')}-{pista.get('artist', '')}"
        uid = pista.get("id") or hashlib.md5(texto.encode("utf-8")).hexdigest()[:10]
        ruta_audio = DIRECTORIO_MUSICA / f"{slugificar(texto)}-{uid}.mp3"
        ruta_portada = DIRECTORIO_CACHE_PORTADAS / f"{uid}.jpg"
        return ruta_audio, ruta_portada

    def asegurar_portada(self, pista):
        _ruta_audio, ruta_portada = self._construir_rutas(pista)
        if ruta_portada.exists():
            return str(ruta_portada)
        url = pista.get("cover_url", "")
        if not url:
            return ""
        respuesta = requests.get(url, timeout=20)
        respuesta.raise_for_status()
        ruta_portada.write_bytes(respuesta.content)
        return str(ruta_portada)

    def asegurar_audio(self, pista):
        ruta_audio, _ruta_portada = self._construir_rutas(pista)
        if ruta_audio.exists():
            return str(ruta_audio)
        consulta = f"{pista.get('title', '')} {pista.get('artist', '')} audio"
        opciones_ydl = {
            "format": "bestaudio/best",
            "default_search": "ytsearch1",
            "noplaylist": True,
            "outtmpl": str(ruta_audio.with_suffix(".%(ext)s")),
            "quiet": True,
            "no_warnings": True,
            "ffmpeg_location": self.ffmpeg,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ],
        }
        with yt_dlp.YoutubeDL(opciones_ydl) as ydl:
            ydl.download([consulta])
        if not ruta_audio.exists():
            raise FileNotFoundError("No se pudo crear el MP3 desde YouTube.")
        return str(ruta_audio)


# Clase principal: Reproductor
# Núcleo de la aplicación. Administra toda la lógica de reproducción, la
# biblioteca de canciones, las playlists, las descargas de Spotify y la
# interfaz gráfica completa. Se divide en métodos por responsabilidad.

class Reproductor:
    def __init__(self, raiz):
        # Configuración de la ventana principal
        # Ajusta el título, tamaño mínimo y color de fondo de la ventana raíz.

        self.raiz = raiz
        self.raiz.title("JansonMusic")
        self.raiz.geometry("1400x860")
        self.raiz.minsize(1200, 720)
        self.raiz.configure(bg=COLORES["fondo"])

        # Inicialización de servicios
        # Arranca el audio, conecta con la API de Spotify, crea el descargador
        # y prepara la cola para comunicación entre hilos y el hilo principal.

        self.audio_ok = inicializar_audio()
        self.spotify = SpotifyBuscar.from_env_or_defaults()
        self.descargador = DescargadorSpotify()
        self.cola_ui = queue.Queue()
        self.cache_imagenes = {}

        # Estado de la biblioteca y reproducción
        # Variables que rastrean qué canción suena, en qué playlist/carpeta
        # estamos, si está en pausa, si hay shuffle/loop activo, etc.

        self.biblioteca = {}
        self.playlists = {}
        self.resultados_spotify = []
        self.pistas_vista = []
        self.id_pista_actual = None
        self.ruta_audio_actual = ""
        self.duracion_actual = 0.0
        self.indice_actual = -1
        self.nombre_playlist_actual = ""
        self.ruta_portada_actual = ""
        self.reproduciendo = False
        self.en_pausa = False
        self.loop = False
        self.shuffle = False
        self._inicio_reproduccion = 0.0
        self._segundos_en_pausa = 0.0
        self.ultima_busqueda_spotify = ""
        self.mapa_resultados_spotify = {}
        self.auto_play_spotify_en_curso = False
        self.panel_izq_activo = None
        self.tamaño_portada_principal = (56, 56)

        # Construcción de la interfaz
        # Crea todos los estilos ttk, luego construye la UI y carga los datos.

        self._construir_estilos()
        self._construir_ui()
        self._cargar_datos()
        self._escanear_musica_existente()
        self._refrescar_todas_las_vistas()

        if self.audio_ok:
            pygame.mixer.music.set_volume(0.7)
        else:
            messagebox.showwarning("Audio", "No se pudo iniciar el sistema de audio.")

        # Bucles periódicos
        # Tres timers que se auto-reprograman: uno procesa la cola de UI,
        # otro actualiza la barra de progreso, y el tercero detecta el fin
        # de una canción para pasar a la siguiente.

        self.raiz.after(150, self._procesar_cola_ui)
        self.raiz.after(250, self._actualizar_progreso)
        self.raiz.after(500, self._verificar_fin)

    # Estilos de widgets ttk
    # Personaliza la apariencia del Treeview (tablas) y el Scrollbar para que
    # coincidan con la paleta oscura de la aplicación.

    def _construir_estilos(self):
        estilo = ttk.Style()
        try:
            estilo.theme_use("clam")
        except Exception:
            pass
        estilo.configure(
            "Treeview",
            background=COLORES["superficie"],
            fieldbackground=COLORES["superficie"],
            foreground=COLORES["texto"],
            rowheight=44,
            bordercolor=COLORES["linea"],
            lightcolor=COLORES["linea"],
            darkcolor=COLORES["linea"],
            font=(FUENTE_PRINCIPAL, 10),
        )
        estilo.configure(
            "Treeview.Heading",
            background=COLORES["panel_alt"],
            foreground=COLORES["apagado"],
            relief="flat",
            borderwidth=0,
            font=(FUENTE_PRINCIPAL, 9, "bold"),
        )
        estilo.map(
            "Treeview",
            background=[("selected", COLORES["acento_suave"])],
            foreground=[("selected", COLORES["texto"])],
        )
        estilo.configure(
            "Oscuro.Vertical.TScrollbar",
            background=COLORES["scrollbar"],
            troughcolor=COLORES["panel_alt"],
            arrowcolor=COLORES["apagado"],
            bordercolor=COLORES["panel_alt"],
            darkcolor=COLORES["panel_alt"],
            lightcolor=COLORES["panel_alt"],
        )

    # Helpers de widgets
    # Métodos cortos para crear los tipos de botones, chips, etiquetas y
    # separadores usados en toda la UI, evitando repetición de código.

    def _crear_btn(self, padre, texto, comando, acento=False, ancho=110, alto=34, icono=None):
        return BotonRedondeado(
            padre, texto=texto, comando=comando,
            ancho=ancho, alto=alto, radio=17,
            acento=acento, icono=icono,
            fuente=(FUENTE_PRINCIPAL, 10, "bold"),
        )

    def _crear_chip(self, padre, texto, comando, ancho=80, alto=28):
        return BotonRedondeado(
            padre, texto=texto, comando=comando,
            ancho=ancho, alto=alto, radio=14,
            color_fondo=COLORES["chip"],
            color_texto=COLORES["texto2"],
            color_hover=COLORES["chip_hover"],
            fuente=(FUENTE_PRINCIPAL, 9, "bold"),
        )

    def _etiqueta(self, padre, texto, tamaño=10, negrita=False, color=None, **kw):
        peso = kw.get("weight", "bold" if negrita else "normal")
        return tk.Label(
            padre, text=texto,
            font=(FUENTE_PRINCIPAL, tamaño, peso),
            bg=padre.cget("bg"),
            fg=color or COLORES["texto"],
            **{k: v for k, v in kw.items() if k not in ("weight",)}
        )

    def _separador(self, padre, pad=(4, 4)):
        tk.Frame(padre, bg=COLORES["linea"], height=1).pack(fill="x", padx=12, pady=pad)

    def _panel(self, padre, **kw):
        return tk.Frame(padre, bg=COLORES["superficie"],
                        highlightthickness=1,
                        highlightbackground=COLORES["linea"], **kw)

    def _set_estado(self, texto, color=None):
        self.etiqueta_estado.config(text=texto, fg=color or COLORES["texto2"])

    # Construcción de la interfaz completa
    # Arma el layout general: barra lateral izquierda (sidebar) y área central.
    # Todo queda dentro de un Frame principal con padding.

    def _construir_ui(self):
        app = tk.Frame(self.raiz, bg=COLORES["fondo"])
        app.pack(fill="both", expand=True, padx=10, pady=10)

        cuerpo = tk.Frame(app, bg=COLORES["fondo"])
        cuerpo.pack(fill="both", expand=True)

        sidebar = tk.Frame(cuerpo, bg=COLORES["panel"], width=270,
                           highlightthickness=1, highlightbackground=COLORES["linea"])
        sidebar.pack(side="left", fill="y", padx=(0, 10))
        sidebar.pack_propagate(False)

        contenido = tk.Frame(cuerpo, bg=COLORES["fondo"])
        contenido.pack(side="left", fill="both", expand=True)

        self._construir_izquierda(sidebar)
        self._construir_centro(contenido)
        self._mostrar_panel_izq("canciones")

    # Sidebar izquierdo
    # Construye: logo, botones de navegación (Canciones / Carpetas / Playlists),
    # los tres paneles intercambiables, y la tarjeta "Reproduciendo ahora".

    def _construir_izquierda(self, padre):
        # Marca / logo
        marca = tk.Frame(padre, bg=COLORES["panel"])
        marca.pack(fill="x", padx=16, pady=(18, 10))

        icono_canvas = tk.Canvas(marca, width=36, height=36, bg=COLORES["panel"],
                                 highlightthickness=0, bd=0)
        icono_canvas.pack(side="left", padx=(0, 10))
        icono_canvas.create_oval(2, 2, 34, 34, fill=COLORES["acento"], outline="")
        icono_canvas.create_oval(10, 10, 26, 26, fill=COLORES["panel"], outline="")
        icono_canvas.create_oval(15, 15, 21, 21, fill=COLORES["acento"], outline="")

        tk.Label(
            marca, text="JansonMusic",
            font=(FUENTE_PRINCIPAL, 15, "bold"),
            bg=COLORES["panel"], fg=COLORES["acento"]
        ).pack(side="left", anchor="w")

        self._separador(padre, pad=(0, 8))

        # Botones de navegación
        nav = tk.Frame(padre, bg=COLORES["panel"])
        nav.pack(fill="x", padx=14, pady=(0, 8))

        self.btn_menu_canciones = self._crear_btn_nav(nav, "♪  Canciones", lambda: self._mostrar_panel_izq("canciones"))
        self.btn_menu_canciones.pack(fill="x", pady=(0, 4))
        self.btn_menu_carpetas = self._crear_btn_nav(nav, "⊞  Carpetas", lambda: self._mostrar_panel_izq("carpeta"))
        self.btn_menu_carpetas.pack(fill="x", pady=(0, 4))
        self.btn_menu_playlist = self._crear_btn_nav(nav, "☰  Playlists", lambda: self._mostrar_panel_izq("playlist"))
        self.btn_menu_playlist.pack(fill="x")

        self._separador(padre, pad=(8, 6))

        # Contenedor de paneles intercambiables
        self.contenedor_panel_izq = tk.Frame(padre, bg=COLORES["panel"])
        self.contenedor_panel_izq.pack(fill="both", expand=True, padx=14)
        self.contenedor_panel_izq.pack_propagate(False)

        # Panel Canciones
        self.panel_canciones = tk.Frame(self.contenedor_panel_izq, bg=COLORES["panel"])
        tk.Label(
            self.panel_canciones,
            text="Modo Canciones\nUsá el buscador superior\npara buscar en Spotify.",
            font=(FUENTE_PRINCIPAL, 10),
            bg=COLORES["panel"],
            fg=COLORES["apagado"],
            justify="left",
        ).pack(anchor="w", pady=(10, 0))

        # Panel Carpeta
        self.panel_carpeta = tk.Frame(self.contenedor_panel_izq, bg=COLORES["panel"])
        self.btn_importar = self._crear_btn(self.panel_carpeta, "+ Carpeta", self._importar_carpeta,
                                            acento=True, ancho=200, alto=34)
        self.btn_importar.pack(pady=(4, 10))

        tk.Label(self.panel_carpeta, text="CARPETAS",
                 font=(FUENTE_PRINCIPAL, 8, "bold"), bg=COLORES["panel"],
                 fg=COLORES["apagado"]).pack(anchor="w")

        self.listbox_carpetas = self._crear_listbox(self.panel_carpeta, alto=4)
        self.listbox_carpetas.pack(fill="x", pady=(4, 8))
        self.listbox_carpetas.bind("<<ListboxSelect>>", lambda _e: self._al_seleccionar_carpeta())

        self._separador(self.panel_carpeta, pad=(0, 6))

        tk.Label(self.panel_carpeta, text="CANCIONES EN CARPETA",
                 font=(FUENTE_PRINCIPAL, 8, "bold"), bg=COLORES["panel"],
                 fg=COLORES["apagado"]).pack(anchor="w")

        self.listbox_canciones_carpeta = self._crear_listbox(self.panel_carpeta)
        self.listbox_canciones_carpeta.pack(fill="both", expand=True, pady=(4, 0))
        self.listbox_canciones_carpeta.bind("<Double-1>", lambda _e: self._reproducir_cancion_carpeta_seleccionada())
        self.listbox_canciones_carpeta.bind("<<ListboxSelect>>", lambda _e: self._previsualizar_cancion_carpeta_seleccionada())
        self._lista_canciones_carpeta = []

        # Panel Playlist
        self.panel_playlist = tk.Frame(self.contenedor_panel_izq, bg=COLORES["panel"])
        fila = tk.Frame(self.panel_playlist, bg=COLORES["panel"])
        fila.pack(fill="x", pady=(4, 8))
        self._crear_chip(fila, "Crear", self._crear_playlist, ancho=88, alto=28).pack(side="left", padx=(0, 6))
        self._crear_chip(fila, "Borrar", self._borrar_playlist, ancho=88, alto=28).pack(side="left")

        tk.Label(self.panel_playlist, text="PLAYLISTS",
                 font=(FUENTE_PRINCIPAL, 8, "bold"), bg=COLORES["panel"],
                 fg=COLORES["apagado"]).pack(anchor="w")

        self.listbox_playlists = self._crear_listbox(self.panel_playlist, alto=4)
        self.listbox_playlists.pack(fill="x", pady=(4, 8))
        self.listbox_playlists.bind("<<ListboxSelect>>", lambda _e: self._al_seleccionar_playlist())

        self._separador(self.panel_playlist, pad=(0, 6))

        tk.Label(self.panel_playlist, text="CANCIONES EN PLAYLIST",
                 font=(FUENTE_PRINCIPAL, 8, "bold"), bg=COLORES["panel"],
                 fg=COLORES["apagado"]).pack(anchor="w")

        self.listbox_canciones_playlist = self._crear_listbox(self.panel_playlist)
        self.listbox_canciones_playlist.pack(fill="both", expand=True, pady=(4, 0))
        self.listbox_canciones_playlist.bind("<Double-1>", lambda _e: self._reproducir_cancion_playlist_seleccionada())
        self.listbox_canciones_playlist.bind("<<ListboxSelect>>", lambda _e: self._previsualizar_cancion_playlist_seleccionada())
        self._lista_canciones_playlist = []

        self._separador(padre, pad=(6, 8))

        # Tarjeta "Reproduciendo ahora"
        self._construir_tarjeta_reproduciendo(padre)

    # Botón de navegación del sidebar
    # Crea una etiqueta con aspecto de botón que cambia de color al hacer hover
    # y al estar activo (resaltado dorado).

    def _crear_btn_nav(self, padre, texto, comando):
        btn = tk.Label(
            padre, text=texto,
            font=(FUENTE_PRINCIPAL, 10),
            bg=COLORES["panel"],
            fg=COLORES["texto2"],
            anchor="w", padx=12, pady=8,
            cursor="hand2",
        )
        btn.bind("<Enter>", lambda _e, b=btn: b.config(bg=COLORES["superficie"], fg=COLORES["texto"]))
        btn.bind("<Leave>", lambda _e, b=btn: b.config(
            bg=COLORES["acento"] if btn.cget("fg") == "white" else COLORES["panel"],
            fg="white" if btn.cget("bg") == COLORES["acento"] else COLORES["texto2"]
        ))
        btn.bind("<Button-1>", lambda _e: comando())
        return btn

    def _activar_btn_nav(self, btn):
        for b in [self.btn_menu_canciones, self.btn_menu_carpetas, self.btn_menu_playlist]:
            b.config(bg=COLORES["panel"], fg=COLORES["texto2"])
        btn.config(bg=COLORES["acento"], fg="white")

    def _crear_listbox(self, padre, alto=8):
        lb = tk.Listbox(
            padre,
            height=alto,
            bg=COLORES["superficie"],
            fg=COLORES["texto"],
            selectbackground=COLORES["acento_suave"],
            selectforeground=COLORES["texto"],
            borderwidth=0,
            relief="flat",
            activestyle="none",
            font=(FUENTE_PRINCIPAL, 9),
            highlightthickness=1,
            highlightbackground=COLORES["linea"],
        )
        return lb

    # Tarjeta "Reproduciendo ahora"
    # Pequeña card en la parte inferior del sidebar que muestra la portada en
    # miniatura, título y artista de la canción que suena en este momento.

    def _construir_tarjeta_reproduciendo(self, padre):
        tarjeta = tk.Frame(padre, bg=COLORES["superficie"],
                           highlightthickness=1, highlightbackground=COLORES["linea"])
        tarjeta.pack(fill="x", padx=14, pady=(0, 16))

        interior = tk.Frame(tarjeta, bg=COLORES["superficie"])
        interior.pack(fill="x", padx=12, pady=10)

        self.etiq_portada_ahora = tk.Label(interior, bg=COLORES["superficie"])
        self.etiq_portada_ahora.pack(side="left", padx=(0, 10))

        lado_texto = tk.Frame(interior, bg=COLORES["superficie"])
        lado_texto.pack(side="left", fill="x", expand=True)

        self.etiq_titulo_ahora = tk.Label(
            lado_texto, text="Sin canción",
            font=(FUENTE_PRINCIPAL, 10, "bold"),
            bg=COLORES["superficie"], fg=COLORES["texto"],
            wraplength=160, justify="left", anchor="w"
        )
        self.etiq_titulo_ahora.pack(fill="x")
        self.etiq_artista_ahora = tk.Label(
            lado_texto, text="Seleccioná una canción",
            font=(FUENTE_PRINCIPAL, 9),
            bg=COLORES["superficie"], fg=COLORES["apagado"],
            wraplength=160, justify="left", anchor="w"
        )
        self.etiq_artista_ahora.pack(fill="x")
        self._set_tarjeta_ahora_placeholder()

    # Selector de panel izquierdo
    # Oculta los tres paneles y muestra solo el seleccionado. También ajusta
    # el hint del buscador y el botón de nav activo.

    def _mostrar_panel_izq(self, nombre_panel):
        self.panel_canciones.pack_forget()
        self.panel_carpeta.pack_forget()
        self.panel_playlist.pack_forget()

        self.panel_izq_activo = nombre_panel
        if nombre_panel == "canciones":
            self.panel_canciones.pack(fill="both", expand=True)
            self._activar_btn_nav(self.btn_menu_canciones)
            self.frame_resultados_locales.pack_forget()
            self.frame_resultados_spotify.pack(fill="both", expand=True)
            self._actualizar_hint_busqueda("Buscar en Spotify...")
        elif nombre_panel == "playlist":
            self.panel_playlist.pack(fill="both", expand=True)
            self._activar_btn_nav(self.btn_menu_playlist)
            self.frame_resultados_locales.pack_forget()
            self.frame_resultados_spotify.pack(fill="both", expand=True)
            self._actualizar_hint_busqueda("Buscar en Spotify para agregar a playlist...")
            self._refrescar_canciones_playlist()
        else:
            self.panel_carpeta.pack(fill="both", expand=True)
            self._activar_btn_nav(self.btn_menu_carpetas)
            self.frame_resultados_locales.pack_forget()
            self.frame_resultados_spotify.pack(fill="both", expand=True)
            self._actualizar_hint_busqueda("Buscar en Spotify para guardar en carpeta...")
            self._refrescar_listas_carpeta()

    # Área central de la aplicación
    # Construye: barra de búsqueda superior, panel de detalle con portada grande,
    # tabla de resultados Spotify, tabla de biblioteca local (oculta por defecto)
    # y la barra de controles de reproducción en la parte inferior.

    def _construir_centro(self, padre):
        # Barra de búsqueda
        top = tk.Frame(padre, bg=COLORES["fondo"])
        top.pack(fill="x", pady=(0, 8))

        envoltorio_busqueda = tk.Frame(
            top, bg=COLORES["superficie"],
            highlightthickness=1, highlightbackground=COLORES["linea"]
        )
        envoltorio_busqueda.pack(side="left", fill="x", expand=True, ipady=0)

        tk.Label(envoltorio_busqueda, text="🔍", bg=COLORES["superficie"],
                 fg=COLORES["apagado"], font=(FUENTE_PRINCIPAL, 11)).pack(side="left", padx=(10, 2))

        self.entrada_spotify = tk.Entry(
            envoltorio_busqueda,
            bg=COLORES["superficie"], fg=COLORES["texto"],
            insertbackground=COLORES["acento"],
            relief="flat", bd=0,
            font=(FUENTE_PRINCIPAL, 11)
        )
        self.entrada_spotify.pack(side="left", fill="x", expand=True, ipady=8)
        self.entrada_spotify.bind("<Return>", lambda _e: self._buscar_spotify())

        self.btn_spotify = self._crear_chip(envoltorio_busqueda, "Buscar", self._buscar_spotify, ancho=80, alto=30)
        self.btn_spotify.pack(side="right", padx=8, pady=5)

        # Contenedor de resultados
        self.contenedor_resultados = tk.Frame(padre, bg=COLORES["panel_alt"],
                                              highlightthickness=1,
                                              highlightbackground=COLORES["linea"])
        self.contenedor_resultados.pack(fill="both", expand=True, pady=(0, 8))

        self.frame_resultados_spotify = tk.Frame(self.contenedor_resultados, bg=COLORES["panel_alt"])
        self.frame_resultados_locales = tk.Frame(self.contenedor_resultados, bg=COLORES["panel_alt"])

        # Panel de detalle derecho (portada grande + info)
        panel_detalle = tk.Frame(
            self.frame_resultados_spotify, bg=COLORES["panel"],
            highlightthickness=1, highlightbackground=COLORES["linea"],
            width=290
        )
        panel_detalle.pack(side="right", fill="y", padx=(4, 8), pady=8)
        panel_detalle.pack_propagate(False)

        frame_portada = tk.Frame(panel_detalle, bg=COLORES["panel"])
        frame_portada.pack(fill="x", padx=20, pady=(24, 12))

        self.img_preview_superior = tk.Label(frame_portada, bg=COLORES["panel"])
        self.img_preview_superior.pack(anchor="center")
        self.etiq_portada = self.img_preview_superior

        barra_dorada = tk.Canvas(panel_detalle, height=3, bg=COLORES["panel"],
                                 highlightthickness=0)
        barra_dorada.pack(fill="x", padx=20, pady=(0, 14))
        barra_dorada.bind("<Configure>", lambda e, c=barra_dorada: (
            c.delete("all"),
            c.create_rectangle(0, 0, e.width, 3, fill=COLORES["acento"], outline="")
        ))

        self.etiq_titulo_preview = tk.Label(
            panel_detalle, text="Sin canción",
            font=(FUENTE_PRINCIPAL, 13, "bold"),
            bg=COLORES["panel"], fg=COLORES["texto"],
            anchor="center", justify="center",
            wraplength=250
        )
        self.etiq_titulo_preview.pack(fill="x", padx=20)
        self.etiq_titulo_pista = self.etiq_titulo_preview

        self.etiq_artista_preview = tk.Label(
            panel_detalle, text="—",
            font=(FUENTE_PRINCIPAL, 10),
            bg=COLORES["panel"], fg=COLORES["acento"],
            anchor="center", justify="center",
            wraplength=250
        )
        self.etiq_artista_preview.pack(fill="x", padx=20, pady=(6, 0))
        self.etiq_artista_pista = self.etiq_artista_preview

        # Tabla de resultados Spotify
        izq_spotify = tk.Frame(self.frame_resultados_spotify, bg=COLORES["panel_alt"])
        izq_spotify.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)

        self.tabla_spotify = ttk.Treeview(
            izq_spotify, columns=("artista",),
            show="tree headings", height=10
        )
        self.tabla_spotify.heading("#0", text="Canción")
        self.tabla_spotify.heading("artista", text="Artista")
        self.tabla_spotify.column("#0", width=230, minwidth=140)
        self.tabla_spotify.column("artista", width=150, minwidth=80)
        self.tabla_spotify.pack(side="left", fill="both", expand=True)
        self.tabla_spotify.bind("<<TreeviewSelect>>", lambda _e: self._al_seleccionar_tabla_spotify())
        scroll_sp = ttk.Scrollbar(izq_spotify, orient="vertical",
                                  command=self.tabla_spotify.yview,
                                  style="Oscuro.Vertical.TScrollbar")
        scroll_sp.pack(side="right", fill="y")
        self.tabla_spotify.configure(yscrollcommand=scroll_sp.set)

        self._set_portada_grande_placeholder()

        # Tabla de biblioteca local (oculta por defecto)
        envoltorio_local = tk.Frame(self.frame_resultados_locales, bg=COLORES["panel_alt"])
        envoltorio_local.pack(fill="both", expand=True, padx=8, pady=8)
        columnas = ("artista", "album", "genero", "duracion")
        self.tabla = ttk.Treeview(envoltorio_local, columns=columnas, show="tree headings", height=10)
        self.tabla.heading("#0", text="Canción")
        self.tabla.heading("artista", text="Artista")
        self.tabla.heading("album", text="Álbum")
        self.tabla.heading("genero", text="Género")
        self.tabla.heading("duracion", text="Dur.")
        self.tabla.column("#0", width=340, minwidth=160)
        self.tabla.column("artista", width=190, minwidth=80)
        self.tabla.column("album", width=190, minwidth=80)
        self.tabla.column("genero", width=110, minwidth=60)
        self.tabla.column("duracion", width=70, anchor="center", minwidth=50)
        self.tabla.pack(side="left", fill="both", expand=True)
        self.tabla.bind("<Double-1>", lambda _e: self._reproducir_pista_seleccionada())
        self.tabla.bind("<<TreeviewSelect>>", lambda _e: self._previsualizar_seleccion_biblioteca())
        barra_y = ttk.Scrollbar(envoltorio_local, orient="vertical",
                                command=self.tabla.yview,
                                style="Oscuro.Vertical.TScrollbar")
        barra_y.pack(side="right", fill="y")
        self.tabla.configure(yscrollcommand=barra_y.set)

        # Widgets ocultos para compatibilidad interna
        self.entrada_busqueda = tk.Entry(padre)
        self.var_campo_busqueda = tk.StringVar(value="Cancion")
        self.combo_campo_busqueda = ttk.Combobox(
            padre, textvariable=self.var_campo_busqueda, state="readonly",
            values=["Cancion", "Artista", "Album", "Genero", "Playlist"]
        )
        self.var_orden = tk.StringVar(value="Cancion")
        self.combo_orden = ttk.Combobox(
            padre, textvariable=self.var_orden, state="readonly",
            values=["Cancion", "Artista", "Album", "Genero", "Duracion"]
        )

        # Barra de controles de reproducción
        self._construir_controles(padre)

    # Barra de controles de reproducción
    # Fila inferior con: perilla de volumen, etiqueta de estado, barra de
    # progreso, tiempo actual/total y botones (Prev, Stop, Play, Next,
    # Shuffle, Loop, Agregar a playlist).

    def _construir_controles(self, padre):
        inferior = tk.Frame(padre, bg=COLORES["panel"],
                            highlightthickness=1, highlightbackground=COLORES["linea"])
        inferior.pack(fill="x")

        # Volumen
        frame_vol = tk.Frame(inferior, bg=COLORES["panel"], width=80)
        frame_vol.pack(side="left", fill="y", padx=(14, 8), pady=12)
        frame_vol.pack_propagate(False)

        tk.Label(frame_vol, text="VOL", font=(FUENTE_PRINCIPAL, 8, "bold"),
                 bg=COLORES["panel"], fg=COLORES["apagado"]).pack()

        self.perilla_volumen = PerillaVolumen(frame_vol, comando=self._set_volumen_perilla, inicial=70)
        self.perilla_volumen.configure(bg=COLORES["panel"])
        self.perilla_volumen.pack(pady=(4, 2))

        self.etiq_vol = tk.Label(frame_vol, text="70%",
                                 font=(FUENTE_PRINCIPAL, 8),
                                 bg=COLORES["panel"], fg=COLORES["acento"])
        self.etiq_vol.pack()

        self.volume_scale = self.perilla_volumen  # alias de compatibilidad

        # Centro: estado + progreso + botones
        controles_centro = tk.Frame(inferior, bg=COLORES["panel"])
        controles_centro.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        self.etiqueta_estado = tk.Label(
            controles_centro, text="Listo",
            font=(FUENTE_PRINCIPAL, 10, "bold"),
            bg=COLORES["panel"], fg=COLORES["acento"]
        )
        self.etiqueta_estado.pack(anchor="center", pady=(0, 4))

        self.progreso = BarraProgreso(controles_centro, al_buscar=self._saltar_audio)
        self.progreso.configure(bg=COLORES["panel"])
        self.progreso.pack(fill="x", padx=60, pady=(0, 2))

        tiempos = tk.Frame(controles_centro, bg=COLORES["panel"])
        tiempos.pack(fill="x", padx=60)
        self.etiq_tiempo_actual = tk.Label(
            tiempos, text="00:00",
            font=(FUENTE_MONO, 9),
            bg=COLORES["panel"], fg=COLORES["acento"]
        )
        self.etiq_tiempo_actual.pack(side="left")
        self.etiq_tiempo_total = tk.Label(
            tiempos, text="00:00",
            font=(FUENTE_MONO, 9),
            bg=COLORES["panel"], fg=COLORES["apagado"]
        )
        self.etiq_tiempo_total.pack(side="right")

        # Fila de botones de control
        fila_controles = tk.Frame(controles_centro, bg=COLORES["panel"])
        fila_controles.pack(pady=(10, 0))

        self.btn_anterior = self._crear_btn(fila_controles, "Prev", self._cancion_anterior, ancho=64, alto=38, icono="◀◀")
        self.btn_anterior.pack(side="left", padx=3)

        self.btn_stop = self._crear_btn(fila_controles, "Stop", self._detener_cancion, ancho=64, alto=38, icono="■")
        self.btn_stop.pack(side="left", padx=3)

        self.btn_play = self._crear_btn(fila_controles, "Play", self._toggle_reproduccion,
                                        acento=True, ancho=96, alto=42, icono="▶")
        self.btn_play.pack(side="left", padx=8)

        self.btn_siguiente = self._crear_btn(fila_controles, "Next", self._siguiente_cancion, ancho=64, alto=38, icono="▶▶")
        self.btn_siguiente.pack(side="left", padx=3)

        tk.Frame(fila_controles, bg=COLORES["panel"], width=16).pack(side="left")

        self.btn_shuffle = self._crear_btn(fila_controles, "Shuffle", self._toggle_shuffle, ancho=90, alto=34)
        self.btn_shuffle.pack(side="left", padx=3)

        self.btn_loop = self._crear_btn(fila_controles, "Loop", self._toggle_loop, ancho=76, alto=34)
        self.btn_loop.pack(side="left", padx=3)

        tk.Frame(fila_controles, bg=COLORES["panel"], width=16).pack(side="left")

        self.btn_agregar_playlist = self._crear_btn(fila_controles, "Playlist", self._agregar_seleccionado_a_playlist,
                                                    ancho=100, alto=34, icono="+")
        self.btn_agregar_playlist.pack(side="left", padx=3)

        self.btn_pausa = self.btn_play  # alias

    # Helpers de portada
    # Métodos para mostrar placeholders decorativos cuando no hay portada
    # disponible, tanto en el panel grande como en la tarjeta pequeña.

    def _set_portada_grande_placeholder(self):
        tamaño = 220
        imagen = Image.new("RGBA", (tamaño, tamaño), (0, 0, 0, 0))
        dibujo = ImageDraw.Draw(imagen)
        dibujo.rounded_rectangle((0, 0, tamaño - 1, tamaño - 1), radius=22, fill=COLORES["superficie"])
        dibujo.ellipse((tamaño // 2 - 50, tamaño // 2 - 50, tamaño // 2 + 50, tamaño // 2 + 50),
                       fill=COLORES["panel_alt"])
        dibujo.ellipse((tamaño // 2 - 32, tamaño // 2 - 32, tamaño // 2 + 32, tamaño // 2 + 32),
                       fill=COLORES["acento_suave"])
        dibujo.ellipse((tamaño // 2 - 14, tamaño // 2 - 14, tamaño // 2 + 14, tamaño // 2 + 14),
                       fill=COLORES["panel"])
        foto = ImageTk.PhotoImage(imagen)
        self.img_preview_superior.config(image=foto)
        self.img_preview_superior.image = foto
        self.etiq_titulo_preview.config(text="Sin canción")
        self.etiq_artista_preview.config(text="—")

    def _set_portada_placeholder(self, texto=""):
        self._set_portada_grande_placeholder()

    def _set_tarjeta_ahora_placeholder(self):
        imagen = Image.new("RGBA", (44, 44), (0, 0, 0, 0))
        dibujo = ImageDraw.Draw(imagen)
        dibujo.rounded_rectangle((0, 0, 43, 43), radius=10, fill=COLORES["superficie"])
        dibujo.ellipse((10, 10, 34, 34), fill=COLORES["acento_suave"])
        dibujo.ellipse((18, 18, 26, 26), fill=COLORES["superficie"])
        foto = ImageTk.PhotoImage(imagen)
        self.etiq_portada_ahora.config(image=foto)
        self.etiq_portada_ahora.image = foto
        self.etiq_titulo_ahora.config(text="Sin canción")
        self.etiq_artista_ahora.config(text="Seleccioná una canción")

    def _set_tarjeta_ahora_pista(self, titulo, artista, fuente_portada=""):
        self.etiq_titulo_ahora.config(text=titulo or "Sin canción")
        self.etiq_artista_ahora.config(text=artista or "Desconocido")
        if fuente_portada:
            try:
                img = self._cargar_imagen(fuente_portada, (44, 44))
                self.etiq_portada_ahora.config(image=img)
                self.etiq_portada_ahora.image = img
                return
            except Exception:
                pass
        self._set_tarjeta_ahora_placeholder()

    # Control de volumen
    # Conecta la perilla de volumen con pygame.mixer y actualiza la etiqueta
    # con el porcentaje actual.

    def _set_volumen_perilla(self, valor):
        if self.audio_ok:
            pygame.mixer.music.set_volume(float(valor) / 100)
        self.etiq_vol.config(text=f"{int(valor)}%")

    def _set_volumen(self, valor):
        self._set_volumen_perilla(float(valor))

    # Hint del buscador
    # Muestra texto de ayuda en el campo de búsqueda cuando está vacío, y lo
    # limpia automáticamente al hacer foco.

    def _actualizar_hint_busqueda(self, hint):
        actual = self.entrada_spotify.get()
        hints_conocidos = (
            "Buscar en Spotify...",
            "Buscar en Spotify para agregar a playlist...",
            "Buscar en Spotify para guardar en carpeta...",
        )
        if not actual or actual in hints_conocidos:
            self.entrada_spotify.delete(0, "end")
            self.entrada_spotify.config(fg=COLORES["apagado"])
            self.entrada_spotify.insert(0, hint)

        def _al_enfocar(e):
            val = self.entrada_spotify.get()
            if val in hints_conocidos:
                self.entrada_spotify.delete(0, "end")
                self.entrada_spotify.config(fg=COLORES["texto"])

        def _al_desenfocar(e):
            if not self.entrada_spotify.get().strip():
                self.entrada_spotify.config(fg=COLORES["apagado"])
                self.entrada_spotify.insert(0, hint)

        self.entrada_spotify.bind("<FocusIn>", _al_enfocar)
        self.entrada_spotify.bind("<FocusOut>", _al_desenfocar)

    def _obtener_consulta_real(self):
        val = self.entrada_spotify.get().strip()
        if val in (
            "Buscar en Spotify...",
            "Buscar en Spotify para agregar a playlist...",
            "Buscar en Spotify para guardar en carpeta...",
        ):
            return ""
        return val

    def _set_popup_spotify_visible(self, visible):
        pass

    # Gestión de biblioteca y datos
    # Métodos para cargar/guardar el JSON de biblioteca, escanear la carpeta
    # de música, extraer metadatos de archivos de audio y refrescar las vistas.

    def _refrescar_listas_carpeta(self):
        if not hasattr(self, "listbox_carpetas"):
            return
        actual = self.listbox_carpetas.get(self.listbox_carpetas.curselection()[0]) if self.listbox_carpetas.curselection() else ""
        carpetas = sorted(
            {str(Path(pista.get("path", "")).parent) for pista in self.biblioteca.values() if pista.get("path")},
            key=str.lower,
        )
        self.listbox_carpetas.delete(0, "end")
        for carpeta in carpetas:
            self.listbox_carpetas.insert("end", carpeta)
        if actual and actual in carpetas:
            idx = carpetas.index(actual)
            self.listbox_carpetas.selection_set(idx)
        elif carpetas:
            self.listbox_carpetas.selection_set(0)
        self._al_seleccionar_carpeta()

    def _al_seleccionar_carpeta(self):
        if not hasattr(self, "listbox_carpetas"):
            return
        sel = self.listbox_carpetas.curselection()
        self._lista_canciones_carpeta = []
        self.listbox_canciones_carpeta.delete(0, "end")
        if not sel:
            return
        carpeta = self.listbox_carpetas.get(sel[0])
        pistas = [
            t for t in self.biblioteca.values()
            if str(Path(t.get("path", "")).parent) == carpeta
        ]
        pistas.sort(key=lambda t: t.get("title", "").lower())
        self._lista_canciones_carpeta = pistas
        for t in pistas:
            dur = self._formatear_tiempo(t.get("duration", 0))
            self.listbox_canciones_carpeta.insert("end", f"{t.get('title', '?')}  [{dur}]")

    def _reproducir_cancion_carpeta_seleccionada(self):
        sel = self.listbox_canciones_carpeta.curselection()
        if not sel:
            return
        pista = self._lista_canciones_carpeta[sel[0]]
        self.pistas_vista = self._lista_canciones_carpeta
        self.nombre_playlist_actual = ""
        self._reproducir_pista(pista)

    def _previsualizar_cancion_carpeta_seleccionada(self):
        sel = self.listbox_canciones_carpeta.curselection()
        if not sel:
            return
        pista = self._lista_canciones_carpeta[sel[0]]
        self._mostrar_info_pista(pista)

    def _cargar_imagen(self, fuente, tamaño):
        clave = f"{fuente}|{tamaño}"
        if clave in self.cache_imagenes:
            return self.cache_imagenes[clave]
        if not fuente:
            imagen = Image.new("RGB", tamaño, COLORES["superficie"])
        elif str(fuente).startswith("http"):
            respuesta = requests.get(fuente, timeout=20)
            respuesta.raise_for_status()
            imagen = Image.open(BytesIO(respuesta.content))
        else:
            imagen = Image.open(fuente)
        imagen = imagen.convert("RGB").resize(tamaño, Image.Resampling.LANCZOS)
        foto = ImageTk.PhotoImage(imagen)
        self.cache_imagenes[clave] = foto
        return foto

    def _cargar_datos(self):
        if not ARCHIVO_DATOS.exists():
            self.biblioteca = {}
            self.playlists = {"Favoritos": []}
            self._guardar_datos()
            return
        try:
            datos = json.loads(ARCHIVO_DATOS.read_text(encoding="utf-8"))
            if isinstance(datos, list):
                self.biblioteca = {}
                self.playlists = {"Favoritos": []}
                for raw in datos:
                    ruta = Path(raw)
                    if ruta.exists() and ruta.suffix.lower() in EXTENSIONES_AUDIO:
                        pista = self._extraer_metadatos(ruta)
                        self.biblioteca[pista["id"]] = pista
                        self.playlists["Favoritos"].append(pista["id"])
                self._guardar_datos()
                return
            self.biblioteca = {t["id"]: t for t in datos.get("library", []) if isinstance(t, dict) and t.get("id")}
            self.playlists = datos.get("playlists", {}) if isinstance(datos.get("playlists", {}), dict) else {}
            if not self.playlists:
                self.playlists = {"Favoritos": []}
        except Exception:
            self.biblioteca = {}
            self.playlists = {"Favoritos": []}
            self._guardar_datos()

        ids_validos = set(self.biblioteca.keys())
        for nombre, ids in list(self.playlists.items()):
            self.playlists[nombre] = [tid for tid in ids if tid in ids_validos]

    def _guardar_datos(self):
        payload = {"library": list(self.biblioteca.values()), "playlists": self.playlists}
        ARCHIVO_DATOS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _escanear_musica_existente(self):
        importadas = 0
        for ruta in DIRECTORIO_MUSICA.rglob("*"):
            if ruta.suffix.lower() not in EXTENSIONES_AUDIO:
                continue
            tid = self._id_pista_desde_ruta(ruta)
            if tid in self.biblioteca:
                continue
            meta = self._extraer_metadatos(ruta)
            self.biblioteca[tid] = meta
            importadas += 1
        if importadas:
            self._guardar_datos()

    def _id_pista_desde_ruta(self, ruta):
        return hashlib.md5(str(ruta.resolve()).encode("utf-8")).hexdigest()

    def _extraer_metadatos(self, ruta, sobreescrituras=None):
        ruta = Path(ruta)
        sobreescrituras = sobreescrituras or {}
        titulo = ruta.stem
        artista = "Desconocido"
        album = "Desconocido"
        genero = "Desconocido"
        duracion = 0.0
        ruta_portada = ""

        try:
            audio = ArchivoMutagen(ruta, easy=True)
            if audio:
                titulo = (audio.get("title") or [titulo])[0]
                artista = (audio.get("artist") or [artista])[0]
                album = (audio.get("album") or [album])[0]
                genero = (audio.get("genre") or [genero])[0]
            mp3 = MP3(ruta)
            duracion = float(mp3.info.length)
            tags = getattr(mp3, "tags", None)
            if tags:
                for clave in tags.keys():
                    if clave.startswith("APIC"):
                        datos_img = tags[clave].data
                        nombre_portada = f"{self._id_pista_desde_ruta(ruta)}.jpg"
                        destino_portada = DIRECTORIO_CACHE_PORTADAS / nombre_portada
                        if not destino_portada.exists():
                            destino_portada.write_bytes(datos_img)
                        ruta_portada = str(destino_portada)
                        break
        except Exception:
            pass

        titulo = sobreescrituras.get("title", titulo)
        artista = sobreescrituras.get("artist", artista)
        album = sobreescrituras.get("album", album)
        genero = sobreescrituras.get("genre", genero)
        ruta_portada = sobreescrituras.get("cover_path", ruta_portada)
        origen = sobreescrituras.get("source", "local")

        return {
            "id": self._id_pista_desde_ruta(ruta),
            "path": str(ruta),
            "title": str(titulo).strip() or ruta.stem,
            "artist": str(artista).strip() or "Desconocido",
            "album": str(album).strip() or "Desconocido",
            "genre": str(genero).strip() or "Desconocido",
            "duration": duracion,
            "cover_path": ruta_portada,
            "source": origen,
        }

    def _refrescar_todas_las_vistas(self):
        self._refrescar_listbox_playlists()
        self._refrescar_listas_carpeta()
        self._aplicar_filtro()

    def _refrescar_listbox_playlists(self):
        actual = self._obtener_nombre_playlist_seleccionada()
        self.listbox_playlists.delete(0, "end")
        for nombre in sorted(self.playlists.keys(), key=str.lower):
            self.listbox_playlists.insert("end", nombre)
        if actual and actual in self.playlists:
            idx = sorted(self.playlists.keys(), key=str.lower).index(actual)
            self.listbox_playlists.selection_clear(0, "end")
            self.listbox_playlists.selection_set(idx)
        self._refrescar_canciones_playlist()

    def _obtener_nombre_playlist_seleccionada(self):
        seleccion = self.listbox_playlists.curselection()
        if not seleccion:
            return ""
        return self.listbox_playlists.get(seleccion[0])

    def _al_seleccionar_playlist(self):
        self.nombre_playlist_actual = self._obtener_nombre_playlist_seleccionada()
        self._refrescar_canciones_playlist()
        if self.nombre_playlist_actual:
            self._set_estado(f"Playlist: {self.nombre_playlist_actual}", COLORES["ok"])

    def _refrescar_canciones_playlist(self):
        if not hasattr(self, "listbox_canciones_playlist"):
            return
        self._lista_canciones_playlist = []
        self.listbox_canciones_playlist.delete(0, "end")
        nombre = self._obtener_nombre_playlist_seleccionada()
        if not nombre or nombre not in self.playlists:
            return
        ids = self.playlists[nombre]
        pistas = [self.biblioteca[tid] for tid in ids if tid in self.biblioteca]
        self._lista_canciones_playlist = pistas
        for t in pistas:
            dur = self._formatear_tiempo(t.get("duration", 0))
            self.listbox_canciones_playlist.insert("end", f"{t.get('title', '?')}  [{dur}]")

    def _reproducir_cancion_playlist_seleccionada(self):
        sel = self.listbox_canciones_playlist.curselection()
        if not sel:
            return
        pista = self._lista_canciones_playlist[sel[0]]
        self.pistas_vista = self._lista_canciones_playlist
        self._reproducir_pista(pista)

    def _previsualizar_cancion_playlist_seleccionada(self):
        sel = self.listbox_canciones_playlist.curselection()
        if not sel:
            return
        pista = self._lista_canciones_playlist[sel[0]]
        self._mostrar_info_pista(pista)

    # Gestión de playlists
    # Crear, borrar y agregar canciones a playlists. Las acciones piden
    # confirmación o nombre mediante diálogos simples de Tkinter.

    def _crear_playlist(self):
        nombre = simpledialog.askstring("Nueva playlist", "Nombre de la playlist:")
        if not nombre:
            return
        nombre = nombre.strip()
        if not nombre:
            return
        if nombre in self.playlists:
            messagebox.showwarning("Playlist", "Esa playlist ya existe.")
            return
        self.playlists[nombre] = []
        self._guardar_datos()
        self._refrescar_listbox_playlists()
        self._set_estado(f"Playlist creada: {nombre}", COLORES["ok"])

    def _borrar_playlist(self):
        nombre = self._obtener_nombre_playlist_seleccionada()
        if not nombre:
            messagebox.showinfo("Playlist", "Selecciona una playlist para borrar.")
            return
        if not messagebox.askyesno("Confirmar", f"Borrar playlist '{nombre}'?"):
            return
        self.playlists.pop(nombre, None)
        self.nombre_playlist_actual = ""
        self._guardar_datos()
        self._refrescar_todas_las_vistas()
        self._set_estado("Playlist eliminada.", COLORES["ok"])

    def _agregar_seleccionado_a_playlist(self):
        pista_sel = self._obtener_pista_seleccionada_de_tabla()
        if not pista_sel:
            messagebox.showinfo("Playlist", "Selecciona una canción en la tabla.")
            return
        opciones = sorted(self.playlists.keys(), key=str.lower)
        if not opciones:
            messagebox.showinfo("Playlist", "Crea una playlist primero.")
            return
        nombre = simpledialog.askstring(
            "Agregar a playlist",
            f"Playlists disponibles: {', '.join(opciones)}\nEscribí el nombre exacto:"
        )
        if not nombre:
            return
        nombre = nombre.strip()
        if nombre not in self.playlists:
            messagebox.showwarning("Playlist", "La playlist no existe.")
            return
        if pista_sel["id"] not in self.playlists[nombre]:
            self.playlists[nombre].append(pista_sel["id"])
            self._guardar_datos()
        self._set_estado(f"'{pista_sel['title']}' agregada a '{nombre}'.", COLORES["ok"])

    # Importación de carpeta
    # Permite al usuario elegir una carpeta del sistema y la escanea en un hilo
    # separado para no bloquear la UI mientras se procesan los archivos.

    def _importar_carpeta(self):
        carpeta = filedialog.askdirectory(title="Selecciona carpeta con música")
        if not carpeta:
            return
        self._set_estado("Importando carpeta...", COLORES["acento"])
        threading.Thread(target=self._worker_importar_carpeta, args=(carpeta,), daemon=True).start()

    def _worker_importar_carpeta(self, carpeta):
        importadas = 0
        for ruta in Path(carpeta).rglob("*"):
            if ruta.suffix.lower() not in EXTENSIONES_AUDIO:
                continue
            tid = self._id_pista_desde_ruta(ruta)
            if tid in self.biblioteca:
                continue
            pista = self._extraer_metadatos(ruta)
            self.biblioteca[tid] = pista
            importadas += 1
        self._guardar_datos()
        self.cola_ui.put(("importacion_lista", importadas))

    # Filtro y renderizado de la tabla de biblioteca
    # Filtra las pistas de la biblioteca según el panel activo (carpeta,
    # playlist, canciones), aplica la búsqueda y el orden, y redibuja la tabla.

    def _aplicar_filtro(self):
        consulta = ""
        campo = self.var_campo_busqueda.get()
        playlist_sel = self.nombre_playlist_actual
        pistas = list(self.biblioteca.values())

        if self.panel_izq_activo == "carpeta":
            sel = self.listbox_carpetas.curselection() if hasattr(self, "listbox_carpetas") else ()
            if sel:
                carpeta_sel = self.listbox_carpetas.get(sel[0])
                pistas = [t for t in pistas if str(Path(t.get("path", "")).parent) == carpeta_sel]
            else:
                pistas = []

        if self.panel_izq_activo == "playlist" and playlist_sel and playlist_sel in self.playlists:
            ids = set(self.playlists[playlist_sel])
            pistas = [t for t in pistas if t["id"] in ids]

        if consulta:
            if campo == "Cancion":
                pistas = [t for t in pistas if consulta in t.get("title", "").lower()]
            elif campo == "Artista":
                pistas = [t for t in pistas if consulta in t.get("artist", "").lower()]
            elif campo == "Album":
                pistas = [t for t in pistas if consulta in t.get("album", "").lower()]
            elif campo == "Genero":
                pistas = [t for t in pistas if consulta in t.get("genre", "").lower()]
            elif campo == "Playlist":
                matching = [n for n in self.playlists if consulta in n.lower()]
                ids = set()
                for n in matching:
                    ids.update(self.playlists.get(n, []))
                pistas = [t for t in pistas if t["id"] in ids]

        clave_orden = self.var_orden.get()
        if clave_orden == "Cancion":
            pistas.sort(key=lambda t: t.get("title", "").lower())
        elif clave_orden == "Artista":
            pistas.sort(key=lambda t: t.get("artist", "").lower())
        elif clave_orden == "Album":
            pistas.sort(key=lambda t: t.get("album", "").lower())
        elif clave_orden == "Genero":
            pistas.sort(key=lambda t: t.get("genre", "").lower())
        elif clave_orden == "Duracion":
            pistas.sort(key=lambda t: float(t.get("duration", 0)))

        self.pistas_vista = pistas
        self._renderizar_tabla_biblioteca()

    def _renderizar_tabla_biblioteca(self):
        id_sel_actual = self._obtener_id_pista_seleccionada()
        self.tabla.delete(*self.tabla.get_children())
        for pista in self.pistas_vista:
            imagen = ""
            if self.panel_izq_activo == "playlist":
                portada = pista.get("cover_path", "")
                if portada:
                    try:
                        imagen = self._cargar_imagen(portada, (30, 30))
                    except Exception:
                        imagen = ""
            self.tabla.insert(
                "", "end",
                iid=pista["id"],
                text=pista.get("title", ""),
                image=imagen,
                values=(
                    pista.get("artist", ""),
                    pista.get("album", ""),
                    pista.get("genre", ""),
                    self._formatear_tiempo(pista.get("duration", 0)),
                ),
            )
        if id_sel_actual and self.tabla.exists(id_sel_actual):
            self.tabla.selection_set(id_sel_actual)
            self.tabla.focus(id_sel_actual)

    def _obtener_id_pista_seleccionada(self):
        sel = self.tabla.selection()
        return sel[0] if sel else ""

    def _obtener_pista_seleccionada_de_tabla(self):
        tid = self._obtener_id_pista_seleccionada()
        return self.biblioteca.get(tid)

    def _previsualizar_seleccion_biblioteca(self):
        pista = self._obtener_pista_seleccionada_de_tabla()
        if pista:
            self._mostrar_info_pista(pista)

    # Mostrar información de una pista
    # Actualiza el panel derecho (portada grande, título, artista) y la tarjeta
    # "Reproduciendo ahora" con los datos de la pista indicada.

    def _mostrar_info_pista(self, pista):
        titulo = pista.get("title", "Sin título")
        artista = pista.get("artist", "Desconocido")
        album = pista.get("album", "Desconocido")
        fuente_portada = pista.get("cover_path", "")

        self.etiq_titulo_pista.config(text=titulo)
        self.etiq_artista_pista.config(text=f"{artista}  ·  {album}")
        self._set_tarjeta_ahora_pista(titulo, artista, fuente_portada)
        self.etiq_titulo_preview.config(text=titulo)
        self.etiq_artista_preview.config(text=f"{artista}  ·  {album}")

        if fuente_portada:
            try:
                img = self._cargar_imagen(fuente_portada, (220, 220))
                self.etiq_portada.config(image=img)
                self.etiq_portada.image = img
            except Exception:
                self._set_portada_grande_placeholder()
        else:
            self._set_portada_grande_placeholder()

    def _reproducir_pista_seleccionada(self):
        pista = self._obtener_pista_seleccionada_de_tabla()
        if not pista:
            messagebox.showinfo("Reproducción", "Selecciona una canción primero.")
            return
        self._reproducir_pista(pista)

    # Reproducción de audio
    # Carga el archivo MP3 en pygame.mixer y actualiza todo el estado interno
    # (índice, portada, duración, botón Play/Pausa, etc.).

    def _reproducir_pista(self, pista):
        ruta = pista.get("path", "")
        if not ruta or not Path(ruta).exists():
            messagebox.showerror("Archivo", "No se encontró el archivo de audio.")
            return
        if not self.audio_ok:
            messagebox.showerror("Audio", "No se pudo inicializar el audio.")
            return

        pygame.mixer.music.load(ruta)
        pygame.mixer.music.play()
        pygame.mixer.music.set_volume(self.perilla_volumen.get() / 100)

        self.id_pista_actual = pista["id"]
        self.ruta_audio_actual = ruta
        self.duracion_actual = float(pista.get("duration", 0))
        self._inicio_reproduccion = time.time()
        self._segundos_en_pausa = 0.0
        self.reproduciendo = True
        self.en_pausa = False

        self.indice_actual = -1
        for idx, item in enumerate(self.pistas_vista):
            if item["id"] == pista["id"]:
                self.indice_actual = idx
                break

        self.progreso.set(0)
        self.etiq_tiempo_actual.config(text="00:00")
        self.etiq_tiempo_total.config(text=self._formatear_tiempo(self.duracion_actual))
        self._mostrar_info_pista(pista)
        self._set_estado(f"Reproduciendo: {pista.get('title', '')}", COLORES["ok"])
        self.btn_play._texto = "Pausa"
        self.btn_play._icono = "⏸"
        self.btn_play._dibujar(self.btn_play._color_fondo)

    # Toggle de reproducción / pausa
    # Botón principal Play/Pausa: si hay algo sonando lo pausa, si está pausado
    # lo reanuda, y si no hay nada seleccionado arranca la primera pista.

    def _toggle_reproduccion(self):
        if self.reproduciendo and not self.en_pausa:
            self._toggle_pausa()
            return
        if self.reproduciendo and self.en_pausa:
            self._toggle_pausa()
            return
        seleccionada = self._obtener_pista_seleccionada_de_tabla()
        if seleccionada:
            self._reproducir_pista(seleccionada)
            return
        if self.pistas_vista:
            self._reproducir_pista(self.pistas_vista[0])

    def _toggle_pausa(self):
        if not self.audio_ok or not self.reproduciendo:
            return
        if self.en_pausa:
            pygame.mixer.music.unpause()
            self._inicio_reproduccion = time.time()
            self.en_pausa = False
            self._set_estado("Reproducción reanudada.", COLORES["ok"])
            self.btn_play._texto = "Pausa"
            self.btn_play._icono = "⏸"
            self.btn_play._dibujar(self.btn_play._color_fondo)
        else:
            self._segundos_en_pausa += time.time() - self._inicio_reproduccion
            pygame.mixer.music.pause()
            self.en_pausa = True
            self._set_estado("Pausado.")
            self.btn_play._texto = "Play"
            self.btn_play._icono = "▶"
            self.btn_play._dibujar(self.btn_play._color_fondo)

    def _detener_cancion(self):
        if self.audio_ok:
            pygame.mixer.music.stop()
        self.reproduciendo = False
        self.en_pausa = False
        self._segundos_en_pausa = 0.0
        self.progreso.set(0)
        self.etiq_tiempo_actual.config(text="00:00")
        self.btn_play._texto = "Play"
        self.btn_play._icono = "▶"
        self.btn_play._dibujar(self.btn_play._color_fondo)
        self._set_estado("Detenido.")

    # Shuffle y Loop
    # Activan/desactivan reproducción aleatoria y en bucle. El botón activo
    # se resalta en dorado para indicar el estado actual.

    def _toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.btn_shuffle._color_fondo = COLORES["acento"] if self.shuffle else COLORES["chip"]
        self.btn_shuffle._color_texto = "white" if self.shuffle else COLORES["texto"]
        self.btn_shuffle._dibujar(self.btn_shuffle._color_fondo)
        self._set_estado("Shuffle activado." if self.shuffle else "Shuffle desactivado.")

    def _toggle_loop(self):
        self.loop = not self.loop
        self.btn_loop._color_fondo = COLORES["acento"] if self.loop else COLORES["chip"]
        self.btn_loop._color_texto = "white" if self.loop else COLORES["texto"]
        self.btn_loop._dibujar(self.btn_loop._color_fondo)
        self._set_estado("Loop activado." if self.loop else "Loop desactivado.")

    # Navegación entre canciones
    # Pasa a la siguiente o anterior pista de la lista visible. Si shuffle está
    # activo, elige una pista aleatoria.

    def _siguiente_cancion(self):
        if not self.pistas_vista:
            return
        if self.shuffle:
            idx = random.randrange(len(self.pistas_vista))
        else:
            idx = 0 if self.indice_actual < 0 else (self.indice_actual + 1) % len(self.pistas_vista)
        self.indice_actual = idx
        pista = self.pistas_vista[idx]
        if self.tabla.exists(pista["id"]):
            self.tabla.selection_set(pista["id"])
            self.tabla.focus(pista["id"])
        self._reproducir_pista(pista)

    def _cancion_anterior(self):
        if not self.pistas_vista:
            return
        idx = len(self.pistas_vista) - 1 if self.indice_actual <= 0 else self.indice_actual - 1
        self.indice_actual = idx
        pista = self.pistas_vista[idx]
        if self.tabla.exists(pista["id"]):
            self.tabla.selection_set(pista["id"])
            self.tabla.focus(pista["id"])
        self._reproducir_pista(pista)

    # Salto de posición en el audio
    # Cuando el usuario arrastra la barra de progreso, recarga el archivo y
    # empieza a reproducir desde el segundo indicado.

    def _saltar_audio(self, porcentaje):
        if not self.reproduciendo or not self.ruta_audio_actual or self.duracion_actual <= 0:
            return
        destino = (porcentaje / 100) * self.duracion_actual
        pygame.mixer.music.load(self.ruta_audio_actual)
        pygame.mixer.music.play(start=destino)
        pygame.mixer.music.set_volume(self.perilla_volumen.get() / 100)
        self._segundos_en_pausa = destino
        self._inicio_reproduccion = time.time()
        self.en_pausa = False
        self.btn_play._texto = "Pausa"
        self.btn_play._icono = "⏸"
        self.btn_play._dibujar(self.btn_play._color_fondo)

    def _segundos_actuales(self):
        if not self.reproduciendo:
            return self._segundos_en_pausa
        if self.en_pausa:
            return self._segundos_en_pausa
        return min(self._segundos_en_pausa + (time.time() - self._inicio_reproduccion), self.duracion_actual)

    # Timers periódicos
    # _actualizar_progreso: actualiza la barra y el tiempo cada 250ms.
    # _verificar_fin: detecta cuando pygame terminó la pista y avanza (o hace
    # loop) cada 500ms.

    def _actualizar_progreso(self):
        if self.reproduciendo and not self.en_pausa:
            seg = self._segundos_actuales()
            self.etiq_tiempo_actual.config(text=self._formatear_tiempo(seg))
            if self.duracion_actual > 0:
                self.progreso.set((seg / self.duracion_actual) * 100)
        self.raiz.after(250, self._actualizar_progreso)

    def _verificar_fin(self):
        if self.audio_ok and self.reproduciendo and not self.en_pausa and not pygame.mixer.music.get_busy():
            self.reproduciendo = False
            if self.loop and self.id_pista_actual:
                pista = self.biblioteca.get(self.id_pista_actual)
                if pista:
                    self._reproducir_pista(pista)
            else:
                self._siguiente_cancion()
        self.raiz.after(500, self._verificar_fin)

    # Búsqueda en Spotify
    # Lanza la búsqueda en un hilo separado para no bloquear la UI. Al terminar,
    # encola el resultado para que el hilo principal actualice la tabla.

    def _buscar_spotify(self):
        consulta = self._obtener_consulta_real()
        if not consulta:
            messagebox.showwarning("Spotify", "Escribí algo para buscar en Spotify.")
            return
        self.ultima_busqueda_spotify = consulta
        self.btn_spotify.config(state="disabled")
        self._set_estado("Buscando en Spotify...", COLORES["acento"])
        threading.Thread(target=self._worker_busqueda_spotify, args=(consulta,), daemon=True).start()

    def _refrescar_spotify(self):
        if not self.ultima_busqueda_spotify:
            return
        self.entrada_spotify.delete(0, "end")
        self.entrada_spotify.insert(0, self.ultima_busqueda_spotify)
        self._buscar_spotify()

    def _worker_busqueda_spotify(self, consulta):
        try:
            resultados = self.spotify.buscar_cancion(consulta, limite=10)
            self.cola_ui.put(("spotify_ok", resultados, consulta))
        except Exception as exc:
            self.cola_ui.put(("spotify_err", str(exc)))

    def _renderizar_resultados_spotify(self):
        self.tabla_spotify.delete(*self.tabla_spotify.get_children())
        self.mapa_resultados_spotify = {}
        for idx, pista in enumerate(self.resultados_spotify, start=1):
            iid = f"sp_{idx:03d}"
            fuente_portada = pista.get("cover_url", "")
            try:
                imagen = self._cargar_imagen(fuente_portada, (36, 36))
            except Exception:
                imagen = self._cargar_imagen("", (36, 36))

            self.tabla_spotify.insert(
                "", "end",
                iid=iid,
                text=pista.get("title", "Desconocido"),
                image=imagen,
                values=(pista.get("artist", "Desconocido"),),
            )
            self.mapa_resultados_spotify[iid] = pista

    def _obtener_pista_spotify_seleccionada(self):
        seleccion = self.tabla_spotify.selection()
        if not seleccion:
            return None
        return self.mapa_resultados_spotify.get(seleccion[0])

    # Selección en tabla Spotify → descarga y reproducción
    # Al seleccionar una pista de Spotify, decide qué hacer según el panel
    # activo: agregar a playlist, guardar en carpeta, o simplemente descargar
    # y reproducir. Todo se ejecuta en hilos separados.

    def _al_seleccionar_tabla_spotify(self):
        self._previsualizar_seleccion_spotify()
        pista = self._obtener_pista_spotify_seleccionada()
        if not pista:
            return
        if self.auto_play_spotify_en_curso:
            return
        self.auto_play_spotify_en_curso = True

        if self.panel_izq_activo == "playlist":
            playlist_destino = self._obtener_nombre_playlist_seleccionada()
            if playlist_destino:
                self._set_estado(f"Descargando y agregando a '{playlist_destino}'...", COLORES["acento"])
                threading.Thread(
                    target=self._worker_descarga_spotify, args=(pista, True, playlist_destino, ""), daemon=True
                ).start()
            else:
                self._set_estado("Sin playlist — reproduciendo sin guardar...", COLORES["acento"])
                threading.Thread(
                    target=self._worker_stream_spotify, args=(pista,), daemon=True
                ).start()

        elif self.panel_izq_activo == "carpeta":
            sel = self.listbox_carpetas.curselection()
            if sel:
                carpeta_destino = self.listbox_carpetas.get(sel[0])
                self._set_estado(f"Descargando en '{Path(carpeta_destino).name}'...", COLORES["acento"])
                threading.Thread(
                    target=self._worker_descarga_spotify, args=(pista, True, "", carpeta_destino), daemon=True
                ).start()
            else:
                self._set_estado("Sin carpeta — reproduciendo sin guardar...", COLORES["acento"])
                threading.Thread(
                    target=self._worker_stream_spotify, args=(pista,), daemon=True
                ).start()

        else:
            self._set_estado("Descargando y reproduciendo...", COLORES["acento"])
            threading.Thread(
                target=self._worker_descarga_spotify, args=(pista, True, "", ""), daemon=True
            ).start()

    def _previsualizar_seleccion_spotify(self):
        pista = self._obtener_pista_spotify_seleccionada()
        if not pista:
            return
        titulo = pista.get("title", "Sin título")
        artista = pista.get("artist", "Desconocido")
        album = pista.get("album", "Desconocido")
        self.etiq_titulo_pista.config(text=titulo)
        self.etiq_artista_pista.config(text=f"{artista}  ·  {album}")
        fuente_portada = pista.get("cover_url", "")
        self._set_tarjeta_ahora_pista(titulo, artista, fuente_portada)
        self.etiq_titulo_preview.config(text=titulo)
        self.etiq_artista_preview.config(text=f"{artista}  ·  {album}")
        if fuente_portada:
            try:
                img = self._cargar_imagen(fuente_portada, (220, 220))
                self.etiq_portada.config(image=img)
                self.etiq_portada.image = img
            except Exception:
                self._set_portada_grande_placeholder()
        else:
            self._set_portada_grande_placeholder()

    def _descargar_seleccion_spotify(self):
        pista = self._obtener_pista_spotify_seleccionada()
        if not pista:
            messagebox.showinfo("Spotify", "Selecciona una canción de Spotify.")
            return
        self._set_estado("Descargando desde YouTube...", COLORES["acento"])
        playlist_destino = self._obtener_nombre_playlist_seleccionada() if self.panel_izq_activo == "playlist" else ""
        threading.Thread(
            target=self._worker_descarga_spotify, args=(pista, False, playlist_destino), daemon=True
        ).start()

    # Workers de descarga Spotify
    # _worker_stream_spotify: descarga el audio pero NO lo agrega a la biblioteca.
    # _worker_descarga_spotify: descarga, guarda en biblioteca, opcionalmente
    # copia a una carpeta y/o agrega a una playlist, luego encola el resultado.

    def _worker_stream_spotify(self, pista):
        try:
            audio_local = self.descargador.asegurar_audio(pista)
            portada_local = self.descargador.asegurar_portada(pista)
            meta = self._extraer_metadatos(
                audio_local,
                sobreescrituras={
                    "title": pista.get("title", ""),
                    "artist": pista.get("artist", ""),
                    "album": pista.get("album", ""),
                    "genre": pista.get("genre", "Desconocido"),
                    "cover_path": portada_local,
                    "source": "spotify_stream_only",
                },
            )
            self.cola_ui.put(("spotify_stream_ok", meta))
        except Exception as exc:
            self.cola_ui.put(("spotify_descarga_err", str(exc)))

    def _worker_descarga_spotify(self, pista, auto_play=False, playlist_destino="", carpeta_destino=""):
        try:
            audio_local = self.descargador.asegurar_audio(pista)
            portada_local = self.descargador.asegurar_portada(pista)

            audio_final = audio_local
            if carpeta_destino:
                dir_destino = Path(carpeta_destino)
                dir_destino.mkdir(parents=True, exist_ok=True)
                archivo_dest = dir_destino / Path(audio_local).name
                if archivo_dest.resolve() != Path(audio_local).resolve():
                    shutil.copy2(audio_local, archivo_dest)
                audio_final = str(archivo_dest)

            meta = self._extraer_metadatos(
                audio_final,
                sobreescrituras={
                    "title": pista.get("title", ""),
                    "artist": pista.get("artist", ""),
                    "album": pista.get("album", ""),
                    "genre": pista.get("genre", "Desconocido"),
                    "cover_path": portada_local,
                    "source": "spotify_youtube",
                },
            )
            self.biblioteca[meta["id"]] = meta
            if playlist_destino and playlist_destino in self.playlists and meta["id"] not in self.playlists[playlist_destino]:
                self.playlists[playlist_destino].append(meta["id"])
            self._guardar_datos()
            self.cola_ui.put(("spotify_descarga_ok", meta, auto_play, playlist_destino, carpeta_destino))
        except Exception as exc:
            self.cola_ui.put(("spotify_descarga_err", str(exc)))

    # Procesador de la cola de UI
    # Lee todos los mensajes pendientes en la cola y actualiza la interfaz de
    # forma segura desde el hilo principal de Tkinter (los workers ponen
    # mensajes aquí en vez de tocar widgets directamente).

    def _procesar_cola_ui(self):
        try:
            while True:
                item = self.cola_ui.get_nowait()
                tipo = item[0]
                if tipo == "importacion_lista":
                    importadas = item[1]
                    self._refrescar_todas_las_vistas()
                    self._set_estado(f"Importación lista: {importadas} canciones nuevas.", COLORES["ok"])
                elif tipo == "spotify_ok":
                    self.resultados_spotify = item[1]
                    consulta = item[2]
                    self.btn_spotify.config(state="normal")
                    self._renderizar_resultados_spotify()
                    if self.resultados_spotify:
                        self._set_estado(f"Spotify: {len(self.resultados_spotify)} resultados para '{consulta}'.", COLORES["ok"])
                    else:
                        self._set_estado(f"Sin resultados para '{consulta}'.", COLORES["advertencia"])
                elif tipo == "spotify_err":
                    self.btn_spotify.config(state="normal")
                    msg = f"Error Spotify: {item[1]}"
                    self._set_estado(msg, COLORES["advertencia"])
                    messagebox.showerror("Error", msg)
                elif tipo == "spotify_stream_ok":
                    meta = item[1]
                    self._set_estado(f"Reproduciendo: {meta.get('title', '')}", COLORES["acento"])
                    self._reproducir_pista(meta)
                    self.auto_play_spotify_en_curso = False
                elif tipo == "spotify_descarga_ok":
                    meta = item[1]
                    auto_play = item[2] if len(item) > 2 else False
                    nombre_playlist = item[3] if len(item) > 3 else ""
                    nombre_carpeta = item[4] if len(item) > 4 else ""
                    self._refrescar_todas_las_vistas()
                    if nombre_carpeta:
                        self._set_estado(f"Guardada en '{Path(nombre_carpeta).name}': {meta.get('title', '')}", COLORES["ok"])
                        self._al_seleccionar_carpeta()
                    elif nombre_playlist:
                        self._set_estado(f"Agregada a '{nombre_playlist}': {meta.get('title', '')}", COLORES["ok"])
                        self._refrescar_canciones_playlist()
                    else:
                        self._set_estado(f"Descargada: {meta.get('title', '')}", COLORES["ok"])
                    if auto_play:
                        self._reproducir_pista(meta)
                    self.auto_play_spotify_en_curso = False
                elif tipo == "spotify_descarga_err":
                    msg = f"No se pudo descargar: {item[1]}"
                    self._set_estado(msg, COLORES["advertencia"])
                    messagebox.showerror("Error", msg)
                    self.auto_play_spotify_en_curso = False
        except queue.Empty:
            pass
        self.raiz.after(150, self._procesar_cola_ui)

    # Utilidad: formatear segundos como MM:SS
    @staticmethod
    def _formatear_tiempo(segundos):
        total = max(int(segundos), 0)
        return f"{total // 60:02d}:{total % 60:02d}"


# Punto de entrada
# Crea la ventana raíz de Tkinter, instancia el Reproductor y arranca el loop
# principal de eventos de la interfaz gráfica.

if __name__ == "__main__":
    raiz = tk.Tk()
    app = Reproductor(raiz)
    raiz.mainloop()