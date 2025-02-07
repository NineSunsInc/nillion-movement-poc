import varint
from typing import List

def utf8_string_to_bytes(data: str) -> bytes:
    """
    Convert a UTF-8 string to a byte array.

    :param data: The input string.
    :return: The encoded byte array.
    """
    return data.encode(encoding='utf-8')

def utf8_bytes_to_string(data: bytes) -> str:
    """
    Convert a byte array to a UTF-8 string.

    :param data: The input byte array.
    :return: The decoded string.
    """
    return data.decode('utf-8')

def concat_uint8_arrays(*u8s: List[bytes]) -> bytearray:
    """
    Concatenate multiple byte arrays into a single byte array.

    :param u8s: A variable number of byte arrays.
    :return: A single concatenated byte array.
    """
    total_len = sum(len(u8) for u8 in u8s)

    result = bytearray(total_len)

    index = 0
    for u8 in u8s:
        result[index:index+len(u8)] = u8
        index += len(u8)

    return result

def varint_prefixed(data: bytes) -> bytearray:
    """
    Prefix the given byte array with its length encoded as a varint.

    :param data: The input byte array.
    :return: A new byte array prefixed with the varint-encoded length.
    """
    length_encoded = varint.encode(len(data))
    return concat_uint8_arrays(length_encoded, data)

def extract_varint_prefixed(o): 
    """
        o: {"bs": data}
    """
    chunk_len = varint.decode_bytes(o["bs"])
    chunk_len_len = encoding_length(chunk_len)
    chunk = o["bs"][chunk_len_len:chunk_len_len + chunk_len]

    o["bs"] = o["bs"][chunk_len_len + chunk_len:]

    return chunk

def encoding_length(value):
    N1 = 2 ** 7
    N2 = 2 ** 14
    N3 = 2 ** 21
    N4 = 2 ** 28
    N5 = 2 ** 35
    N6 = 2 ** 42
    N7 = 2 ** 49
    N8 = 2 ** 56
    N9 = 2 ** 63

    if value < N1:
        return 1
    elif value < N2:
        return 2
    elif value < N3:
        return 3
    elif value < N4:
        return 4
    elif value < N5:
        return 5
    elif value < N6:
        return 6
    elif value < N7:
        return 7
    elif value < N8:
        return 8
    elif value < N9:
        return 9
    else:
        return 10
