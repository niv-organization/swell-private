"""Trie-based URL path router for a lightweight web framework."""


class RouteNode:
    def __init__(self):
        self.children = {}
        self.handler = None
        self.param_name = None


class TrieRouter:
    def __init__(self):
        self._root = RouteNode()

    def add(self, path, handler):
        node = self._root
        for segment in path.strip("/").split("/"):
            if segment.startswith(":"):
                key = ":param"
                if key not in node.children:
                    node.children[key] = RouteNode()
                node.children[key].param_name = segment[1:]
                node = node.children[key]
            else:
                if segment not in node.children:
                    node.children[segment] = RouteNode()
                node = node.children[segment]
        node.handler = handler

    def match(self, path):
        node = self._root
        params = {}
        for segment in path.strip("/").split("/"):
            if segment in node.children:
                node = node.children[segment]
            elif ":param" in node.children:
                node = node.children[":param"]
                params[node.param_name] = segment
            else:
                return None, {}
        return node.handler, params

    def has_route(self, path):
        handler, _ = self.match(path)
        return handler is not None
