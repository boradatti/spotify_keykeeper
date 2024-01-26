from typing import TypeAlias

from tools.spotify import SpotifyAPI, SpotifyPlaylist, SpotifyTrack
from tools.db import SQLite, SQLKeyMode, SQLTrack
from tools.pil import get_encoded_cover
from utils.misc import chunk_list

SharedTrackList: TypeAlias = list[SpotifyTrack | SQLTrack]


class SpotifySQLHandler:
  spotify: SpotifyAPI
  sql: SQLite

  def __init__(self, *, spotify: SpotifyAPI, sql: SQLite):
    self.spotify = spotify
    self.sql = sql

  def iterate_playlists(self, *, key: SQLKeyMode, mode: SQLKeyMode, playlists: list[SpotifyPlaylist]) -> None:
      for playlist in playlists:
        print(f'⌛ Compiling from "{playlist}"')
        collection_playlist_id = self.get_collection_playlist_id(key=key, mode=mode, playlist=playlist)
        collection_playlist_tracks, final_tracks = self.get_track_lists(collection_playlist_id=collection_playlist_id)
        self.iterate_playlist_tracks(
          key=key,
          mode=mode,
          playlist=playlist,
          collection_playlist_id=collection_playlist_id,
          collection_playlist_tracks=collection_playlist_tracks,
          final_tracks=final_tracks
        )
        self.check_for_new_collection_tracks(
          collection_playlist_id=collection_playlist_id,
          collection_playlist_tracks=collection_playlist_tracks,
          final_tracks=final_tracks
        )
        self.clear_current_collection(
          collection_playlist_id=collection_playlist_id,
          collection_playlist_tracks=collection_playlist_tracks
        )
        self.add_final_tracks_to_collection(
          collection_playlist_id=collection_playlist_id,
          final_tracks=final_tracks
        )
      print('✅ Done!')

  def create_collection_playlist(self, *, playlist: SpotifyPlaylist, key_str: str, mode_str: str) -> SpotifyPlaylist:
    name = f'{playlist.name} • {key_str} {mode_str}'
    description = f'All the tracks in "{playlist.name}" that might be in the key of {key_str} {mode_str}'
    cover = get_encoded_cover(img_url=playlist.cover, text_key=key_str, text_mode=mode_str)
    col_playlist = self.spotify.create_playlist(name, description, cover)
    return col_playlist

  def set_track_analytics(self, track: SpotifyTrack) -> None:
    sql_analytics = self.sql.get_track_analytics(track.id)
    if sql_analytics:
      track.set_analytics(key=sql_analytics.key, mode=sql_analytics.mode, tempo=sql_analytics.tempo)
    else:
      self.spotify.get_track_analytics(track)

  def get_collection_playlist_id(self, *, key: SQLKeyMode, mode: SQLKeyMode, playlist: SpotifyPlaylist) -> str:
      collection_playlist_id: str = None

      sql_collection = self.sql.get_collection_by_data(playlist_id=playlist.id, key=key.id, mode=mode.id)

      if not sql_collection:
        collection_playlist_id = self.create_collection_playlist(playlist=playlist, key_str=key.name, mode_str=mode.name).id
      elif not self.spotify.check_following_playlist(sql_collection.id):
        self.sql.delete_collection(sql_collection.id)
        collection_playlist_id = self.create_collection_playlist(playlist=playlist, key_str=key.name, mode_str=mode.name).id
        sql_collection = None

      if not sql_collection:
        self.sql.add_collection(collection_id=collection_playlist_id, playlist_id=playlist.id, key=key.id, mode=mode.id)
      else:
        collection_playlist_id = sql_collection.id

      return collection_playlist_id

  def get_track_lists(self, *, collection_playlist_id: SharedTrackList) -> tuple[list[SpotifyTrack], SharedTrackList]:
      collection_playlist_tracks = list(self.spotify.get_playlist_tracks(collection_playlist_id))
      final_tracks: SharedTrackList = []
      return collection_playlist_tracks, final_tracks

  def iterate_playlist_tracks(
      self,
      *,
      key: SQLKeyMode,
      mode: SQLKeyMode,
      playlist: SpotifyPlaylist,
      collection_playlist_id: SharedTrackList,
      collection_playlist_tracks: list[SpotifyTrack],
      final_tracks: SharedTrackList
    ) -> None:
      for playlist_track in self.spotify.get_playlist_tracks(playlist.id):
        sql_collection_track = self.sql.get_track_by_collection(track_id=playlist_track.id, collection_id=collection_playlist_id)
        if sql_collection_track:
          if sql_collection_track not in collection_playlist_tracks:
            continue
          final_tracks.append(sql_collection_track)
        self.set_track_analytics(playlist_track)
        if playlist_track.matches(key=key.id, mode=mode.id):
          if playlist_track not in final_tracks:
            final_tracks.append(playlist_track)
          if not sql_collection_track:
            self.sql.add_track(track_id=playlist_track.id, collection_id=collection_playlist_id, tempo=playlist_track.tempo)

  def check_for_new_collection_tracks(
      self,
      *,
      collection_playlist_id: str,
      collection_playlist_tracks: list[SpotifyTrack],
      final_tracks: SharedTrackList
    ) -> None:
      for collection_track in collection_playlist_tracks:
        if collection_track not in final_tracks:
          self.set_track_analytics(collection_track)
          final_tracks.append(collection_track)
          sql_collection_track = self.sql.get_track_by_collection(track_id=collection_track.id, collection_id=collection_playlist_id)
          if not sql_collection_track:
            self.sql.add_track(track_id=collection_track.id, collection_id=collection_playlist_id, tempo=collection_track.tempo)

  def clear_current_collection(self, *, collection_playlist_id: str, collection_playlist_tracks: SharedTrackList) -> None:
      for chunk in chunk_list(collection_playlist_tracks, 100):
        track_ids = [track.id for track in chunk]
        self.spotify.delete_playlist_tracks(playlist_id=collection_playlist_id, track_ids=track_ids)

  def add_final_tracks_to_collection(self, *,  collection_playlist_id: str, final_tracks: SharedTrackList) -> None:
    final_tracks.sort(key=lambda x: x.tempo)
    for chunk in chunk_list(final_tracks, 100):
      track_ids = [track.id for track in chunk]
      self.spotify.add_playlist_tracks(playlist_id=collection_playlist_id, track_ids=track_ids)
