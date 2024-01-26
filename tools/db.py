import sqlite3
from functools import wraps
from dataclasses import dataclass, field

from utils.vars import DATA_DIRPATH

DB_FP = f'{DATA_DIRPATH}/sqlite.db'
KEYS = [
  (0, 'C'), (1, 'C#'),
  (2, 'D'), (3, 'D#'),
  (4, 'E'),
  (5, 'F'), (6, 'F#'),
  (7, 'G'), (8, 'G#'),
  (9, 'A'), (10, 'A#'),
  (11, 'B')
]
MODES = [
  (0, 'Minor'), (1, 'Major')
]

@dataclass
class SQLKeyMode:
  id: int
  name: str

  def __repr__(self):
    return self.name
  
@dataclass
class SQLCollection:
  id: str
  playlist_id: str
  key: int
  mode: int

@dataclass
class SQLTrack:
  id: str
  tempo: float

  def __eq__(self, other: 'SQLTrack | str') -> bool:
    if isinstance(other, SQLTrack) or hasattr(other, 'id'):
      return self.id == other.id
    if isinstance(other, str):
      return self.id == other
    
@dataclass
class SQLTrackAnalytics:
  key: int
  mode: int
  tempo: float


@dataclass
class SQLite:
  connection: sqlite3.Connection = field(init=False)

  class Decorators:
    @classmethod
    def handle_commit(_, func):
      @wraps(func)
      def inner(*args, **kwargs):
        this: SQLite = args[0]
        result = func(*args, **kwargs)
        this.connection.commit()
        return result
      return inner

  def __enter__(self) -> 'SQLite':
    self.__open_connection()
    self.__enable_foreign_keys()
    return self
  
  def __exit__(self, *_):
    self.__close_connection()

  def __open_connection(self):
    self.connection = sqlite3.connect(DB_FP)

  def __close_connection(self):
    self.connection.close()

  # QUERIES
    
  @Decorators.handle_commit
  def add_collection(self, *, collection_id: str, playlist_id: str, key: int, mode: int) -> None:
    self.connection.execute('''
      INSERT INTO collections (id, playlist_id, key, mode)
      VALUES (?, ?, ?, ?)
    ''', [collection_id, playlist_id, key, mode])
    
  @Decorators.handle_commit
  def delete_collection(self, collection_id: str) -> None:
    self.connection.execute('''
      DELETE FROM collections
      WHERE id = ?
    ''', [collection_id])
    
  def get_collection_by_data(self, *, playlist_id: str, key: int, mode: int) -> SQLCollection | None:
    c = self.connection.execute('''
      SELECT id FROM collections
      WHERE playlist_id = ?
      AND key = ? AND mode = ?
    ''', (playlist_id, key, mode))
    result = c.fetchone()
    if result:
      return SQLCollection(result[0], playlist_id, key, mode)
  
  def get_track_by_collection(self, *, track_id: str, collection_id: str) -> SQLTrack | None:
    c = self.connection.execute('''
      SELECT id, tempo FROM tracks
      WHERE id = ? AND collection_id = ?
    ''', [track_id, collection_id])
    if result := c.fetchone():
      _id, tempo = result
      return SQLTrack(_id, tempo)
  
  def get_track_analytics(self, track_id: str) -> SQLTrackAnalytics | None:
    c = self.connection.execute('''
      SELECT key, mode, tracks.tempo FROM collections
      INNER JOIN tracks ON collections.id = tracks.collection_id
      WHERE tracks.id = ?
    ''', [track_id])
    result = c.fetchone()
    return SQLTrackAnalytics(*result) if result else None
  
  def get_all_keys(self) -> list[SQLKeyMode]:
    c = self.connection.execute('SELECT id, name FROM keys')
    return [SQLKeyMode(id, name) for (id, name) in c.fetchall()]
  
  def get_all_modes(self) -> list[SQLKeyMode]:
    c = self.connection.execute('SELECT id, name FROM modes')
    return [SQLKeyMode(id, name) for (id, name) in c.fetchall()]
  
  @Decorators.handle_commit
  def add_track(self, *, track_id: str, collection_id: str, tempo: float) -> None:
    self.connection.execute('''
      INSERT INTO tracks (id, collection_id, tempo)
      VALUES (?, ?, ?)
    ''', [track_id, collection_id, tempo])

  # INITIALIZING DATABASE

  @Decorators.handle_commit
  def initialize(self):
    self.__prepare_tables()

  def __enable_foreign_keys(self):
    self.connection.execute('PRAGMA foreign_keys = ON')

  def __prepare_tables(self):
    self.__prepare_keys_table()
    self.__prepare_modes_table()
    self.__prepare_collections_table()
    self.__prepare_tracks_table()

  def __prepare_keys_table(self):
    self.connection.execute('''
      CREATE TABLE IF NOT EXISTS keys (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
      )           
    ''')
    self.connection.executemany('''
      INSERT OR IGNORE INTO keys (id, name)
      VALUES (?, ?)
    ''', KEYS)

  def __prepare_modes_table(self):
    self.connection.execute('''
      CREATE TABLE IF NOT EXISTS modes (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
      )           
    ''')
    self.connection.executemany('''
      INSERT OR IGNORE INTO modes (id, name)
      VALUES (?, ?)
    ''', MODES)

  def __prepare_collections_table(self):
    self.connection.execute('''
      CREATE TABLE IF NOT EXISTS collections (
        id TEXT PRIMARY KEY,
        playlist_id TEXT NOT NULL,
        key INTEGER NOT NULL,
        mode INTEGER NOT NULL,
                            
        FOREIGN KEY (key) REFERENCES keys(id)
        FOREIGN KEY (mode) REFERENCES modes(id)
      )
    ''')
    self.connection.execute('''
      CREATE UNIQUE INDEX IF NOT EXISTS playlist_key_mode
      ON collections (playlist_id, key, mode)
    ''')

  def __prepare_tracks_table(self):
    self.connection.execute('''
      CREATE TABLE IF NOT EXISTS tracks (
        id TEXT PRIMARY KEY,
        collection_id TEXT,
        tempo REAL NOT NULL,
                            
        FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE
      )
    ''')
