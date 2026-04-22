import base64
import os
import re

import requests


class SpotifyBuscar:
    def __init__(self, client_id=None, client_secret=None):
        self.base_url = "https://api.spotify.com/v1"
        self.auth_url = "https://accounts.spotify.com/api/token"
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None

        if client_id and client_secret:
            try:
                self.token = self.obtener_token_acceso()
            except Exception:
                self.token = None

    @classmethod
    def from_env_or_defaults(cls):
        client_id = os.environ.get("SPOTIFY_CLIENT_ID", "b55baa7b53434bf6ad0024737488a8fc")
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "54769e53ad32448e83b09a75f23b12eb")
        return cls(client_id, client_secret)

    def obtener_token_acceso(self):
        if not self.client_id or not self.client_secret:
            return None

        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode("utf-8")
        ).decode("utf-8")

        response = requests.post(
            self.auth_url,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def _do_search(self, query, limite, market):
        params = {
            "q": query,
            "type": "track",
            "limit": limite,
        }
        if market:
            params["market"] = market

        return requests.get(
            f"{self.base_url}/search",
            headers={"Authorization": f"Bearer {self.token}"},
            params=params,
            timeout=20,
        )

    def buscar_cancion(self, query, limite=10, market=None):
        query = str(query or "").strip()
        if not query:
            return []

        limite = int(limite)
        limite = min(max(limite, 1), 10)
        market = market or os.environ.get("SPOTIFY_MARKET", "AR")

        if not self.token:
            self.token = self.obtener_token_acceso()
            if not self.token:
                raise RuntimeError(
                    "No hay token de Spotify. Configura SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET."
                )

        response = self._do_search(query, limite, market)

        if response.status_code == 401:
            self.token = self.obtener_token_acceso()
            response = self._do_search(query, limite, market)

        if response.status_code == 400:
            safe_query = re.sub(r"\s+", " ", re.sub(r"[^\w\s\-\.,'&/()]", " ", query)).strip()
            if safe_query and safe_query != query:
                retry = self._do_search(safe_query, limite, market)
                if retry.status_code < 400:
                    response = retry
            if response.status_code == 400 and market:
                retry_no_market = self._do_search(query, limite, None)
                if retry_no_market.status_code < 400:
                    response = retry_no_market

        response.raise_for_status()
        return self._formatear_resultados(response.json())

    def _formatear_resultados(self, data):
        tracks = data.get("tracks", {}).get("items", [])
        results = []

        for track in tracks:
            album = track.get("album", {})
            images = album.get("images", [])
            results.append(
                {
                    "id": track.get("id", ""),
                    "nombre": track.get("name", "Desconocido"),
                    "title": track.get("name", "Desconocido"),
                    "artista": ", ".join(artist.get("name", "") for artist in track.get("artists", [])),
                    "artist": ", ".join(artist.get("name", "") for artist in track.get("artists", [])),
                    "album": album.get("name", "Sin album"),
                    "imagen": images[0].get("url", "") if images else "",
                    "cover_url": images[0].get("url", "") if images else "",
                    "url": track.get("external_urls", {}).get("spotify", ""),
                    "preview": track.get("preview_url", ""),
                    "genre": "Desconocido",
                }
            )

        return results
