"""Support for interacting with Spotify Metafy."""
from collections import namedtuple
from datetime import datetime, timedelta
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Union, cast
import pprint

from aiohttp import ClientError
from attr import dataclass
from homeassistant.helpers import event
from spotipy import Spotify, SpotifyException
import spotify_token

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
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.event import track_state_change
from homeassistant.components.cast.media_player import CastDevice

import time

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

ICON = "mdi:spotify"

SCAN_INTERVAL = timedelta(hours=2)

SUPPORT_SPOTIFY_METAFY = (
    SUPPORT_PAUSE | SUPPORT_PLAY | SUPPORT_SELECT_SOURCE | SUPPORT_SHUFFLE_SET
)

access_token = None


def setup_platform(
    hass: HomeAssistant,
    config: ConfigEntry,
    add_entities: Callable[[List[Entity], bool], None],
    discovery_info=None,
) -> None:
    """Set up the Spotify Metafy platform."""

    token_manager = SpotifyTokenManager(hass, config)
    entity_component: EntityComponent = hass.data[MEDIA_PLAYER_DOMAIN]

    def on_entity_added(event: Event):
        for user in config["users"]:
            spotify_entity_id = user['spotify_entity_id']
            chromecast_entity_id = user['chromecast_entity_id']
            if event.data['entity_id'] in [chromecast_entity_id, spotify_entity_id]:
                chromecast_entity = entity_component.get_entity(chromecast_entity_id)
                spotify_entity =  cast(SpotifyMediaPlayer, entity_component.get_entity(spotify_entity_id))

                # We'll come back here when the other entity updates
                if chromecast_entity is None or spotify_entity is None:
                    return

                user_prefix = user["user_prefix"] if "user_prefix" in user else ""
                destination = user["destination"]
                playlists = user["playlists"]


                add_entities([MetafyMediaPlayer(
                spotify_entity,
                playlist["uri"],
                destination,
                user_prefix + spotify_entity._spotify.spotify_playlist_info[playlist['uri']]['name'],
                spotify_entity._spotify.spotify_playlist_info[playlist['uri']],
                chromecast_entity,
            ) for playlist in playlists])
    event.async_track_state_added_domain(hass, 'media_player', on_entity_added)

    entities: List[MetafyMediaPlayer] = []

    # Make sure all the players are ready
    #for user in config["users"]:
    #    spotify_entity_id = user["spotify_entity_id"]
    #    spotify_media_player: SpotifyMediaPlayer = entity_component.get_entity(
    #        spotify_entity_id
    #    )
    #    chromecast_entity: CastDevice = entity_component.get_entity(
    #        user["chromecast_entity_id"]
    #    )

    #    sp_key = user["sp_key"]
    #    sp_dc = user["sp_dc"]
    #    global access_token
    #    if access_token is None:
    #        pass
    #    print(access_token)
    #    if spotify_media_player is None or chromecast_entity is None:
    #        raise PlatformNotReady

    #for user in config["users"]:
    #    user_prefix = user["user_prefix"] if "user_prefix" in user else ""
    #    destination = user["destination"]
    #    playlists = user["playlists"]
    #    spotify_entity_id = user["spotify_entity_id"]
    #    spotify_media_player: SpotifyMediaPlayer = entity_component.get_entity(
    #        spotify_entity_id
    #    )
    #    chromecast_entity = entity_component.get_entity(user["chromecast_entity_id"])
    #    for playlist in playlists:
    #        uri = playlist["uri"]
    #        spotify_playlist_info = spotify_media_player._spotify.playlist(uri)
    #        playlist_name = user_prefix + spotify_playlist_info["name"]
    #        mmp = MetafyMediaPlayer(
    #            spotify_media_player,
    #            uri,
    #            destination,
    #            playlist_name,
    #            spotify_playlist_info,
    #            chromecast_entity,
    #        )
    #        entities.append(mmp)

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
        chromecast_entity: CastDevice,
    ):
        """Initialize."""
        self._id = playlist_id
        self._name = name
        self._destination = destination
        self._spotify_media_player = spotify_media_player
        self._spotify_playlist_info = spotify_playlist_info

        print(self._access_token)
        print(self._spotify_media_player.access_token)
        # pprint.pprint(vars(self._spotify_media_player))
        pprint.pprint(self._spotify_media_player._session.token)
        print(type(chromecast_entity))
        pprint.pprint(vars(chromecast_entity))
        self.chromecast_entity = chromecast_entity

        self.player_available = True

    @property
    def creds(self) -> str:
        """Return the creds"""
        return self._spotify_media_player.access_token

    @property
    def yolo(self) -> str:
        return "YOLO"

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
        return STATE_IDLE
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
        global access_token
        self.chromecast_entity.play_media(
            media_type="cast",
            media_id=json.dumps(
                {
                    "app_name": "spotify",
                    "media_id": "unused",
                    "access_token": access_token,
                }
            ),
        )
        # self._spotify_media_player.select_source(self._destination)
        # self._spotify_media_player.play_media(MEDIA_TYPE_PLAYLIST, self._id)
        # self._spotify_media_player.media_play()
        # time.sleep(1)
        # self._spotify_media_player.schedule_update_ha_state(True)

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

@dataclass
class Token:
    access_token: str
    expiry_time: datetime

@dataclass
class User:
    prefix: str
    sp_key: str
    sp_dc: str

    token: Union[None, Token]

class SpotifyTokenManager:

    data: Dict[str, User]

    def __init__(self, hass: HomeAssistant, config: ConfigEntry):
        self.hass = hass
        self.data = {
            user["user_prefix"]: User(
                prefix=user["user_prefix"], sp_dc=user["sp_dc"], sp_key=user["sp_key"], token=None
            )
            for user in config["users"]
        }

        event.async_track_time_interval(hass, self.update_tokens, timedelta(minutes=10))

    def update_tokens(self, arg):
        for user in self.data.values():
            token, expiry = spotify_token.start_session(dc=user.sp_dc, key=user.sp_key)
            user.token = Token(access_token=token, expiry_time=datetime.fromtimestamp(expiry))

        _LOGGER.debug("Updated tokens " + pprint.pformat(self.data))
