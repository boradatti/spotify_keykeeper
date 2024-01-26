import os

from dotenv import load_dotenv

from tools.spotify import SpotifyAPI, REFRESH_TOKEN_FP
from tools.db import SQLite, DB_FP
from tools.prompter import PLAYLIST_IDS_FP
from utils.vars import DATA_DIRPATH


def load_env():
  ENV = '.env' # committed
  ENV_LOCAL = '.env.local' # ignored

  env_local = os.path.join(os.path.dirname(__file__), '..', ENV_LOCAL)
  if os.path.exists(env_local):
    load_dotenv(env_local, override=True)
    return
  
  env = os.path.join(os.path.dirname(__file__), '..', ENV)
  load_dotenv(env, override=True)

def init_spotify() -> SpotifyAPI:
  load_env()
  SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
  SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
  SPOTIFY_REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI')
  return SpotifyAPI(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET,
    redirect_uri= SPOTIFY_REDIRECT_URI
  )

def check_setup() -> bool:
  paths = [DATA_DIRPATH, PLAYLIST_IDS_FP, DB_FP, REFRESH_TOKEN_FP]
  for path in paths:
    if not os.path.exists(path):
      return False
  return True

def setup_db():
  with SQLite() as sql:
    sql.initialize()

def setup_spotify():
  spotify = init_spotify()
  spotify.authorize()

def setup_playlist_file():
  if not os.path.exists(PLAYLIST_IDS_FP):
    with open(PLAYLIST_IDS_FP, mode='w', encoding='utf8') as f:
      f.write('')

def create_datadir():
  os.makedirs(DATA_DIRPATH, exist_ok=True)

def run_setup() -> None:
  print('Your setup it incomplete\nRunning setup...')
  create_datadir()
  setup_db()
  setup_playlist_file()
  setup_spotify()
  print(f'Setup complete. You can rerun the script, but first make sure to add some playlist IDs to {PLAYLIST_IDS_FP}')
  quit()
