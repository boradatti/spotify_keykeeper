import os
import json
import requests
from time import sleep
from functools import wraps
from dataclasses import dataclass, field, InitVar
from typing import Generator, Literal, TypeAlias

from base64 import b64encode
import urllib.parse as urlparse
from urllib.parse import urlencode
from selenium import webdriver

from utils.vars import DATA_DIRPATH


BASE_URLS = {
  'api': 'https://api.spotify.com/v1',
  'auth': 'https://accounts.spotify.com'
}
SCOPES = [
  'playlist-modify-public',
  'playlist-modify-private',
  'ugc-image-upload'
]
REFRESH_TOKEN_FP = f'{DATA_DIRPATH}/refresh_token.txt'


@dataclass
class SpotifyTrack:
  id: str = field(hash=True)
  name: str
  artist: str
  key: int = field(init=False, default=None)
  mode: int = field(init=False, default=None)
  tempo: float = field(init=False, default=None)

  def set_analytics(self, *, key: int, mode: int, tempo: float):
    self.key = key
    self.mode = mode
    self.tempo = tempo

  def matches(self, *, key: int, mode: int) -> bool:
    return self.key == key and self.mode == mode

  def __eq__(self, other: 'SpotifyTrack | str') -> bool:
    if isinstance(other, SpotifyTrack) or hasattr(other, 'id'):
      return self.id == other.id
    if isinstance(other, str):
      return self.id == other

@dataclass
class SpotifyPlaylist:
  id: str
  name: str
  cover: str | None = field(init=False, default=None)
  images: InitVar[list[dict[str, str]] | None]

  def __post_init__(self, images):
    if images:
      self.cover = images[0]['url']

  def __repr__(self):
    return self.name

BaseUrlTarget: TypeAlias = Literal['api', 'auth']

class SpotifyError(Exception): ...


