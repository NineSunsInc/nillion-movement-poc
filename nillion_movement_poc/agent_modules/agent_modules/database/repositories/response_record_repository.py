import json

from typing import List, Tuple
from agent_modules.database.repositories.base_repository import BaseRepository
from agent_modules.database.types.response_record import ResponseRecord


class ResponseRecordRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__()

        self.table_name = "response_records"
        self.connection = self._initialize_sqlite3_conn()
        self._create_table_if_not_exists()

    def insert_record(self, input: str, response: str, past_steps: List[Tuple], category: str, chain: str, expiration: int):
        query = f"INSERT INTO {self.table_name}(input, response, past_steps, category, chain, expiration) VALUES (?,?,?,?,?,?);"
        past_steps = json.dumps(past_steps)

        self.connection.execute(
            query,
            [input, response, past_steps, category, chain, expiration]
        )
        self.connection.commit()

    def delete_by_ids(self, ids: List[int]):
        id_list = "(" + ",".join(ids) + ")"
        delete_query = f"DELETE FROM {self.table_name} WHERE rowid in {id_list};"
        self.connection.execute(delete_query)
        self.connection.commit()

    def find_document_by_category_and_chain(self, category: str, chain: str) -> List[ResponseRecord]:
        query = f"SELECT * FROM {self.table_name} WHERE category = ? AND chain = ?;" 
        cursor = self.connection.cursor()
        cursor.execute(query, [category, chain])

        results = cursor.fetchall()
        responses = []

        for row in results:
            responses.append(ResponseRecord(row["id"], row["input"], row["response"], json.loads(row["past_steps"]), row["category"], row["chain"], row["expiration"]))

        return responses

    def _create_table_if_not_exists(self) -> None:
        self.connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name}
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                input TEXT,
                response TEXT,
                past_steps TEXT,
                category TEXT,
                chain TEXT,
                expiration INTEGER
            )
            ;
            """
        )
    