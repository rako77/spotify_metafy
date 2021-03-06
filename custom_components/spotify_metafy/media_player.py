"""Support for interacting with Spotify Metafy."""
from datetime import timedelta
import logging
from typing import Any, Callable, Dict, List, Optional

from aiohttp import ClientError
from spotipy import Spotify, SpotifyException

from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.components.media_player import MediaPlayerDevice
from homeassistant.components.spotify.media_player import SpotifyMediaPlayer
from homeassistant.components.media_player.const import (
    MEDIA_TYPE_PLAYLIST,
    SUPPORT_PAUSE,
    SUPPORT_PLAY,
    SUPPORT_SELECT_SOURCE,
    SUPPORT_SHUFFLE_SET,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_IDLE,
    STATE_PAUSED,
    STATE_PLAYING,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.event import track_state_change

import time

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

ICON = "mdi:spotify"

SCAN_INTERVAL = timedelta(hours=2)

SUPPORT_SPOTIFY_METAFY = (
    SUPPORT_PAUSE | SUPPORT_PLAY | SUPPORT_SELECT_SOURCE | SUPPORT_SHUFFLE_SET
)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigEntry,
    add_entities: Callable[[List[Entity], bool], None],
    discovery_info=None,
) -> None:
    """Set up the Spotify Metafy platform."""

    if "spotify" not in hass.data:
        raise PlatformNotReady

    entities: List[MetafyMediaPlayer] = []
    entity_component: EntityComponent = hass.data[MEDIA_PLAYER_DOMAIN]

    # Make sure all the players are ready
    for user in config["users"]:
        spotify_entity_id = user["spotify_entity_id"]
        spotify_media_player: SpotifyMediaPlayer = entity_component.get_entity(
            spotify_entity_id
        )
        if spotify_media_player is None:
            raise PlatformNotReady

    for user in config["users"]:
        user_prefix = user["user_prefix"] if "user_prefix" in user else ""
        destination = user["destination"]
        playlists = user["playlists"]
        spotify_entity_id = user["spotify_entity_id"]
        spotify_media_player: SpotifyMediaPlayer = entity_component.get_entity(
            spotify_entity_id
        )
        for playlist in playlists:
            uri = playlist["uri"]
            spotify_playlist_info = spotify_media_player._spotify.playlist(uri)
            playlist_name = user_prefix + spotify_playlist_info["name"]
            mmp = MetafyMediaPlayer(
                spotify_media_player,
                uri,
                destination,
                playlist_name,
                spotify_playlist_info,
            )
            entities.append(mmp)

    add_entities(entities)

    for entity in entities:
        track_state_change(
            hass,
            [entity._spotify_media_player.entity_id],
            entity.update_on_state_change,
        )

    return True


def spotify_exception_handler(func):
    """Decorate Spotify calls to handle Spotify exception.

    A decorator that wraps the passed in function, catches Spotify errors,
    aiohttp exceptions and handles the availability of the media player.
    """

    def wrapper(self, *args, **kwargs):
        try:
            result = func(self, *args, **kwargs)
            self.player_available = True
            return result
        except (SpotifyException, ClientError):
            self.player_available = False

    return wrapper


class MetafyMediaPlayer(MediaPlayerDevice):
    """Representation of a Spotify controller."""

    def __init__(
        self,
        spotify_media_player: SpotifyMediaPlayer,
        playlist_id: str,
        destination: str,
        name: str,
        spotify_playlist_info: str,
    ):
        """Initialize."""
        self._id = playlist_id
        self._name = name
        self._destination = destination
        self._spotify_media_player = spotify_media_player
        self._spotify_playlist_info = spotify_playlist_info

        self.player_available = True

    @property
    def name(self) -> str:
        """Return the name."""
        return self._name

    @property
    def icon(self) -> str:
        """Return the icon."""
        return ICON

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.player_available

    @property
    def unique_id(self) -> str:
        """Return the unique ID."""
        return self._id

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._id)},
            "manufacturer": "Spotify AB",
            "model": "Spotify Playlist",
            "name": self._name,
        }

    @property
    def state(self) -> Optional[str]:
        """Return the playback state."""
        if (
            self._spotify_media_player.source_list == None
            or self._destination not in self._spotify_media_player.source_list
        ):
            return STATE_UNAVAILABLE
        context = self._spotify_media_player._currently_playing.get("context")
        if context == None or context["type"] != MEDIA_TYPE_PLAYLIST:
            return STATE_IDLE
        uri = context["uri"]
        spotify = self._spotify_media_player._spotify
        uri = spotify._get_id(MEDIA_TYPE_PLAYLIST, uri)
        current_uri = spotify._get_id(MEDIA_TYPE_PLAYLIST, self._id)
        if (
            uri == current_uri
            and self._spotify_media_player.source == self._destination
        ):
            if self._spotify_media_player._currently_playing["is_playing"]:
                return STATE_PLAYING
            return STATE_PAUSED
        return STATE_IDLE

    @property
    def media_content_type(self) -> Optional[str]:
        """Return the media type."""
        return MEDIA_TYPE_PLAYLIST

    @property
    def media_image_url(self) -> Optional[str]:
        """Return the media image URL."""
        return self._spotify_playlist_info["images"][0]["url"]

    @property
    def media_image_remotely_accessible(self) -> bool:
        """If the image url is remotely accessible."""
        return True

    @property
    def media_title(self) -> Optional[str]:
        """Return the media title."""
        return self._spotify_playlist_info["name"]

    @property
    def media_playlist(self):
        """Title of Playlist currently playing."""
        return self._spotify_playlist_info["name"]

    @property
    def supported_features(self) -> int:
        """Return the media player features that are supported."""
        return SUPPORT_SPOTIFY_METAFY

    @spotify_exception_handler
    def media_play(self) -> None:
        """Start or resume playback."""
        self._spotify_media_player.select_source(self._destination)
        self._spotify_media_player.play_media(MEDIA_TYPE_PLAYLIST, self._id)
        self._spotify_media_player.media_play()
        time.sleep(1)
        self._spotify_media_player.schedule_update_ha_state(True)

    @spotify_exception_handler
    def media_pause(self) -> None:
        """Pause playback."""
        self._spotify_media_player.media_pause()
        time.sleep(1)
        self._spotify_media_player.schedule_update_ha_state(True)

    @spotify_exception_handler
    def set_shuffle(self, shuffle: bool) -> None:
        """Enable/Disable shuffle mode."""
        self._spotify_media_player.shuffle(shuffle)

    @property
    def source_list(self) -> Optional[List[str]]:
        """Return a list of source devices."""
        return self._spotify_media_player.source_list

    @spotify_exception_handler
    def select_source(self, source: str) -> None:
        """Select playback device."""
        self._destination = source
        self._spotify_media_player.select_source(source)

    @spotify_exception_handler
    def update(self) -> None:
        """Update state and attributes."""
        if not self.enabled:
            return

        if not self._spotify_media_player._session.valid_token:
            return

        # todo make this call less frequently
        playlist_image = self._spotify_media_player._spotify.playlist_cover_image(
            self._id
        )
        self._spotify_playlist_info["images"] = playlist_image

    @spotify_exception_handler
    def update_on_state_change(self, entity_id, old_state, new_state) -> None:
        """Update state and attributes."""
        self.schedule_update_ha_state()