@dataclass
class SpotifyAPI:
  client_id: str = field(kw_only=True)
  client_secret: str = field(kw_only=True)
  redirect_uri: str = field(kw_only=True)
  
  base_64: bytes = field(init=False)
  access_token: str = field(init=False)
  refresh_token: str = field(init=False)

  class Decorators:
    @classmethod
    def __confirm_resource_found(cls, data: dict[str, dict]):
      return type(data) is not dict or data.get('error', {}).get('status') != 404
    
    @classmethod
    def __confirm_access_token_valid(cls, data: dict[str, dict]):
      return type(data) is not dict or data.get('error', {}).get('status') != 401
    
    @classmethod
    def __handle_errors(cls, data: dict[str, dict]):
      if type(data) is not dict:
        return
      if error := data.get('error'):
        raise SpotifyError(error.get('status'), error.get('message'))

    @classmethod
    def validator(cls, func):
      @wraps(func)
      def inner(*args, **kwargs):
        this: SpotifyAPI = args[0]
        if kwargs.get('target') == 'api' and not this._check_authorized():
          raise SpotifyError('Unauthorized: refresh_token.txt file not found')
        result: dict = func(*args, **kwargs)
        if not cls.__confirm_access_token_valid(result):
          this._refetch_access_token()
          result = func(*args, **kwargs)
        if not cls.__confirm_resource_found(result):
          return None
        cls.__handle_errors(result)
        return result
      return inner

  def __post_init__(self):
    self.base_64 = self.__get_b64encoded_credentials()
    self.__set_refresh_token()
    if not self._check_authorized():
      return
    self._refetch_access_token()

  # REQUESTS

  def get_playlist(self, playlist_id: str) -> SpotifyPlaylist | None:
    item = self.__get_playlist_item(playlist_id)
    if not item: return
    return self.__instantiate_playlist(item)

  def get_playlist_tracks(self, playlist_id: str) -> Generator[SpotifyTrack, None, None]:
    for item in self.__get_playlist_track_items(playlist_id):
      yield self.__instantiate_track(item)
  
  def get_track(self, track_id: str) -> SpotifyTrack | None:
    item = self.__get_track_item(track_id)
    if not item: return
    return self.__instantiate_track(item)
  
  def get_track_analytics(self, track: SpotifyTrack) -> SpotifyTrack:
    data = self.__get_track_analysis(track.id)
    self.__set_track_analytics(track, data)
  
  def create_playlist(self, name: str, description: str = '', img_base64_str: str = '') -> SpotifyPlaylist:
    playlist_id = self.__create_playlist(name, description)
    if img_base64_str:
      self.__upload_playlist_cover(playlist_id, img_base64_str)
    return self.get_playlist(playlist_id)
  
  def __create_playlist(self, name: str, description: str = '') -> str:
    return self.__post(f'/users/{self.get_current_user_id()}/playlists', data = { 'name': name, 'description': description }).get('id')
  
  def __upload_playlist_cover(self, playlist_id: str, img_base64_str: str) -> None:
    return self.__put(
      f'/playlists/{playlist_id}/images',
      headers=self.__combine_headers_with_default({'Content-Type': 'image/jpeg'}),
      data=img_base64_str
    )

  def get_current_user_id(self) -> str | None:
    data = self.get_current_user()
    return data['id']
  
  def check_following_playlist(self, playlist_id: str) -> bool:
    user_id = self.get_current_user_id()
    params = { 'ids': [user_id] }
    [following] = self.__get(f'/playlists/{playlist_id}/followers/contains', params=params)
    return following
  
  def get_current_user(self) -> dict[str, str]:
    return self.__get('/me')
  
  def add_playlist_tracks(self, *, playlist_id: str, track_ids=list[str]):
    track_uris = [f'spotify:track:{track_id}' for track_id in track_ids]
    return self.__post(f'/playlists/{playlist_id}/tracks', data={'uris': track_uris})
  
  def delete_playlist_tracks(self, *, playlist_id: str, track_ids=list[str]):
    track_uris = [{'uri': f'spotify:track:{track_id}'} for track_id in track_ids]
    return self.__delete(f'/playlists/{playlist_id}/tracks', data={'tracks': track_uris})
  
  def __get_playlist_item(self, playlist_id: str) -> dict | None:
    return self.__get(f'/playlists/{playlist_id}')

  def __get_playlist_track_items(self, playlist_id: str) -> Generator[dict, None, None]:
    return self.__iterate_all(f'/playlists/{playlist_id}/tracks')

  def __get_track_item(self, track_id: str) -> dict | None:
    return self.__get(f'/tracks/{track_id}') 
  
  def __get_track_analysis(self, track_id: str) -> dict:
    return self.__get(f'/audio-analysis/{track_id}')
  
  def __instantiate_playlist(self, data: dict):
    _id = data['id']
    _name = data['name']
    _images = data['images']
    return SpotifyPlaylist(
      id=_id,
      name=_name,
      images=_images
    )

  def __instantiate_track(self, data: dict):
    _data_track = data.get('track', data)
    _id = _data_track['id']
    _name = _data_track['name']
    _artist = ', '.join(artist['name'] for artist in _data_track['artists'])
    return SpotifyTrack(
      id=_id,
      name=_name,
      artist=_artist
    )
  
  def __set_track_analytics(self, track: SpotifyTrack, analytics: dict):
    track.set_analytics(
      key = analytics['track']['key'],
      mode = analytics['track']['mode'],
      tempo = analytics['track']['tempo']
    )

  def __iterate_all(self, url: str) -> Generator[dict, None, None]:
    while url:
      result = self.__get(url)
      for item in result['items']:
        yield item
      url = result['next']
      if url:
        url = url.replace(BASE_URLS['api'], '')

  # AUTH

  def authorize(self) -> None:
    auth_url = self.__get_authorization_url()
    auth_code = self.__get_authorization_code(auth_url)
    self.__fetch_user_credentials(auth_code)

  def __get_b64encoded_credentials(self) -> bytes:
    return b64encode((f'{self.client_id}:{self.client_secret}').encode('ascii')).decode('ascii')

  def _check_authorized(self) -> bool:
    return bool(self.refresh_token)

  def __store_refresh_token(self, token: str) -> None:
    with open(REFRESH_TOKEN_FP, mode='w', encoding='utf8') as f:
      f.write(token)
  
  def __get_stored_refresh_token(self) -> str | None:
    if not os.path.exists(REFRESH_TOKEN_FP):
      return
    with open(REFRESH_TOKEN_FP, mode='r', encoding='utf8') as f:
      return f.read().strip()
    
  def __set_refresh_token(self) -> None:
    self.refresh_token = self.__get_stored_refresh_token()
    
  def __get_authorization_url(self) -> str:
    url = f'{BASE_URLS["auth"]}/authorize'
    params = {
      'response_type': 'code',
      'client_id': self.client_id,
      'scope': ' '.join(SCOPES),
      'redirect_uri': self.redirect_uri,
    }
    url_parts = list(urlparse.urlparse(url))
    query = dict(urlparse.parse_qsl(url_parts[4]))
    query.update(params)
    url_parts[4] = urlencode(query)
    auth_url = urlparse.urlunparse(url_parts)
    return auth_url

  def __get_authorization_code(self, auth_url: str) -> str:
    chrome = webdriver.Chrome()
    chrome.get(auth_url)
    while True:
      if not chrome.current_url.startswith(self.redirect_uri):
        sleep(1)
        continue
      redirect_url = chrome.current_url
      chrome.close()
      break
    url_parts = list(urlparse.urlparse(redirect_url))
    query = dict(urlparse.parse_qsl(url_parts[4]))
    return query['code']

  def __fetch_user_credentials(self, code: str) -> None:
    data = self.__post(
      '/api/token',
      target='auth',
      data={
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': self.redirect_uri
      },
      headers={
        'Authorization': f'Basic {self.base_64}'
      }
    )
    self.access_token = data['access_token']
    self.refresh_token = data['refresh_token']
    self.__store_refresh_token(self.refresh_token)

  def _refetch_access_token(self) -> None:
    data = self.__post(
      '/api/token',
      target='auth',
      data={
        'grant_type': 'refresh_token',
        'refresh_token': self.refresh_token
      },
      headers={
        'Authorization': f'Basic {self.base_64}'
      }
    )
    self.access_token = data['access_token']
    self.refresh_token = data.get('refresh_token', self.refresh_token)
    self.__store_refresh_token(self.refresh_token)

  # HTTP

  def __get(self, endpoint, *, target: BaseUrlTarget = 'api', headers={}, params={}, data={}):
    return self.__request(
      endpoint,
      method='GET',
      data=data,
      params=params,
      headers=headers,
      target=target
    )

  def __post(self, endpoint, *, target: BaseUrlTarget = 'api', headers={}, params={}, data={}):
    return self.__request(
      endpoint,
      method='POST',
      data=data,
      params=params,
      headers=headers,
      target=target
    )

  def __put(self, endpoint, *, target: BaseUrlTarget = 'api', headers={}, params={}, data={}):
    return self.__request(
      endpoint,
      method='PUT',
      data=data,
      params=params,
      headers=headers,
      target=target
    )

  def __delete(self, endpoint, *, target: BaseUrlTarget = 'api', headers={}, params={}, data={}):
    return self.__request(
      endpoint,
      method='DELETE',
      data=data,
      params=params,
      headers=headers,
      target=target
    )
  
  @Decorators.validator
  def __request(self, endpoint, *, method=Literal['GET', 'POST', 'PUT', 'DELETE'], target: BaseUrlTarget = 'api', headers={}, params={}, data={}) -> dict | list | None:
    base_url = self.__get_base_url(target)
    self.__validate_endpoint_syntax(endpoint)
    r = requests.request(
      method=method,
      url=base_url+endpoint,
      **self.__set_request_kwargs(params=params, data=data, headers=headers, target=target)
    )
    return self.__parse_res_json(r)
  
  def __get_base_url(self, target: BaseUrlTarget) -> str:
    options = list(BASE_URLS.keys())
    if target not in options:
      raise TypeError(f'Target "{target}" it invalid. Allowed options: {options}')
    return BASE_URLS[target]
  
  def __validate_endpoint_syntax(self, endpoint: str):
    if not endpoint.startswith('/'):
      raise SyntaxError('Endpoint must start with forward slash')
  
  def __set_request_kwargs(self, *, params={}, data={}, headers={}, target: BaseUrlTarget) -> dict:
    kwargs = {}
    if params:
      kwargs['params'] = params
    if headers:
      kwargs['headers'] = headers
    else:
      headers = self.__get_default_json_headers()
      kwargs['headers'] = headers
    if data:
      if headers.get('Content-Type') == 'application/json':
        data = data if target == 'auth' else json.dumps(data)
      kwargs['data'] = data
    return kwargs
  
  def __get_default_json_headers(self) -> dict[str, str]:
    return {
      'Content-Type': 'application/json',
      'Authorization': f'Bearer {self.access_token}'
    }
  
  def __combine_headers_with_default(self, headers: dict) -> dict[str, str]:
    return {**self.__get_default_json_headers(), **headers}

  def __parse_res_json(self, response: requests.Response) -> dict[str, str] | list | None:
    try:
      data: dict[str, str] = response.json()
    except json.JSONDecodeError:
      return
    if type(data) is dict and data.get('error', {}).get('message') == 'Error parsing JSON.':
      data = json.loads(response.content)
    return data
