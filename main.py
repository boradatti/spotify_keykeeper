from tools.prompter import Prompter
from tools.handler import SpotifySQLHandler
from tools.db import SQLite
from utils.setup import init_spotify, check_setup, run_setup


def control_setup():
  if not check_setup():
    run_setup()

def main():
  control_setup()
  with SQLite() as sql:
    key, mode = Prompter.get_key_and_mode(sql)
    spotify = init_spotify()
    playlists = Prompter.get_playlists(spotify)
    handler = SpotifySQLHandler(spotify=spotify, sql=sql)
    handler.iterate_playlists(key=key, mode=mode, playlists=playlists)


if __name__ == '__main__':
  main()
