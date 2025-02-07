# Standard library imports
import os
from dataclasses import dataclass

# Third-party imports
import chainlit as cl
from dotenv import load_dotenv
import aiohttp

# Nine Suns SDK imports
from mighty_crypto_sdk.asymmetric_encryption import string_decrypt_asymmetric
from mighty_crypto_sdk.symmetric_encryption import decrypt_symmetric
from mighty_crypto_sdk.json_datagram import JSONDatagram

# Local imports
from agent_modules.exception.exceptions import DecryptionError

@dataclass
class EncryptedData:
    encrypted_data: str
    encrypted_key: str

class DataService:
    def __init__(self):
        load_dotenv()
        self.api_public_key = os.getenv("API_KEY_PUBLIC_KEY")
        self.api_private_key = os.getenv("API_KEY_PRIVATE_KEY")
        self.ninesuns_url = os.getenv("NINE_SUNS_SDK_URL")

    async def get_and_decrypt_data(self, data_api_key: str) -> dict:
        try:
            encrypted_data = await self._get_data_by_api_key(data_api_key)
            await self._log_encrypted_data(encrypted_data.encrypted_data)
            
            decrypted_data = self._decrypt_data(encrypted_data)
            await cl.Message(content="Successfully decrypt private data!").send()
            
            return decrypted_data
        except Exception as e:
            raise DecryptionError(f"Failed to decrypt data: {str(e)}")

    async def _get_data_by_api_key(self, api_key: str) -> EncryptedData:
        async with aiohttp.ClientSession() as session:
            headers = {
                "x-api-key": api_key,
                "User-Agent": "Mozilla/5.0"
            }
            async with session.get(self.ninesuns_url, headers=headers) as response:
                object_response = await response.json()
                return EncryptedData(
                    object_response["encrypted_data"],
                    object_response["public_key_encrypted_key"]
                )

    def _decrypt_data(self, encrypted_data: EncryptedData) -> dict:
        symmetric_key = string_decrypt_asymmetric(
            self.api_private_key, 
            self.api_public_key, 
            encrypted_data.encrypted_key
        )
        
        return decrypt_symmetric(
            encrypted_data.encrypted_data,
            symmetric_key,
            JSONDatagram("User Shared Encrypted Data Datagram")
        )

    async def _log_encrypted_data(self, encrypted_data: str):
        await cl.Message(content=f"Your encrypted data: {encrypted_data}").send()