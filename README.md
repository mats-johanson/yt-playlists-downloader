# Spotify Crate Downloader

Download your Spotify playlists as fully-tagged MP3s, organized into mood-named folders.
You curate playlists in Spotify; this tool matches each track to a YouTube video, downloads
it as MP3 V0, and writes proper ID3 tags + cover art from Spotify's metadata.

Files land in `../Synced Music/<Playlist Name>/Artist - Title.mp3`.

> Audio comes from YouTube. Spotify is used only for your track lists and metadata — nothing
> is ever downloaded from Spotify.

## 1. Get the code

```bash
git clone https://github.com/mats-johanson/yt-playlists-downloader.git
cd yt-playlists-downloader
```

Everything below runs from inside this folder.

## 2. Install the tools

```bash
brew install ffmpeg deno uv
```

(macOS. `ffmpeg` converts audio, `deno` solves YouTube's bot challenges, `uv` runs the app.
Everything Python is installed automatically on first run.)

## 3. Connect your Spotify account

The tool reads playlists through Spotify's API, which needs a free personal "app" for the login:

1. Open <https://developer.spotify.com/dashboard> and click **Create app**.
2. Set **Redirect URI** to exactly `http://127.0.0.1:8765/callback`, tick the **Web API**, save.
3. Copy the app's **Client ID** (you don't need the secret).
4. Put it in a `.env` file at the project root:
   ```bash
   cp .env.example .env      # then paste your Client ID into SPOTIFY_CLIENT_ID
   ```

The first run opens your browser once to approve access; the login is cached after that.

## 4. Pick which playlists to download

In Spotify, add **`[DJ]`** anywhere in the **description** of each playlist you want downloaded.
That's the whole selection mechanism — tagged playlists are in, everything else is ignored.

## 5. Run

```bash
./download_playlists.sh
```

You'll see a live progress bar per playlist. When it finishes you get a summary of what
downloaded and anything that couldn't be matched. Re-run any time — already-downloaded tracks
are skipped, so it only fetches what's new.

---

## Fixing a wrong match

Some tracks resolve to the wrong video (live takes, covers, remixes). After a run, `logs/unmatched.txt`
lists anything that scored too low. To pin a specific YouTube video for a track, drop a line into
`config/spotify_overrides.toml`:

```toml
# <spotify_track_id> = "<youtube_video_id>"
"3n3Ppam7vgaVa1iaRUc9Lp" = "dQw4w9WgXcQ"
```

## Options

```
./download_playlists.sh [--no-dashboard] [--debug] [--logout] [--clean-orphans]
```

| Flag | Effect |
|---|---|
| `--no-dashboard` | Single-line progress instead of the multi-bar view |
| `--debug` | Verbose yt-dlp output to `logs/debug.log` |
| `--logout` | Forget the Spotify login (re-auth on next run) |
| `--clean-orphans` | Reset download history for folders you've deleted |

- Set `OUTPUT_ROOT=/path/to/music` to change where files are saved.
- Want to add a YouTube playlist that isn't on Spotify, or use a tag other than `[DJ]`?
  `cp config/playlists.toml.example config/playlists.toml` and edit it. Optional — the tool
  runs fine without it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| **"No Spotify playlists matched [DJ]"** | Make sure `[DJ]` is in the playlist *description* (not the title). Spotify caches edits ~30s. |
| **"Port 8765 in use"** | Set `SPOTIFY_REDIRECT_PORT=8766` in `.env` **and** update the Redirect URI in your Spotify app to match. |
| **Login refused / expired** | `./download_playlists.sh --logout`, then run again. |
| **403 / "Sign in to confirm"** | Confirm `deno` is installed and on your `PATH`. |

## For developers

Architecture, module map, matcher tuning, and the full file layout live in
[`CLAUDE.md`](CLAUDE.md). Tests: `uv run --extra dev pytest`.
