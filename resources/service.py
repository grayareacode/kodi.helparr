import os
import sys

import time
import xbmc
import xbmcgui
import xbmcaddon
import json

# Manually add resources to python path
addon = xbmcaddon.Addon()
addon_dir = addon.getAddonInfo("path")
sys.path.insert(0, os.path.join(addon_dir, "resources"))

from utils import install_player, log


class PlayerMonitor(xbmc.Monitor):
    def onNotification(self, sender, method, data):
        # We can also listen to OnPlayBackStopped here if we want more granularity
        # but the check loop in main is simpler or wait logic
        pass


def mark_as_unwatched(
    tmdb_id, media_type, season=None, episode=None, playing_file=None
):
    log(f"Attempting to unwatch item: {tmdb_id} ({media_type}) S{season}E{episode}")

    # Wait a bit for Kodi to mark it as watched (if it does)
    time.sleep(2)

    # 1. Find the item in the library

    if media_type == "episode" or media_type == "tv":
        # Find TV Show first
        # We fetch all shows and filter in python to avoid JSON-RPC filter errors with uniqueid
        json_query = {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetTVShows",
            "params": {"properties": ["uniqueid"]},
            "id": 1,
        }

        response = xbmc.executeJSONRPC(json.dumps(json_query))

        try:
            data = json.loads(response)
            all_shows = data.get("result", {}).get("tvshows", [])

            # Filter python-side
            items = []
            for show in all_shows:
                unique_ids = show.get("uniqueid", {})
                # unique_ids can be a dict (kodi 19+) or maybe simple id? usually dict.
                # We check if str(tmdb_id) is in values or specifically 'tmdb' key
                if isinstance(unique_ids, dict):
                    if (
                        str(tmdb_id) == str(unique_ids.get("tmdb", ""))
                        or str(tmdb_id) in unique_ids.values()
                    ):
                        items.append(show)
                        break

            if items:
                tvshow_id = items[0].get("tvshowid")
                log(f"Found TV Show ID: {tvshow_id}")

                if season and episode:
                    # Find specific episode
                    ep_query = {
                        "jsonrpc": "2.0",
                        "method": "VideoLibrary.GetEpisodes",
                        "params": {
                            "tvshowid": tvshow_id,
                            "season": int(season),
                            "properties": ["episode", "season"],
                            "filter": {
                                "and": [
                                    {
                                        "field": "season",
                                        "operator": "is",
                                        "value": str(season),
                                    },
                                    {
                                        "field": "episode",
                                        "operator": "is",
                                        "value": str(episode),
                                    },
                                ]
                            },
                        },
                        "id": 2,
                    }
                    ep_response = xbmc.executeJSONRPC(json.dumps(ep_query))
                    ep_data = json.loads(ep_response)
                    episodes = ep_data.get("result", {}).get("episodes", [])

                    if episodes:
                        episode_id = episodes[0].get("episodeid")
                        log(f"Found Episode ID: {episode_id}. Resetting playcount.")

                        set_query = {
                            "jsonrpc": "2.0",
                            "method": "VideoLibrary.SetEpisodeDetails",
                            "params": {
                                "episodeid": episode_id,
                                "playcount": 0,
                                "resume": {"position": 0, "total": 0},
                            },
                            "id": 3,
                        }
                        xbmc.executeJSONRPC(json.dumps(set_query))
                        log("Episode Playcount reset to 0.")
                    else:
                        log(
                            "Episode not found in library. Attempting to unwatch via Files..."
                        )
                        unwatch_tmdb_helper_url(
                            tmdb_id, media_type, season, episode, playing_file
                        )
                else:
                    log("Season/Episode not provided for TV Show. Skipping unwatch.")

            else:
                log("TV Show not found in library. Attempting to unwatch via Files...")
                if season and episode:
                    unwatch_tmdb_helper_url(
                        tmdb_id, media_type, season, episode, playing_file
                    )
        except Exception as e:
            log(f"Error unwatching episode: {e}", xbmc.LOGERROR)

    else:
        # Movie
        json_query = {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetMovies",
            "params": {
                "properties": ["playcount", "uniqueid"],
                "filter": {
                    "field": "uniqueid",
                    "operator": "is",
                    "value": str(tmdb_id),
                },
            },
            "id": 1,
        }

        response = xbmc.executeJSONRPC(json.dumps(json_query))

        try:
            data = json.loads(response)
            items = data.get("result", {}).get("movies", [])

            if items:
                item_id = items[0].get("movieid")
                log(f"Found Movie ID: {item_id}. Resetting playcount.")

                set_query = {
                    "jsonrpc": "2.0",
                    "method": "VideoLibrary.SetMovieDetails",
                    "params": {
                        "movieid": item_id,
                        "playcount": 0,
                        "resume": {"position": 0, "total": 0},
                    },
                    "id": 2,
                }
                xbmc.executeJSONRPC(json.dumps(set_query))
                log("Movie Playcount reset to 0.")
            else:
                log("Movie not found in library. Attempting to unwatch via Files...")
                unwatch_tmdb_helper_url(tmdb_id, media_type, None, None, playing_file)

        except Exception as e:
            log(f"Error unwatching movie: {e}", xbmc.LOGERROR)


