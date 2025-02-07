import sqlite3
import os

from dotenv import load_dotenv
from abc import ABC, abstractmethod


class BaseRepository(ABC):
    def __init__(self) -> None:
        load_dotenv()
        self.db_file = "./sqlite-vec-db/vec.db"

    def _initialize_sqlite3_conn(self):
        connection = sqlite3.connect(self.db_file, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        
        return connection
    
    @abstractmethod
    def _create_table_if_not_exists(self) -> None:
        pass