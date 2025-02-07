from .utils import concat_uint8_arrays, varint_prefixed, utf8_string_to_bytes, utf8_bytes_to_string, extract_varint_prefixed

METADATA_VERSION = "0.1.0"

class AADMeta:
    def __init__(self, version: str, type: str, nonce: bytearray) -> None:
        self.version = version
        self.type = type
        self.nonce = nonce
        self.METADATA_VERSION = "0.1.0"

    def serialize(self):
        """
            A serialized AAD header contains four pieces of information:
            - version of the metadata format
            - version of the encrypted object
            - type name of the encrypted object
            - nonce used for the encryption scheme

            It is composed of several varint-prefixed Uint8Arrays, which is then itself expressed as a
            varint-prefixed byte array.

            It looks like this on the wire:
            NNxxxxxxxxxxxxxxxxxxxxxxxxx...
              AAxx...BBxx...CCxx...DDxx...

            where AA, BB, CC, DD, and NN are varint-encoded (1-10 bytes long) and express the number of bytes following
            that indicator which comprise that field.

            - AAxxx is the prefixed metadata format version
            - BBxxx is the prefixed object version
            - CCxxx is the prefixed typename
            - DDxxx is the prefixed nonce. Length is prefixed instead of static to allow for multiple envelope types.
            
            - NNxxx is the prefixed length of those four strings concatenated together.
        """
        data = concat_uint8_arrays(
            varint_prefixed(utf8_string_to_bytes(METADATA_VERSION)),
            varint_prefixed(utf8_string_to_bytes(self.version)),
            varint_prefixed(utf8_string_to_bytes(self.type)),
            varint_prefixed(self.nonce)
        )

        return varint_prefixed(data)
    
    def deserialize(data):
        header = extract_varint_prefixed({"bs": data})

        raw_metadata = varint_prefixed(header)
        content = data[len(raw_metadata):]

        header_buf = {"bs": header}

        metadata_version = utf8_bytes_to_string(extract_varint_prefixed(header_buf))
        if (metadata_version != METADATA_VERSION):
            raise Exception("Unrecognized metadata version")
        
        metadata = AADMeta(
            version = utf8_bytes_to_string(extract_varint_prefixed(header_buf)),
            type = utf8_bytes_to_string(extract_varint_prefixed(header_buf)),
            nonce = extract_varint_prefixed(header_buf)
        )

        if (len(header_buf["bs"]) != 0):
            raise Exception("Unexpected additional content in header")
        
        return {
            "metadata": metadata,
            "raw_metadata": raw_metadata,
            "content": content
        }
