"""Short-code generator and resolver for a URL shortener service."""

import string

ALPHABET = string.ascii_letters + string.digits
BASE = len(ALPHABET)


def encode_id(num):
    """Encode a positive integer id into a short base-62 code."""
    if num == 0:
        return ALPHABET[0]
    chars = []
    while num > 0:
        chars.append(ALPHABET[num % BASE])
        num //= BASE
    return "".join(chars)


def decode_code(code):
    """Decode a short code back into its integer id."""
    num = 0
    for char in code:
        num = num * BASE + ALPHABET.index(char)
    return num


class UrlStore:
    def __init__(self, repo):
        self._repo = repo

    def shorten(self, long_url):
        record_id = self._repo.insert(long_url)
        return encode_id(record_id)

    def resolve(self, code):
        record_id = decode_code(code)
        record = self._repo.get(record_id)
        return record["long_url"]
