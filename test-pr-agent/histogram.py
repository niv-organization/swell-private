class Histogram:
    def __init__(self, buckets):
        self.buckets = sorted(buckets)
        self.counts = [0] * (len(buckets) + 1)

    def observe(self, value):
        for i, edge in enumerate(self.buckets):
            if value <= edge:
                self.counts[i] += 1
                return
        self.counts[-1] += 1
