import requests
import xbmc
from utils import log

ENABLE_REQUESTS = True


class MediaClient:
    def __init__(self, radarr_host, radarr_apikey, sonarr_host, sonarr_apikey):
        self._radarr_host = radarr_host
        if not self._radarr_host.startswith("http"):
            self._radarr_host = "http://" + self._radarr_host

        self._radarr_apikey = radarr_apikey

        self._sonarr_host = sonarr_host
        if not self._sonarr_host.startswith("http"):
            self._sonarr_host = "http://" + self._sonarr_host

        self._sonarr_apikey = sonarr_apikey
        self._radarr_headers = {"X-Api-Key": self._radarr_apikey}
        self._sonarr_headers = {"X-Api-Key": self._sonarr_apikey}

    # ----------------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------------
    def _get_radarr_quality_profile_id(self):
        return self._get_quality_profile_id(self._radarr_host, self._radarr_headers)

    def _get_sonarr_quality_profile_id(self):
        return self._get_quality_profile_id(self._sonarr_host, self._sonarr_headers)

    def _get_quality_profile_id(self, host, headers):
        url = f"{host}/api/v3/qualityprofile"
        try:
            r = requests.get(url, headers=headers)
            r.raise_for_status()
            profiles = r.json()
            if profiles:
                # Prefer 'Any;'
                for profile in profiles:
                    if profile["name"] == "Any":
                        return profile["id"]
                return profiles[0]["id"]
        except Exception as e:
            log(f"Error getting quality profile: {e}", xbmc.LOGERROR)
        return 1

    def _get_radarr_root_folder_path(self):
        return self._get_root_folder_path(self._radarr_host, self._radarr_headers)

    def _get_sonarr_root_folder_path(self):
        return self._get_root_folder_path(self._sonarr_host, self._sonarr_headers)

    def _get_root_folder_path(self, host, headers):
        url = f"{host}/api/v3/rootfolder"
        try:
            r = requests.get(url, headers=headers)
            r.raise_for_status()
            folders = r.json()
            if folders:
                return folders[0]["path"]
        except Exception as e:
            log(f"Error getting root folder: {e}", xbmc.LOGERROR)
        return ""

    # ----------------------------------------------------------------------
    # Movie Methods
    # ----------------------------------------------------------------------
    def get_movie(self, tmdb_id):
        """
        Check if a movie exists in Radarr.
        Returns the movie object if found, None otherwise.
        """
        check_url = f"{self._radarr_host}/api/v3/movie?tmdbId={tmdb_id}"
        try:
            r = requests.get(check_url, headers=self._radarr_headers)
            r.raise_for_status()
            existing_movies = r.json()
            if existing_movies:
                return existing_movies[0]
        except Exception as e:
            log(f"Error checking for movie: {e}", xbmc.LOGERROR)
        return None

    def add_movie(self, tmdb_id):
        """
        Add a movie to Radarr.
        Returns the added movie object.
        """
        # Grab movie data for payload
        lookup_url = f"{self._radarr_host}/api/v3/movie/lookup/tmdb?tmdbId={tmdb_id}"
        r = requests.get(lookup_url, headers=self._radarr_headers)
        r.raise_for_status()
        movie = r.json()

        # Prepare payload
        movie["qualityProfileId"] = self._get_radarr_quality_profile_id()
        movie["rootFolderPath"] = self._get_radarr_root_folder_path()
        movie["monitored"] = True
        movie["addOptions"] = {"searchForMovie": True}

        if not movie["rootFolderPath"]:
            raise Exception("No root folder found in Radarr configuration.")

        # Add movie
        if ENABLE_REQUESTS:
            post_url = f"{self._radarr_host}/api/v3/movie"
            r = requests.post(post_url, json=movie, headers=self._radarr_headers)
            r.raise_for_status()
            return r.json()
        else:
            return movie

    def request_movie(self, tmdb_id):
        """
        High-level workflow:
        1. Check if movie exists.
        2. If yes, return status (available/monitored).
        3. If no, add it and return status (requested).
        """
        movie = self.get_movie(tmdb_id)

        if movie:
            is_available = movie.get("hasFile", False)
            status = "available" if is_available else "monitored"
            message = (
                f"Movie '{movie.get('title')}' is already downloaded and available."
                if is_available
                else f"Movie '{movie.get('title')}' is already monitored but not yet downloaded."
            )
            return {
                "status": status,
                "message": message,
                "available": is_available,
                "data": movie,
            }
        else:
            try:
                new_movie = self.add_movie(tmdb_id)
                return {
                    "status": "requested",
                    "message": f"Successfully requested movie: {new_movie.get('title')}",
                    "available": False,
                    "data": new_movie,
                }
            except Exception as e:
                log(f"Error adding movie: {e}", xbmc.LOGERROR)
                return {
                    "status": "error",
                    "message": f"Error adding movie: {e}",
                    "available": False,
                    "data": None,
                }

    # ----------------------------------------------------------------------
    # Series Methods
    # ----------------------------------------------------------------------
    def get_series(self, tmdb_id):
        """
        Check if a series exists in Sonarr.
        Returns the fully detailed series object if found, None otherwise.
        """
        # 1. Lookup to find internal ID
        lookup_url = f"{self._sonarr_host}/api/v3/series/lookup?term=tmdb:{tmdb_id}"
        try:
            r = requests.get(lookup_url, headers=self._sonarr_headers)
            r.raise_for_status()
            series_list = r.json()
            if not series_list:
                return None

            series_candidate = series_list[0]
            if series_candidate.get("id", 0) > 0:
                # 2. Fetch full details using internal ID
                series_id = series_candidate["id"]
                detail_url = f"{self._sonarr_host}/api/v3/series/{series_id}"
                r_detail = requests.get(detail_url, headers=self._sonarr_headers)
                r_detail.raise_for_status()
                return r_detail.json()
        except Exception as e:
            log(f"Error getting series: {e}", xbmc.LOGERROR)
        return None

    def get_episode(self, series_id, season_number, episode_number):
        """
        Fetch a specific episode from Sonarr.
        """
        ep_url = f"{self._sonarr_host}/api/v3/episode?seriesId={series_id}&seasonNumber={season_number}"
        try:
            r = requests.get(ep_url, headers=self._sonarr_headers)
            r.raise_for_status()
            episodes = r.json()
            return next(
                (ep for ep in episodes if ep["episodeNumber"] == episode_number),
                None,
            )
        except Exception as e:
            log(f"Error getting episode: {e}", xbmc.LOGERROR)
            return None

    def add_series(self, tmdb_id):
        """
        Add a series to Sonarr.
        Returns the added series object.
        """
        # Lookup series data
        lookup_url = f"{self._sonarr_host}/api/v3/series/lookup?term=tmdb:{tmdb_id}"
        r = requests.get(lookup_url, headers=self._sonarr_headers)
        r.raise_for_status()
        series_list = r.json()

        if not series_list:
            raise Exception(f"No series found for TMDB ID {tmdb_id}")

        series = series_list[0]
        if series.get("id", 0) > 0:
            raise Exception(f"Series '{series.get('title')}' is already added.")

        # Prepare payload
        series["qualityProfileId"] = self._get_sonarr_quality_profile_id()
        series["rootFolderPath"] = self._get_sonarr_root_folder_path()
        series["monitored"] = True

        # Ensure addOptions is set
        add_options = series.get("addOptions", {}) or {}
        add_options["searchForMissingEpisodes"] = True
        series["addOptions"] = add_options

        # Ensure all seasons are monitored
        if "seasons" in series:
            for season in series["seasons"]:
                season["monitored"] = True

        if not series["rootFolderPath"]:
            raise Exception("No root folder found in Sonarr configuration.")

        # Add series
        if ENABLE_REQUESTS:
            post_url = f"{self._sonarr_host}/api/v3/series"
            r = requests.post(post_url, json=series, headers=self._sonarr_headers)
            r.raise_for_status()
            return r.json()
        else:
            return series

    def request_series(self, tmdb_id, season=None, episode=None):
        """
        High-level workflow:
        1. Check if series exists.
        2. If yes, check specific episode (if requested) or overall series status.
        3. If no, add series and return status.
        """
        series = self.get_series(tmdb_id)

        if series:
            # Series exists
            if season is not None and episode is not None:
                # Check specific episode
                ep_obj = self.get_episode(series["id"], season, episode)
                if ep_obj:
                    is_available = ep_obj.get("hasFile", False)
                    status = "available" if is_available else "monitored"
                    message = (
                        f"Episode S{season:02d}E{episode:02d} of '{series.get('title')}' is downloaded and available."
                        if is_available
                        else f"Episode S{season:02d}E{episode:02d} of '{series.get('title')}' is monitored but not yet downloaded."
                    )
                    return {
                        "status": status,
                        "message": message,
                        "available": is_available,
                        "data": ep_obj,  # Return episode data
                    }
                else:
                    return {
                        "status": "error",
                        "message": f"Episode S{season:02d}E{episode:02d} not found.",
                        "available": False,
                        "data": None,
                    }
            else:
                # Check Series Availability
                stats = series.get("statistics", {})
                file_count = stats.get("episodeFileCount", 0)
                episode_count = stats.get("episodeCount", 0)
                percent = stats.get("percentOfEpisodes", 0)

                is_available = percent == 100 or (
                    file_count > 0 and file_count == episode_count
                )

                if is_available:
                    status = "available"
                    message = f"Series '{series.get('title')}' is already downloaded and available."
                elif file_count > 0:
                    status = "monitored"
                    remaining = episode_count - file_count
                    message = f"Series '{series.get('title')}' is monitored. {file_count}/{episode_count} episodes downloaded ({remaining} remaining)."
                else:
                    status = "monitored"
                    message = f"Series '{series.get('title')}' is already monitored but not yet downloaded."

                return {
                    "status": status,
                    "message": message,
                    "available": is_available,
                    "data": series,
                }
        else:
            # Series Missing -> Add it
            try:
                new_series = self.add_series(tmdb_id)
                return {
                    "status": "requested",
                    "message": f"Successfully requested series: {new_series.get('title')}",
                    "available": False,
                    "data": new_series,
                }
            except Exception as e:
                log(f"Error adding series: {e}", xbmc.LOGERROR)
                return {
                    "status": "error",
                    "message": f"Error adding series: {e}",
                    "available": False,
                    "data": None,
                }
