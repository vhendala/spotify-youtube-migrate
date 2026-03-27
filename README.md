# 🎵 Spotify → YouTube Music Migrator

A Python CLI tool that automatically migrates your Spotify music library — liked songs and playlists — to YouTube Music.

## Features

- ✅ Migrate all **Liked Songs** (handles Spotify's 50-item pagination)
- ✅ Migrate all **Playlists** with their tracks (added in batches to avoid API timeouts)
- ✅ Rate limit protection with `time.sleep()` between requests
- ✅ Error log file (`migracao_erros.txt`) listing every song that couldn't be found or migrated
- ✅ Interactive menu to choose what to migrate

## Requirements

- Python 3.10+
- A Spotify Developer App
- A YouTube Music account with OAuth credentials

## Installation

```bash
git clone https://github.com/your-username/youtube-spotify-migrate.git
cd youtube-spotify-migrate
pip install spotipy ytmusicapi python-dotenv
```

## Configuration

### 1. Spotify Credentials

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create an app.
2. Copy your **Client ID** and **Client Secret**.
3. Add `http://127.0.0.1:8888/callback` as a **Redirect URI** in the app settings.
4. Rename `.env.example` to `.env` and fill in your credentials:

```env
SPOTIPY_CLIENT_ID=your_client_id_here
SPOTIPY_CLIENT_SECRET=your_client_secret_here
```

### 2. YouTube Music OAuth

Run the following command and follow the browser prompt to authorize access:

```bash
ytmusicapi oauth
```

This generates an `oauth.json` file in the current directory, which the script reads automatically.

## Usage

```bash
python migrate.py
```

You'll see an interactive menu:

```
╔══════════════════════════════════════╗
║   Spotify → YouTube Music Migrate    ║
╠══════════════════════════════════════╣
║  1. Migrate Liked Songs only         ║
║  2. Migrate Playlists only           ║
║  3. Migrate Everything               ║
║  0. Exit                             ║
╚══════════════════════════════════════╝
```

## Error Logging

Any song that could not be found or added is saved to `migracao_erros.txt`:

```
[NOT_FOUND] Song Name — Artist Name
[PLAYLIST:My Playlist][NOT_FOUND] Another Song — Artist
[LIKE_FAILED] Song Name — Artist | <error detail>
```

Review this file after migration to manually handle missing tracks.

## Security

Sensitive files are excluded from version control via `.gitignore`:

| File | Description |
|---|---|
| `.env` | Spotify credentials |
| `oauth.json` | YouTube Music OAuth token |
| `.cache*` | Spotify local token cache |

> **Never commit `.env` or `oauth.json` to a public repository.**

## Project Structure

```
youtube-spotify-migrate/
├── migrate.py        # Main script
├── .env              # Your secrets (git-ignored)
├── .env.example      # Public template for credentials
├── .gitignore        # Protects sensitive files
└── README.md         # This file
```

## License

MIT