def unwatch_tmdb_helper_url(tmdb_id, media_type, season, episode, playing_file=None):
    urls = []

    # Priority: Use the exact captured file path if available
    # However, based on testing, the local file path (if captured)
    # usually fails with "Invalid params" when trying to set file details.
    # The generated plugin:// URLs are what works.
    # But we'll leave this here just in case it works in some contexts.
    if playing_file:
        urls.append(playing_file)

    base_url = "plugin://plugin.video.themoviedb.helper/"

    # Add fallback generated URLs just in case
    if media_type == "movie":
        # Variation 1: ?info=play&tmdb_id=X&tmdb_type=movie
        urls.append(f"{base_url}?info=play&tmdb_id={tmdb_id}&tmdb_type=movie")
        # Variation 2: ?info=play&tmdb_type=movie&tmdb_id=X (unlikely but safe to try)
        urls.append(f"{base_url}?info=play&tmdb_type=movie&tmdb_id={tmdb_id}")

    elif media_type == "episode" or media_type == "tv":
        if season is None or episode is None:
            return

        # Variation 1: tmdb_type=tv (Most common for episodes in TMDbHelper)
        urls.append(
            f"{base_url}?info=play&tmdb_type=tv&tmdb_id={tmdb_id}&season={season}&episode={episode}"
        )
        urls.append(
            f"{base_url}?info=play&tmdb_id={tmdb_id}&tmdb_type=tv&season={season}&episode={episode}"
        )

        # Variation 2: tmdb_type=episode
        urls.append(
            f"{base_url}?info=play&tmdb_type=episode&tmdb_id={tmdb_id}&season={season}&episode={episode}"
        )
        urls.append(
            f"{base_url}?info=play&tmdb_id={tmdb_id}&tmdb_type=episode&season={season}&episode={episode}"
        )

    for url in urls:
        json_query = {
            "jsonrpc": "2.0",
            "method": "Files.SetFileDetails",
            "params": {
                "file": url,
                "media": "video",
                "playcount": 0,
                "resume": {"position": 0, "total": 0},
            },
            "id": 10,
        }
        xbmc.executeJSONRPC(json.dumps(json_query))


def run_service():
    monitor = xbmc.Monitor()
    window = xbmcgui.Window(10000)

    playing_file = None

    while not monitor.abortRequested():
        if monitor.waitForAbort(1):
            break

        # Check if we were tracking something
        if window.getProperty("helparr_active") == "true":
            # While it is playing, capture the playing file
            if xbmc.Player().isPlaying():
                try:
                    # Capture the file path that started this playback (should be the plugin:// URL)
                    current_file = xbmc.Player().getPlayingFile()
                    if current_file and current_file != playing_file:
                        playing_file = current_file
                        # log(f"Captured playing file: {playing_file}")
                except Exception:
                    pass

            # Wait until player stops
            else:
                log("Helparr playback finished. Checking for cleanup...")

                # Get details
                tmdb_id = window.getProperty("helparr_tmdb_id")
                media_type = window.getProperty("helparr_media_type")
                season = window.getProperty("helparr_season")
                episode = window.getProperty("helparr_episode")

                # Clear active flag IMMEDIATELY
                window.clearProperty("helparr_active")
                window.clearProperty("helparr_tmdb_id")
                window.clearProperty("helparr_media_type")
                window.clearProperty("helparr_season")
                window.clearProperty("helparr_episode")

                if tmdb_id:
                    # Pass the captured playing file
                    mark_as_unwatched(
                        tmdb_id, media_type, season, episode, playing_file
                    )

                # Reset
                playing_file = None


if __name__ == "__main__":
    install_player()
    run_service()
