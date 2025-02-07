from abc import ABC, abstractmethod


class OraclesService(ABC):
    @abstractmethod
    def calculate_pair_price(self, src_token: str, dest_token: str):
        pass 