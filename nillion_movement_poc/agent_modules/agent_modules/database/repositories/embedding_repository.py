import os
import sqlite3
import sqlite_vec
import struct

from typing import Tuple, List
from langchain_text_splitters import CharacterTextSplitter, RecursiveJsonSplitter
from dotenv import load_dotenv

from agent_modules.database.repositories.base_repository import BaseRepository
from agent_modules.embedding.embedding_service import MiniLmEmbeddingService
from agent_modules.database.types.document import Document

class EmbeddingRepository(BaseRepository):
    def __init__(
        self,
        table_name: str,
        embedding_service: MiniLmEmbeddingService = None,
    ) -> None:
        super().__init__()
        self.table_name = table_name

        self.embedding_function = embedding_service if embedding_service else MiniLmEmbeddingService().get_service()
        self.embedding_length = 384 # This is the embedding length of minilm-l6-v2

        self.text_splitter = CharacterTextSplitter(separator=",", chunk_size=1000, chunk_overlap=50)
        self.json_splitter = RecursiveJsonSplitter(max_chunk_size=300, min_chunk_size=100)

        # TODO: How to provide the database connection?
        self.connection = self._initialize_sqlite3_conn() 
        self._create_table_if_not_exists()

    def insert_text(self, text: str, user_session_id: str, is_json_data: bool = False):
        # Get max id
        max_id = self.get_max_id()

        # Process data input
        data_input = self._process_data_input(text, user_session_id, is_json_data)
        self.connection.executemany(
            f"INSERT INTO {self.table_name}(text, user_session_id, text_embedding) "
            f"VALUES (?,?,?)",
            data_input,
        )
        self.connection.commit()

        results = self.connection.execute(
            f"SELECT rowid FROM {self.table_name} WHERE rowid > {max_id}"
        )

        return [row["rowid"] for row in results]

    def search(self, text: str, user_session_id: str, k: int) -> List[Document]:
        embedding = self.embedding_function.embed_query(text)
        sql_query = f"""
            SELECT 
                e.rowid,
                text,
                distance
            FROM {self.table_name} AS e
            INNER JOIN {self.table_name}_vec AS v on v.rowid = e.rowid  
            WHERE
                v.text_embedding MATCH ?
                AND v.user_session_id = ?
                AND k = ?
            ORDER BY distance
        """
        cursor = self.connection.cursor()

        data_input = [self._serialize_f32(embedding), user_session_id, k]

        cursor.execute(
            sql_query,
            data_input
        )
        results = cursor.fetchall()

        documents = []
        for row in results:
            doc = Document(row["rowid"], row["text"])
            documents.append((doc, row["distance"]))

        return documents

    def get_max_id(self) -> int:
        max_id = self.connection.execute(
            f"SELECT max(rowid) as rowid FROM {self.table_name}"
        ).fetchone()
        
        max_id = max_id["rowid"]
    
        if max_id is None:  # no text added yet
            max_id = 0
        
        return max_id

    def _initialize_sqlite3_conn(self):
        connection = sqlite3.connect(self.db_file, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)

        # Print the sqlite-vec version
        # vec_version, = connection.execute("select vec_version()").fetchone()
        # print(f"vec_version={vec_version}")

        return connection

    def _serialize_f32(self, vector: List[float]) -> bytes:
        """Serializes a list of floats into a compact "raw bytes" format

        Source: https://github.com/asg017/sqlite-vec/blob/21c5a14fc71c83f135f5b00c84115139fd12c492/examples/simple-python/demo.py#L8-L10
        """
        return struct.pack("%sf" % len(vector), *vector)

    def _create_table_if_not_exists(self) -> None:
        self.connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name}
            (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                user_session_id TEXT,
                text TEXT,
                text_embedding BLOB
            )
            ;
            """
        )
        self.connection.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {self.table_name}_vec USING vec0(
                rowid INTEGER PRIMARY KEY,
                user_session_id TEXT,
                text_embedding float[{self.embedding_length}]
            )
            ;
            """
        )
        self.connection.execute(
            f"""
                CREATE TRIGGER IF NOT EXISTS embed_{self.table_name}_text
                AFTER INSERT ON {self.table_name}
                BEGIN
                    INSERT INTO {self.table_name}_vec(rowid, user_session_id, text_embedding)
                    VALUES (new.rowid, new.user_session_id, new.text_embedding) 
                    ;
                END;
            """
        )
        self.connection.commit()
    
    def _process_data_input(self, text: str, user_session_id: str, is_json_data: bool) -> List[Tuple[str, bytes]]:
        # split text into chunks
        texts = self.json_splitter.split_text(text, ensure_ascii=False) if is_json_data else self.text_splitter.split_text(text) 
        embeds = self.embedding_function.embed_documents(list(texts))
        data_input = [
            (text, user_session_id, self._serialize_f32(embed))
            for text, embed in zip(texts, embeds)
        ]

        return data_input