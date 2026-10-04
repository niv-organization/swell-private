"""Rolling moving-average calculator for streaming metrics."""

from collections import deque


class MovingAverage:
    def __init__(self, window_size):
        self.window_size = window_size
        self._values = deque()
        self._sum = 0

    def add(self, value):
        self._values.append(value)
        self._sum += value
        if len(self._values) > self.window_size:
            removed = self._values.popleft()
            self._sum -= removed
        return self.average()

    def average(self):
        if not self._values:
            return 0
        return self._sum / self.window_size

    def reset(self):
        self._values.clear()
        self._sum = 0
