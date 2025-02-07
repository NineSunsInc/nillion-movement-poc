class DataAPIKeyError(Exception):
    """Raised when there's an issue with the Data API key"""
    pass

class NetworkError(Exception):
    """Raised when there's an issue with network operations"""
    pass

class DecryptionError(Exception):
    """Raised when there's an issue with data decryption"""
    pass