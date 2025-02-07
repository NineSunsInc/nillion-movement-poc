import base64
import nacl.secret
import nacl.utils
import nacl.public
import base64
from nacl.public import PrivateKey, PublicKey, Box
from .utils import utf8_bytes_to_string

def new_nonce():
    return nacl.utils.random(nacl.public.Box.NONCE_SIZE)

def string_decrypt_asymmetric(my_private_key, their_public_key, plain_text):
    try:
        my_private_key_bytes = base64.b64decode(my_private_key)
        their_public_key_bytes = base64.b64decode(their_public_key)
        my_private_key = PrivateKey(my_private_key_bytes)
        their_public_key = PublicKey(their_public_key_bytes)
        
        box = Box(my_private_key, their_public_key)
        
        shared_key = box.shared_key()
        
        # decrypt_asymmetric(shared_key, plain_text)
    except Exception as e:
        print(f"Error: {e}")

def decrypt_asymmetric(secret_or_shared_key, message_with_nonce):
    message_with_nonce_as_byte_array = base64.b64decode(message_with_nonce)
    nonce = message_with_nonce_as_byte_array[:nacl.secret.SecretBox.NONCE_SIZE]
    message = message_with_nonce_as_byte_array[nacl.secret.SecretBox.NONCE_SIZE:]
    
    decrypted = nacl.secret.SecretBox(secret_or_shared_key).decrypt(message, nonce)
    
    if not decrypted:
        raise ValueError("Could not decrypt message")
    
    decrypted_message = utf8_bytes_to_string(decrypted)
    return decrypted_message

def string_decrypt_asymmetric(my_private_key, their_public_key, encrypted_text):
    try:
        my_private_key_bytes = base64.b64decode(my_private_key)
        their_public_key_bytes = base64.b64decode(their_public_key)
        my_private_key = PrivateKey(my_private_key_bytes)
        their_public_key = PublicKey(their_public_key_bytes)
        
        box = Box(my_private_key, their_public_key)
        
        shared_key = box.shared_key()
        
        return decrypt_asymmetric(shared_key, encrypted_text)
    except Exception as e:
        raise e
    
def encrypt_asymmetric(secret_or_shared_key, msg_str):
        # Convert message to bytes
    message = msg_str.encode('utf-8')
    
    # Generate a nonce
    nonce = new_nonce()
    

    box = nacl.secret.SecretBox(secret_or_shared_key)
    encrypted_message = box.encrypt(message, nonce)
    
    # Concatenate nonce and encrypted message
    full_message = nonce + encrypted_message.ciphertext
    
    # Encode the result as base64
    encoded_message = base64.b64encode(full_message).decode('utf-8')
    print(f"encoded_message {encoded_message}")
    
    return encoded_message

def string_encrypt_asymmetric(my_private_key, their_public_key, plain_text):
    try:
        print(f"my_private_key {my_private_key}")
        print(f"their_public_key {their_public_key}")
        my_private_key_bytes = base64.b64decode(my_private_key)
        their_public_key_bytes = base64.b64decode(their_public_key)
        my_private_key = PrivateKey(my_private_key_bytes)
        their_public_key = PublicKey(their_public_key_bytes)
        
        box = Box(my_private_key, their_public_key)
        
        shared_key = box.shared_key()
        print("Shared Key", shared_key)
        
        encrypt_asymmetric(shared_key, plain_text)
    except Exception as e:
        print(f"Error: {e}")

