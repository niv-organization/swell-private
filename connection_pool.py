"""Database connection pool with configurable size and timeout."""

import threading
import time
import queue
import uuid


class Connection:
    """Represents a database connection."""

    def __init__(self, host: str, port: int):
        self.id = str(uuid.uuid4())[:8]
        self.host = host
        self.port = port
        self.in_use = False
        self.created_at = time.time()

    def execute(self, query: str) -> dict:
        """Execute a query on this connection."""
        if not self.in_use:
            raise RuntimeError(f"Connection {self.id} is not checked out")
        # Simulate query execution
        time.sleep(0.01)
        return {"status": "ok", "connection": self.id, "query": query}

    def close(self):
        self.in_use = False


class ConnectionPool:
    """Thread-safe pool of reusable database connections."""

    def __init__(self, host: str, port: int, max_size: int = 10, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.max_size = max_size
        self.timeout = timeout
        self._pool: queue.Queue[Connection] = queue.Queue(maxsize=max_size)
        self._lock = threading.Lock()
        self._current_size = 0

    def _create_connection(self) -> Connection:
        conn = Connection(self.host, self.port)
        return conn

    def acquire(self) -> Connection:
        """Acquire a connection from the pool."""
        # Try to get an existing connection first
        try:
            conn = self._pool.get_nowait()
            conn.in_use = True
            return conn
        except queue.Empty:
            pass

        # Create a new connection if under limit
        with self._lock:
            if self._current_size < self.max_size:
                self._current_size += 1
                conn = self._create_connection()
                conn.in_use = True
                return conn

        # Wait for a connection to be returned
        try:
            conn = self._pool.get(timeout=self.timeout)
            conn.in_use = True
            return conn
        except queue.Empty:
            raise TimeoutError("Could not acquire connection from pool")

    def release(self, conn: Connection):
        """Return a connection back to the pool."""
        conn.in_use = False
        self._pool.put(conn)

    def execute_query(self, query: str) -> dict:
        """Convenience method: acquire a connection, run the query, return it."""
        conn = self.acquire()
        result = conn.execute(query)
        self.release(conn)
        return result
