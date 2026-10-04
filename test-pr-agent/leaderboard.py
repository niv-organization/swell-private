class Leaderboard:
    def __init__(self):
        self.scores = {}

    def submit(self, player, score):
        self.scores[player] = max(self.scores.get(player, 0), score)

    def top(self, n):
        ranked = sorted(self.scores.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:n]
