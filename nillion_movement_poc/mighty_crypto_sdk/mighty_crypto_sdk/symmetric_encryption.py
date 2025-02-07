import base64
from .tagged_secret_box import *

def raw_encrypt_symmetric(content: str, symmetric_key: str, datagram: JSONDatagram):
    secret_box = TaggedSecretBox(base64.b64decode(symmetric_key))
    return secret_box.encrypt(datagram, content)

def encrypt_symmetric(content: str, symmetric_key: str, datagram: JSONDatagram):
    return base64.b64encode(raw_encrypt_symmetric(content, symmetric_key, datagram))

def raw_decrypt_symmetric(message: bytes, symmetric_key: str, datagram: JSONDatagram):
    secret_box = TaggedSecretBox(base64.b64decode(symmetric_key))
    return secret_box.decrypt(datagram, message)

def decrypt_symmetric(message: str, symmetric_key: str, datagram: JSONDatagram):
    return raw_decrypt_symmetric(base64.b64decode(message), symmetric_key, datagram)
