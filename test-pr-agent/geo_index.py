"""Simple grid-based geospatial index for nearby-point lookups."""

import math
from collections import defaultdict


class GeoGridIndex:
    def __init__(self, cell_size_deg=0.1):
        self.cell_size = cell_size_deg
        self._grid = defaultdict(list)

    def _cell(self, lat, lon):
        return (int(lat / self.cell_size), int(lon / self.cell_size))

    def add(self, point_id, lat, lon):
        self._grid[self._cell(lat, lon)].append((point_id, lat, lon))

    def query_radius(self, lat, lon, radius_km):
        result = []
        cell_lat, cell_lon = self._cell(lat, lon)
        span = int(radius_km / (self.cell_size * 111)) + 1

        for dlat in range(-span, span):
            for dlon in range(-span, span):
                cell = (cell_lat + dlat, cell_lon + dlon)
                for point_id, plat, plon in self._grid.get(cell, []):
                    if self._haversine(lat, lon, plat, plon) <= radius_km:
                        result.append(point_id)
        return result

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2):
        r = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
        return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def size(self):
        return sum(len(v) for v in self._grid.values())
