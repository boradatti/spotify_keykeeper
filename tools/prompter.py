import re
import inquirer

from tools.spotify import SpotifyAPI, SpotifyPlaylist
from tools.db import SQLite, SQLKeyMode

from utils.vars import DATA_DIRPATH

PLAYLIST_IDS_FP = f'{DATA_DIRPATH}/playlist_ids.txt'

class Prompter:
  @classmethod
  def get_key_and_mode(cls, sql: SQLite) -> tuple[SQLKeyMode, SQLKeyMode]:
    key = cls.__get_key(sql)
    mode = cls.__get_mode(sql)
    return key, mode
  
  @classmethod
  def get_playlists(cls, spotify: SpotifyAPI) -> list[SpotifyPlaylist]:
    playlist_ids = cls.__read_playlist_ids()
    cls.assert_found_playlist_ids(playlist_ids)
    playlists = cls.__get_multiple_playlists(spotify, playlist_ids)
    playlists = cls.__filter_selected_playlists(playlists)
    return playlists

  @classmethod
  def assert_found_playlist_ids(cls, playlist_ids: list[str]) -> None:
    condition = len(playlist_ids) > 0 and playlist_ids != ['']
    assert condition, f'No playlist IDs found in {PLAYLIST_IDS_FP}. Quitting...'

  @classmethod
  def __get_key(cls, sql: SQLite) -> SQLKeyMode:
    keys = sql.get_all_keys()
    return inquirer.list_input(
      'Which key would you like to collect?',
      choices=keys,
      carousel=True
    )

  @classmethod
  def __get_mode(cls, sql: SQLite) -> SQLKeyMode:
    modes = list(reversed(sql.get_all_modes()))
    return inquirer.list_input(
      'Which mode would you like to collect?',
      choices=modes,
      carousel=True
    )

  @classmethod
  def __read_playlist_ids(cls) -> list[str]:
    with open(PLAYLIST_IDS_FP, mode='r', encoding='utf8') as f:
      lines = re.split(r'\n+', f.read().strip())
      return list(set(lines))
    
  @classmethod
  def __get_multiple_playlists(cls, spotify: SpotifyAPI, ids: list[str]) -> list[SpotifyPlaylist]:
    playlists = []
    for playlist_id in ids:
      if playlist := spotify.get_playlist(playlist_id):
        playlists.append(playlist)
    return playlists

  @classmethod
  def __filter_selected_playlists(cls, playlists: list[SpotifyPlaylist]) -> list[SpotifyPlaylist]:
    return inquirer.checkbox(
      'Which playlists would you like to collect from?',
      choices=playlists,
      default=playlists,
      carousel=True
    )
