import asyncio


class EventEmitter:
    """Bridges events produced in the (synchronous, background-thread) loop
    to WebSocket clients on the FastAPI event loop."""

    def __init__(self):
        self._connections: set = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket) -> None:
        self._connections.discard(websocket)

    def emit(self, event: dict) -> None:
        """Thread-safe: safe to call from the background thread running the loop."""
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._broadcast(event), self._loop)

    async def _broadcast(self, event: dict) -> None:
        dead = []
        for ws in list(self._connections):
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)


emitter = EventEmitter()
