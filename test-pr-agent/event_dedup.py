class EventDeduplicator:
    def __init__(self):
        self.seen = set()

    def is_duplicate(self, event_id):
        if event_id in self.seen:
            return True
        self.seen.add(event_id)
        return False
