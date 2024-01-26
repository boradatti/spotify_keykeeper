
from typing import TypeVar, Generator

T = TypeVar('T')


def chunk_list(lst: list[T], n: int) -> Generator[list[T], None, None]:
  for i in range(0, len(lst), n):
    yield lst[i:i + n]