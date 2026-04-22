import hashlib
import json


def make_signature(value):
    return hashlib.md5(json.dumps(value, sort_keys=True).encode()).hexdigest()
