"""Space-efficient probabilistic membership filter."""

import hashlib
import math


class BloomFilter:
    def __init__(self, expected_items, false_positive_rate=0.01):
        self.size = self._optimal_size(expected_items, false_positive_rate)
        self.hash_count = self._optimal_hashes(self.size, expected_items)
        self._bits = bytearray(self.size // 8 + 1)
        self._count = 0

    def add(self, item):
        for i in range(self.hash_count):
            index = self._hash(item, i)
            self._bits[index // 8] |= (1 << (index % 8))
        self._count += 1

    def might_contain(self, item):
        for i in range(self.hash_count):
            index = self._hash(item, i)
            if not (self._bits[index // 8] & (1 << (index % 8))):
                return False
        return True

    def _hash(self, item, seed):
        digest = hashlib.md5(f"{seed}:{item}".encode()).hexdigest()
        return int(digest, 16) % self.size

    @staticmethod
    def _optimal_size(n, p):
        return int(-(n * math.log(p)) / (math.log(2) ** 2))

    @staticmethod
    def _optimal_hashes(m, n):
        return max(1, int((m / n) * math.log(2)))

    def estimated_fill_ratio(self):
        set_bits = sum(bin(b).count("1") for b in self._bits)
        return set_bits / self.size
