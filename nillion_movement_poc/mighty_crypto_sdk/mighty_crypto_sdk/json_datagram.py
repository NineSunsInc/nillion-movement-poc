import json
from .utils import utf8_string_to_bytes, utf8_bytes_to_string
from semver_range import Range

class JSONDatagram:
    def __init__(self, type: str, version: str = "0.0.1", version_constraint: Range = Range("0.0.*")):
        # The version constraint is not used (currently)
        self.type = type
        self.version = version
        self.version_constraint = version_constraint

    def serialize(self, data) -> bytes:
        return utf8_string_to_bytes(json.dumps({"version":self.version, "type": self.type, "data": data},separators=(',', ':')))
        
    def deserialize(self, data: bytes) -> str:
        parsed = json.loads(utf8_bytes_to_string(data))

        return parsed["data"]