import os
import sys
import random
import tkinter as tk
from tkinter import ttk, messagebox
import pygame
import time
from mutagen.mp3 import MP3

CARPETA = "musica"


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


class Reproductor:
    def __init__(self, root):
        self.root = root
        self.root.title("Reproductor Simple")
        self.root.geometry("520x380")
        self.root.resizable(False, False)
        self.root.configure(bg='black')

        self.audio_ok = init_audio()
        self.songs = []
        self.index = 0
        self.loop = False
        self.shuffle = False
        self.playing = False
        self.paused = False
        self.current_song = None

        # NUEVO (tiempo)
        self.duration = 0
        self.start_time = 0
        self.pause_time = 0

        self.title_label = tk.Label(root, text="Sin canciones", font=("Arial", 14), bg='black', fg='white')
        self.title_label.pack(pady=10)

        self.status_label = tk.Label(root, text="", font=("Arial", 10), fg="gray", bg='black')
        self.status_label.pack(pady=2)

        self.listbox = tk.Listbox(root, height=6, font=("Arial", 11), bg='black', fg='white', selectbackground='gray')
        self.listbox.pack(fill="x", padx=15)

        # 🔥 BARRA DE PROGRESO
        self.progress = ttk.Scale(root, from_=0, to=100, orient="horizontal", length=400)
        self.progress.pack(pady=5)

        self.time_label = tk.Label(root, text="00:00 / 00:00", font=("Arial", 10), bg='black', fg='white')
        self.time_label.pack()

        self.load_songs()

        controles = tk.Frame(root, bg='black')
        controles.pack(pady=12)

        tk.Button(controles, text="⏮", width=4, command=self.prev_song, bg='gray', fg='white').pack(side="left", padx=4)
        
        # Botón único con imagen dinámica
        try:
            self.play_image = tk.PhotoImage(file="imagenes/1.png")
            self.pause_image = tk.PhotoImage(file="imagenes/2.png")
            self.toggle_btn = tk.Button(controles,
                                       image=self.play_image,
                                       command=self.toggle_play,
                                       bg='black',
                                       activebackground='black',
                                       relief='flat',
                                       borderwidth=0,
                                       highlightthickness=0)
            self.toggle_btn.pack(side="left", padx=4)
        except Exception as e:
            print("No se pudo cargar imágenes:", e)
            self.toggle_btn = tk.Button(controles,
                                        text="▶/⏸",
                                        width=5,
                                        command=self.toggle_play,
                                        bg='gray',
                                        fg='white',
                                        activebackground='gray',
                                        relief='flat',
                                        borderwidth=0,
                                        highlightthickness=0)
            self.toggle_btn.pack(side="left", padx=4)
        
        tk.Button(controles, text="⏹", width=4, command=self.stop_song, bg='gray', fg='white').pack(side="left", padx=4)
        tk.Button(controles, text="⏭", width=4, command=self.next_song, bg='gray', fg='white').pack(side="left", padx=4)

        options = tk.Frame(root, bg='black')
        options.pack(pady=6)

        tk.Button(options, text="Shuffle", width=8, command=self.toggle_shuffle, bg='gray', fg='white').pack(side="left", padx=6)
        tk.Button(options, text="Loop", width=8, command=self.toggle_loop, bg='gray', fg='white').pack(side="left", padx=6)

        self.volume = tk.Scale(root, from_=0, to=1, resolution=0.1, orient="horizontal",
                               label="Volumen", command=self.set_volume, bg='black', fg='white', troughcolor='gray')
        self.volume.set(0.7)
        self.volume.pack(fill="x", padx=15, pady=8)

        if self.audio_ok:
            pygame.mixer.music.set_volume(0.7)
        else:
            messagebox.showwarning("Audio", "No se pudo inicializar el audio.")

        self.root.after(500, self.check_end)
        self.update_progress()

    def load_songs(self):
        if not os.path.exists(CARPETA):
            os.makedirs(CARPETA)

        self.songs = [
            os.path.join(CARPETA, f)
            for f in sorted(os.listdir(CARPETA))
            if f.lower().endswith(".mp3")
        ]

        self.listbox.delete(0, "end")

        for song in self.songs:
            self.listbox.insert("end", os.path.basename(song))

        if self.songs:
            self.index = 0
            self.title_label.config(text=os.path.basename(self.songs[0]))
            self.status_label.config(text=f"{len(self.songs)} canciones cargadas")
        else:
            self.status_label.config(text="Pon mp3 en carpeta 'musica'")

    def play_song(self, use_selection=True):
        if not self.songs:
            return

        if not self.audio_ok:
            self.audio_ok = init_audio()
            if not self.audio_ok:
                return

        if use_selection:
            selection = self.listbox.curselection()
            if selection:
                self.index = selection[0]

        song = self.songs[self.index]

        try:
            pygame.mixer.music.load(song)
            loops = -1 if self.loop else 0
            pygame.mixer.music.play(loops=loops)
            pygame.mixer.music.set_volume(self.volume.get())

            self.playing = True
            self.paused = False
            self.current_song = song

            # 🔥 DURACIÓN REAL
            audio = MP3(song)
            self.duration = int(audio.info.length)

            self.start_time = time.time()
            self.pause_time = 0

            self.title_label.config(text=os.path.basename(song))
            self.status_label.config(text="Reproduciendo")

            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(self.index)
            
            self.update_button_image()

        except Exception as e:
            print("Error:", e)

    def update_button_image(self):
        """Actualiza la imagen del botón según el estado"""
        if hasattr(self, 'toggle_btn') and hasattr(self, 'play_image') and hasattr(self, 'pause_image'):
            if self.playing and not self.paused:
                self.toggle_btn.config(image=self.pause_image)
            else:
                self.toggle_btn.config(image=self.play_image)

    def toggle_play(self):
        """Alterna entre play y pausa"""
        if not self.songs:
            return
        
        if self.playing:
            # Si está reproduciendo, pausar
            self.toggle_pause()
        else:
            # Si está pausado o detenido, reproducir
            self.play_song()

    def toggle_pause(self):
        if not self.audio_ok or not self.playing:
            return

        if self.paused:
            pygame.mixer.music.unpause()
            self.start_time = time.time() - self.pause_time
            self.paused = False
        else:
            pygame.mixer.music.pause()
            self.pause_time = time.time() - self.start_time
            self.paused = True
        
        self.update_button_image()

    def stop_song(self):
        if not self.audio_ok:
            return
        pygame.mixer.music.stop()
        self.playing = False
        self.paused = False
        self.update_button_image()
        self.progress.set(0)

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

    def format_time(self, s):
        return f"{int(s//60):02d}:{int(s%60):02d}"

    def update_progress(self):
        if self.playing and not self.paused:
            current = time.time() - self.start_time

            if self.duration > 0:
                percent = (current / self.duration) * 100
                self.progress.set(percent)

                self.time_label.config(
                    text=f"{self.format_time(current)} / {self.format_time(self.duration)}"
                )

        self.root.after(1000, self.update_progress)

    def check_end(self):
        if self.audio_ok and self.playing and not self.paused and not pygame.mixer.music.get_busy():
            if not self.loop:
                self.next_song()
        self.root.after(500, self.check_end)


root = tk.Tk()
app = Reproductor(root)
root.mainloop()