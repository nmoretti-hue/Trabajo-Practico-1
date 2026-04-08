"""Un reproductor de música utilizando Tkinter. Vas a tener que usar otra librería para cargar y reproducir los archivos de audio. Tiene que contar con los siguientes requisitos mínimos:
Controles básicos (Play, Pausa, Stop, Siguiente, Anterior, Volumen).
Creación de listas de reproducción (playlists).
La posibilidad de agregar música desde una carpeta y de buscar/ordenar por canción, artista, álbum, género musical o playlists.
Leer los metadatos de los archivos (Artista, Álbum) utilizando una librería externa y mostrar el nombre de la canción, el artista y la carátula del disco en la interfaz.
Implementar una barra de progreso funcional que avance con la canción y muestre el tiempo.
Modos de reproducción "Aleatorio" (Shuffle) y "Repetir" (Loop).
    Se recomienda el uso de JSON para guardar la información, o incluso la implementación de una base de datos simple con SQLite para quien se anime. Si se te ocurre alguna más, va a ser más que bienvenida.
"""
import os
import tkinter as tk
from tkinter import ttk
import pygame
from mutagen import File
import random
import json
import time

CARPETA = "musica"

pygame.mixer.init()

class Reproductor:
    def __init__(self, root):
        self.root = root
        self.root.title("Reproductor Simple")

        self.lista = []
        self.indice = 0
        self.loop = False
        self.shuffle = False
        self.duracion = 0

        self.cargar_musica()

        self.label = tk.Label(root, text="Sin canción")
        self.label.pack()

        self.barra = ttk.Scale(root, from_=0, to=100, orient="horizontal")
        self.barra.pack(fill="x")

        controles = tk.Frame(root)
        controles.pack()

        tk.Button(controles, text="⏮", command=self.anterior).pack(side="left")
        tk.Button(controles, text="▶", command=self.play).pack(side="left")
        tk.Button(controles, text="⏸", command=self.pausar).pack(side="left")
        tk.Button(controles, text="⏹", command=self.stop).pack(side="left")
        tk.Button(controles, text="⏭", command=self.siguiente).pack(side="left")

        tk.Button(root, text="Shuffle", command=self.toggle_shuffle).pack()
        tk.Button(root, text="Loop", command=self.toggle_loop).pack()

        self.volumen = tk.Scale(root, from_=0, to=1, resolution=0.1,
                                orient="horizontal", label="Volumen",
                                command=self.cambiar_volumen)
        self.volumen.set(0.5)
        self.volumen.pack()

        self.actualizar_barra()

    def cargar_musica(self):
        if not os.path.exists(CARPETA):
            os.makedirs(CARPETA)

        self.lista = []

        for archivo in os.listdir(CARPETA):
            if archivo.endswith(".mp3"):
                ruta = os.path.join(CARPETA, archivo)
                self.lista.append(ruta)

        with open("playlist.json", "w") as f:
            json.dump(self.lista, f)

    def obtener_info(self, ruta):
        try:
            audio = File(ruta)
            titulo = audio.tags.get("TIT2", ["Desconocido"])[0]
            artista = audio.tags.get("TPE1", ["Desconocido"])[0]
            duracion = int(audio.info.length)
            return titulo, artista, duracion
        except:
            return os.path.basename(ruta), "", 0

    def play(self):
        if not self.lista:
            self.label.config(text="No hay música en la carpeta")
            return

        ruta = self.lista[self.indice]
        pygame.mixer.music.load(ruta)
        pygame.mixer.music.play()

        titulo, artista, self.duracion = self.obtener_info(ruta)
        self.label.config(text=f"{titulo} - {artista}")

    def pausar(self):
        pygame.mixer.music.pause()

    def stop(self):
        pygame.mixer.music.stop()
        self.barra.set(0)

    def siguiente(self):
        if self.shuffle:
            self.indice = random.randint(0, len(self.lista)-1)
        else:
            self.indice = (self.indice + 1) % len(self.lista)
        self.play()

    def anterior(self):
        self.indice = (self.indice - 1) % len(self.lista)
        self.play()

    def cambiar_volumen(self, val):
        pygame.mixer.music.set_volume(float(val))

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle

    def toggle_loop(self):
        self.loop = not self.loop

    def actualizar_barra(self):
        if pygame.mixer.music.get_busy():
            pos = pygame.mixer.music.get_pos() // 1000
            if self.duracion > 0:
                progreso = (pos / self.duracion) * 100
                self.barra.set(progreso)

            if pos >= self.duracion - 1:
                if self.loop:
                    self.play()
                else:
                    self.siguiente()

        self.root.after(1000, self.actualizar_barra)


root = tk.Tk()
app = Reproductor(root)
root.mainloop()