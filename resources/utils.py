import os

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs


ADDON_NAME = "TMDb Download Helparr"
PLAYER_FILENAME = "helparr.json"


def log(msg, level=xbmc.LOGINFO):
    xbmc.log(f"[{ADDON_NAME}] {msg}", level)


def notify(message, header=ADDON_NAME, icon=xbmcgui.NOTIFICATION_INFO, time=5000):
    xbmcgui.Dialog().notification(header, message, icon, time)


def install_player():
    addon = xbmcaddon.Addon()
    addon_dir = addon.getAddonInfo("path")

    dest_folder = xbmcvfs.translatePath(
        "special://profile/addon_data/plugin.video.themoviedb.helper/players/"
    )
    dest_path = os.path.join(dest_folder, PLAYER_FILENAME)

    # 2. Only now setup source path and read content
    source_path = os.path.join(addon_dir, "resources", "players", PLAYER_FILENAME)

    if not xbmcvfs.exists(source_path):
        log(f"Source player file not found at: {source_path}", xbmc.LOGERROR)
        notify("Source player file not found", icon=xbmcgui.NOTIFICATION_ERROR)
        return

    try:
        with xbmcvfs.File(source_path) as f:
            source_content = f.read()
    except Exception as e:
        log(f"Read Error: {e}", xbmc.LOGERROR)
        return

    # Check if update is needed
    if xbmcvfs.exists(dest_path):
        try:
            with xbmcvfs.File(dest_path) as f:
                dest_content = f.read()
            if source_content == dest_content:
                # Already up to date
                return
        except Exception:
            pass

    # 3. Create folder if needed
    if not xbmcvfs.exists(dest_folder):
        if not xbmcvfs.mkdirs(dest_folder):
            log(f"Create folder failed: {dest_folder}", xbmc.LOGERROR)
            notify("Create folder failed", icon=xbmcgui.NOTIFICATION_ERROR)
            return

    # 4. Write file
    try:
        with xbmcvfs.File(dest_path, "w") as f:
            f.write(source_content)
        log("Player installed.", xbmc.LOGINFO)
        notify("TMDb Helper Player Installed", icon=xbmcgui.NOTIFICATION_INFO)
    except Exception as e:
        log(f"Install Error: {e}", xbmc.LOGERROR)
        notify(f"Install failed: {e}", icon=xbmcgui.NOTIFICATION_ERROR)
