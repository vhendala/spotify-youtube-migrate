"""
migrate.py — Migração de biblioteca musical do Spotify para o YouTube Music.

Dependências:
    pip install spotipy ytmusicapi

Configuração:
    - Variáveis de ambiente: SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET
    - Arquivo oauth.json do YT Music (gerado com: ytmusicapi oauth)
"""

import os
import time
import logging
from typing import Generator

from dotenv import load_dotenv

load_dotenv()  # Carrega variáveis do .env antes de qualquer acesso a os.environ

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from ytmusicapi import YTMusic

# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------

SPOTIFY_SCOPE = "user-library-read playlist-read-private playlist-read-collaborative"
SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8888/callback"
YT_OAUTH_FILE = "browser.json"
ERROR_LOG_FILE = "migracao_erros.txt"

# Pausa entre buscas no YT Music para respeitar o rate limit do Google
RATE_LIMIT_SLEEP_SECONDS = 0.5

# Tamanho máximo do lote ao adicionar faixas em uma playlist do YT Music
CHUNK_SIZE = 50

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def log_error(message: str) -> None:
    """Salva uma linha no arquivo de log de erros e também emite um WARNING."""
    logger.warning(message)
    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message + "\n")


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------

def build_spotify_client() -> spotipy.Spotify:
    """Cria e retorna um cliente Spotify autenticado via OAuth."""
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise EnvironmentError(
            "Defina as variáveis de ambiente SPOTIPY_CLIENT_ID e SPOTIPY_CLIENT_SECRET."
        )

    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope=SPOTIFY_SCOPE,
    )
    return spotipy.Spotify(auth_manager=auth)


def build_ytmusic_client() -> YTMusic:
    """Cria e retorna um cliente YT Music lendo o oauth.json local."""
    if not os.path.exists(YT_OAUTH_FILE):
        raise FileNotFoundError(
            f"Arquivo '{YT_OAUTH_FILE}' não encontrado. "
            "Execute: ytmusicapi oauth"
        )
    return YTMusic(YT_OAUTH_FILE)


# ---------------------------------------------------------------------------
# Extração de dados do Spotify (com paginação)
# ---------------------------------------------------------------------------

def fetch_saved_tracks(sp: spotipy.Spotify) -> Generator[dict, None, None]:
    """
    Gerador que produz cada faixa curtida do usuário no Spotify,
    tratando a paginação automaticamente (limite de 50 por request).
    """
    response = sp.current_user_saved_tracks(limit=50)

    while response:
        for item in response["items"]:
            yield item["track"]

        response = sp.next(response) if response["next"] else None


def fetch_user_playlists(sp: spotipy.Spotify) -> Generator[dict, None, None]:
    """Gerador que produz cada playlist do usuário no Spotify."""
    response = sp.current_user_playlists(limit=50)

    while response:
        for playlist in response["items"]:
            yield playlist

        response = sp.next(response) if response["next"] else None


def fetch_playlist_tracks(sp: spotipy.Spotify, playlist_id: str) -> Generator[dict, None, None]:
    """
    Gerador que produz cada faixa de uma playlist específica.
    Playlists curadas pelo Spotify ou privadas de terceiros retornam 403 — nesse caso
    o gerador simplesmente não emite nenhum item.
    """
    try:
        response = sp.playlist_tracks(playlist_id, limit=100)
    except spotipy.SpotifyException as e:
        # 403 é esperado para playlists curadas/privadas de outros usuários
        log_error(f"[PLAYLIST_ACESSO_NEGADO] id={playlist_id} | {e}")
        return

    while response:
        for item in response["items"]:
            # Itens locais ou removidos podem não ter track
            if item.get("track"):
                yield item["track"]

        response = sp.next(response) if response["next"] else None


# ---------------------------------------------------------------------------
# Busca no YouTube Music
# ---------------------------------------------------------------------------

def find_video_id(ytmusic: YTMusic, track_name: str, artist_name: str) -> str | None:
    """
    Busca uma música no YT Music e retorna o videoId do primeiro resultado
    do tipo 'songs'. Retorna None se nada for encontrado.
    """
    query = f"{track_name} {artist_name}"
    try:
        results = ytmusic.search(query, filter="songs", limit=5)
        if results:
            return results[0].get("videoId")
    except Exception as e:  # noqa: BLE001
        log_error(f"Erro ao buscar '{query}' no YT Music: {e}")
    return None


# ---------------------------------------------------------------------------
# Migração: Músicas Curtidas
# ---------------------------------------------------------------------------

def migrate_liked_songs(sp: spotipy.Spotify, ytmusic: YTMusic) -> None:
    """
    Busca todas as músicas curtidas no Spotify e dá LIKE nas equivalentes
    encontradas no YT Music.
    """
    logger.info("=== Iniciando migração de MÚSICAS CURTIDAS ===")
    total_ok = 0
    total_fail = 0

    for track in fetch_saved_tracks(sp):
        track_name: str = track["name"]
        artist_name: str = track["artists"][0]["name"]

        video_id = find_video_id(ytmusic, track_name, artist_name)

        if video_id:
            try:
                ytmusic.rate_song(video_id, "LIKE")
                logger.info(f"  ✔ Curtido: {track_name} — {artist_name}")
                total_ok += 1
            except Exception as e:  # noqa: BLE001
                log_error(f"[LIKE_FALHOU] {track_name} — {artist_name} | {e}")
                total_fail += 1
        else:
            log_error(f"[NAO_ENCONTRADO] {track_name} — {artist_name}")
            total_fail += 1

        time.sleep(RATE_LIMIT_SLEEP_SECONDS)

    logger.info(
        f"=== Músicas curtidas concluído: {total_ok} migradas, {total_fail} com falha ==="
    )


