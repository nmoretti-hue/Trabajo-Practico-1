import requests
import json
import base64

class SpotifyBuscar:
    """Búsqueda de canciones en Spotify con autenticación"""
    
    def __init__(self, client_id=None, client_secret=None):
        self.base_url = "https://api.spotify.com/v1"
        self.auth_url = "https://accounts.spotify.com/api/token"
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        
        # Si se proporcionan credenciales, obtener token
        if client_id and client_secret:
            self.token = self.obtener_token_acceso(client_id, client_secret)
    
    def obtener_token_acceso(self, client_id, client_secret):
        """
        Obtiene token de acceso para la API de Spotify
        
        Args:
            client_id (str): Client ID de Spotify Developer
            client_secret (str): Client Secret de Spotify Developer
            
        Returns:
            str: Token de acceso
        """
        try:
            # Codificar credenciales en Base64
            credentials = base64.b64encode(
                f"{client_id}:{client_secret}".encode()
            ).decode()
            
            headers = {
                'Authorization': f'Basic {credentials}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            data = {'grant_type': 'client_credentials'}
            
            response = requests.post(self.auth_url, headers=headers, data=data, timeout=5)
            
            if response.status_code == 200:
                token = response.json().get('access_token')
                print(f"✓ Token de Spotify obtenido correctamente")
                return token
            else:
                print(f"✗ Error obteniendo token: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"✗ Error en autenticación: {e}")
            return None
    
    def buscar_cancion(self, query, limite=10):
        """
        Busca canciones en Spotify
        
        Args:
            query (str): Término de búsqueda (artista, canción, etc)
            limite (int): Número máximo de resultados
            
        Returns:
            list: Lista de canciones encontradas
        """
        if not self.token:
            print("✗ Sin token de autenticación. Configurar credenciales de Spotify.")
            return []
        
        try:
            headers = {
                'Authorization': f'Bearer {self.token}'
            }
            
            params = {
                'q': query,
                'type': 'track',
                'limit': limite
            }
            
            response = requests.get(
                f"{self.base_url}/search",
                headers=headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                datos = response.json()
                return self._formato_resultados(datos)
            else:
                print(f"✗ Error en búsqueda: {response.status_code}")
                if response.status_code == 401:
                    print("✗ Token inválido. Reintentando autenticación...")
                    self.token = self.obtener_token_acceso(self.client_id, self.client_secret)
                return []
                
        except Exception as e:
            print(f"✗ Error en búsqueda: {e}")
            return []
    
    def _formato_resultados(self, datos):
        """Formatea los resultados de la búsqueda"""
        resultados = []
        
        if isinstance(datos, dict) and 'tracks' in datos:
            for track in datos.get('tracks', {}).get('items', []):
                resultado = {
                    'nombre': track.get('name', 'Desconocido'),
                    'artista': ', '.join([a.get('name', '') for a in track.get('artists', [])]),
                    'url': track.get('external_urls', {}).get('spotify', ''),
                    'id': track.get('id', ''),
                    'preview': track.get('preview_url', ''),
                    'imagen': track.get('album', {}).get('images', [{}])[0].get('url', '') if track.get('album', {}).get('images') else ''
                }
                resultados.append(resultado)
        
        return resultados
    
    def obtener_artista(self, artist_id):
        """Obtiene información de un artista"""
        if not self.token:
            return None
        
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            response = requests.get(
                f"{self.base_url}/artists/{artist_id}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"✗ Error obteniendo artista: {e}")
            return None
    
    def obtener_album(self, album_id):
        """Obtiene información de un álbum"""
        if not self.token:
            return None
        
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            response = requests.get(
                f"{self.base_url}/albums/{album_id}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"✗ Error obteniendo álbum: {e}")
            return None
            )
            
            if response.status_code == 200:
                datos = response.json()
                return self._formato_resultados(datos)
            else:
                print(f"Error en búsqueda: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"Error en búsqueda con token: {e}")
            return []
