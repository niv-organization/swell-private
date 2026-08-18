ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"

def encode(num):
    if num == 0:
        return ALPHABET[0]
    out = ""
    base = len(ALPHABET)
    while num > 0:
        out = ALPHABET[num % base] + out
        num //= base
    return out