# ---------------------------------------------------------------------------
# Migração: Playlists
# ---------------------------------------------------------------------------

def _batch(iterable: list, size: int) -> Generator[list, None, None]:
    """Divide uma lista em sublistas de tamanho `size`."""
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


def migrate_playlist(
    sp: spotipy.Spotify,
    ytmusic: YTMusic,
    playlist: dict,
) -> None:
    """Migra uma única playlist do Spotify para o YT Music."""
    playlist_name: str = playlist["name"]
    playlist_id: str = playlist["id"]
    logger.info(f"  → Migrando playlist: '{playlist_name}'")

    # 1. Coletar videoIds das faixas
    video_ids: list[str] = []
    spotify_track_count = 0
    for track in fetch_playlist_tracks(sp, playlist_id):
        spotify_track_count += 1
        track_name: str = track["name"]
        artist_name: str = track["artists"][0]["name"]

        video_id = find_video_id(ytmusic, track_name, artist_name)
        if video_id:
            video_ids.append(video_id)
            logger.info(f"    ✔ Encontrado: {track_name} — {artist_name}")
        else:
            log_error(f"[PLAYLIST:{playlist_name}][NAO_ENCONTRADO] {track_name} — {artist_name}")

        time.sleep(RATE_LIMIT_SLEEP_SECONDS)

    if spotify_track_count == 0:
        logger.warning(f"  '{playlist_name}': Spotify não retornou nenhuma faixa (playlist inacessível ou vazia).")
        return

    if not video_ids:
        logger.warning(f"  '{playlist_name}': {spotify_track_count} faixa(s) do Spotify, mas nenhuma encontrada no YouTube Music.")
        return

    # 2. Criar nova playlist no YT Music
    try:
        new_playlist_id: str = ytmusic.create_playlist(
            title=playlist_name,
            description=f"Migrado do Spotify: {playlist_name}",
        )
        logger.info(f"  ✔ Playlist criada no YT Music: '{playlist_name}' (id={new_playlist_id})")
    except Exception as e:  # noqa: BLE001
        log_error(f"[PLAYLIST_CRIACAO_FALHOU] '{playlist_name}' | {e}")
        return

    # 3. Adicionar faixas em lotes para evitar timeout
    for chunk in _batch(video_ids, CHUNK_SIZE):
        try:
            ytmusic.add_playlist_items(new_playlist_id, chunk)
            logger.info(f"    ✔ Lote de {len(chunk)} faixas adicionado.")
        except Exception as e:  # noqa: BLE001
            log_error(f"[PLAYLIST:{playlist_name}][LOTE_FALHOU] {e}")
        time.sleep(RATE_LIMIT_SLEEP_SECONDS)


def migrate_playlists(sp: spotipy.Spotify, ytmusic: YTMusic) -> None:
    """Busca todas as playlists do usuário no Spotify e as migra para o YT Music."""
    logger.info("=== Iniciando migração de PLAYLISTS ===")
    total = 0

    for playlist in fetch_user_playlists(sp):
        migrate_playlist(sp, ytmusic, playlist)
        total += 1

    logger.info(f"=== Playlists concluído: {total} processadas ===")


# ---------------------------------------------------------------------------
# Menu principal
# ---------------------------------------------------------------------------

def print_menu() -> None:
    print("\n╔══════════════════════════════════════╗")
    print("║   Spotify → YouTube Music Migrate    ║")
    print("╠══════════════════════════════════════╣")
    print("║  1. Migrar somente Músicas Curtidas  ║")
    print("║  2. Migrar somente Playlists         ║")
    print("║  3. Migrar Tudo                      ║")
    print("║  0. Sair                             ║")
    print("╚══════════════════════════════════════╝")


def main() -> None:
    print_menu()
    choice = input("Escolha uma opção: ").strip()

    if choice == "0":
        logger.info("Saindo.")
        return

    if choice not in {"1", "2", "3"}:
        logger.error("Opção inválida.")
        return

    logger.info("Autenticando no Spotify...")
    sp = build_spotify_client()

    logger.info("Autenticando no YouTube Music...")
    ytmusic = build_ytmusic_client()

    if choice == "1":
        migrate_liked_songs(sp, ytmusic)
    elif choice == "2":
        migrate_playlists(sp, ytmusic)
    elif choice == "3":
        migrate_liked_songs(sp, ytmusic)
        migrate_playlists(sp, ytmusic)

    logger.info(f"Migração finalizada. Verifique '{ERROR_LOG_FILE}' para itens com falha.")


if __name__ == "__main__":
    main()
