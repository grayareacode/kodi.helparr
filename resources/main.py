import os
import sys
import random

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

# Manually add resources to python path to ensure imports work
addon = xbmcaddon.Addon()
addon_dir = addon.getAddonInfo("path")
sys.path.insert(0, os.path.join(addon_dir, "resources"))

from client import MediaClient
from utils import log, notify, PLAYER_FILENAME


def main():
    url = sys.argv[0]
    try:
        handle = int(sys.argv[1])
    except Exception:
        handle = -1

    # Parse query string manually
    query_str = sys.argv[2] if len(sys.argv) > 2 else ""
    params = {}
    if query_str.startswith("?"):
        query_str = query_str[1:]
    if query_str:
        for pair in query_str.split("&"):
            if "=" in pair:
                key, val = pair.split("=", 1)
                params[key] = val

    action = params.get("action")

    log(f"Action: {action}, Params: {params}")

    if not action:
        # Root listing

        # Item 1: Play Test Video
        li = xbmcgui.ListItem(label="Play Test Video")
        # Fix deprecation: use InfoTagVideo
        info = li.getVideoInfoTag()
        info.setTitle("Test Video")

        li.setArt({"icon": "DefaultVideo.png"})
        li.setProperty("IsPlayable", "true")
        play_url = url + "?action=test_play"
        xbmcplugin.addDirectoryItem(
            handle=handle, url=play_url, listitem=li, isFolder=False
        )

        # Item 3: Uninstall Player
        li_uninstall = xbmcgui.ListItem(label="Uninstall Player from TMDbHelper")
        li_uninstall.setArt({"icon": "DefaultAddon.png"})
        uninstall_url = url + "?action=uninstall_player"
        xbmcplugin.addDirectoryItem(
            handle=handle, url=uninstall_url, listitem=li_uninstall, isFolder=False
        )

        # Item 4: Settings
        li_settings = xbmcgui.ListItem(label="Settings")
        li_settings.setArt({"icon": "DefaultAddon.png"})
        settings_url = url + "?action=settings"
        xbmcplugin.addDirectoryItem(
            handle=handle, url=settings_url, listitem=li_settings, isFolder=False
        )

        xbmcplugin.endOfDirectory(handle)
        return

    if action == "settings":
        addon.openSettings()
        return

    if action == "uninstall_player":
        uninstall_player()
        return

    if action == "test_play":
        # Direct play for testing
        play_downloading_video(handle, title="Test Video")
        return

    # Handle Main Play Action
    if action == "play":
        tmdb_id = params.get("tmdb_id")
        media_type = params.get("type", "movie")
        season = params.get("season")
        episode = params.get("episode")
        handle_play_request(handle, tmdb_id, media_type, season, episode)


def uninstall_player():
    dest_folder = xbmcvfs.translatePath(
        "special://profile/addon_data/plugin.video.themoviedb.helper/players/"
    )
    dest_path = os.path.join(dest_folder, PLAYER_FILENAME)

    if xbmcvfs.exists(dest_path):
        try:
            xbmcvfs.delete(dest_path)
            notify("Player uninstalled successfully!", icon=xbmcgui.NOTIFICATION_INFO)
        except Exception as e:
            log(f"Uninstall Error: {e}", xbmc.LOGERROR)
            notify(f"Uninstall failed: {e}", icon=xbmcgui.NOTIFICATION_ERROR)
    else:
        notify(
            "Player not found (already uninstalled?)", icon=xbmcgui.NOTIFICATION_WARNING
        )


def handle_play_request(handle, tmdb_id, media_type, season=None, episode=None):
    if not tmdb_id:
        notify("Missing TMDB ID", icon=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return

    radarr_url = addon.getSetting("radarr_url")
    radarr_key = addon.getSetting("radarr_key")
    sonarr_url = addon.getSetting("sonarr_url")
    sonarr_key = addon.getSetting("sonarr_key")

    client = MediaClient(radarr_url, radarr_key, sonarr_url, sonarr_key)
    icon = addon.getAddonInfo("icon")

    notify("Checking...", icon=icon, time=2000)

    try:
        if media_type == "tv" or media_type == "episode":
            # Pass season and episode integers if available
            s_val = int(season) if season else None
            e_val = int(episode) if episode else None
            result = client.request_series(tmdb_id, season=s_val, episode=e_val)
        else:
            result = client.request_movie(tmdb_id)

        status = result.get("status")
        message = result.get("message", "Unknown response")

        data = result.get("data")
        if not data:
            data = {}
        title = data.get("title", "")

        if status == "available":
            # 2. If available, display notification. This shouldn't happen
            # as TMDb Helper will play the content if it is already available.
            notify("Already Available", header=f"{title}", icon=icon, time=5000)
            # Do NOT play video (resolve false)
            xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())

        elif status in ["requested", "monitored"]:
            # 3. If successfully requested (or monitoring), display notification AND play video.
            notify("Downloading", header=f"{title}", icon=icon, time=5000)
            play_downloading_video(
                handle,
                title=f"Downloading: {title}",
                tmdb_id=tmdb_id,
                media_type=media_type,
                season=season,
                episode=episode,
            )
        else:
            # Error
            log(f"Play Request Error: {message}", xbmc.LOGERROR)
            notify(f"Error: {message}", icon=icon, time=5000)
            xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())

    except Exception as e:
        log(f"Error: {e}", xbmc.LOGERROR)
        notify(f"Error: {e}", icon=icon, time=5000)
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())


def play_downloading_video(
    handle,
    title="Downloading...",
    tmdb_id=None,
    media_type=None,
    season=None,
    episode=None,
):
    images_dir = os.path.join(addon_dir, "resources", "images")
    video_path = None

    # Use os module for local directory operations as xbmcvfs can be inconsistent with absolute paths
    if os.path.exists(images_dir):
        try:
            files = os.listdir(images_dir)

            # Filter files that start with "downloading" and end with ".mp4"
            candidates = [
                f for f in files if f.startswith("downloading") and f.endswith(".mp4")
            ]

            if candidates:
                selected = random.choice(candidates)
                video_path = os.path.join(images_dir, selected)
        except Exception as e:
            log(f"Error listing files: {e}", xbmc.LOGERROR)
    else:
        log(f"Images directory does not exist: {images_dir}", xbmc.LOGERROR)

    if not video_path:
        log("No downloading video found!", xbmc.LOGERROR)
        notify("No downloading video found!", icon=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return

    log(f"Playing video: {video_path}")
    li = xbmcgui.ListItem(path=video_path)

    # Prevent Kodi from scraping/saving metadata for this playback
    li.setContentLookup(False)

    # Set info to prevent marking as watched and provide a clear title
    tag = li.getVideoInfoTag()
    tag.setTitle(title)
    tag.setMediaType("video")
    tag.setPlaycount(0)

    # Force Kodi to treat this as a live stream to ignore duration/watched status
    li.setProperty("IsLive", "true")
    li.setProperty("IsRealtimeStream", "true")

    # Set window properties so the service can track this playback
    # and ensure it isn't marked as watched
    window = xbmcgui.Window(10000)
    window.setProperty("helparr_active", "true")
    if tmdb_id:
        window.setProperty("helparr_tmdb_id", str(tmdb_id))
    if media_type:
        window.setProperty("helparr_media_type", str(media_type))
    if season:
        window.setProperty("helparr_season", str(season))
    if episode:
        window.setProperty("helparr_episode", str(episode))

    xbmcplugin.setResolvedUrl(handle, True, li)


if __name__ == "__main__":
    main()
