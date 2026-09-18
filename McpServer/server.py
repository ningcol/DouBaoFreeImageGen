import asyncio
import json
import logging
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import websockets
from fastmcp import Context, FastMCP


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SERVER_HOST = "0.0.0.0"
WS_PORT = 8080
MCP_PORT = 8081
TASK_TIMEOUT_SECONDS = 90
CLIENT_SLOT_WAIT_SECONDS = 15


@dataclass(eq=False)
class ClientState:
    websocket: Any
    client_id: str
    ready_tabs: int = 1
    in_flight: int = 0

    @property
    def available_slots(self) -> int:
        return max(self.ready_tabs - self.in_flight, 0)


@dataclass
class PendingTask:
    client: ClientState
    future: asyncio.Future


@dataclass
class AppContext:
    """Shared state for connected browser clients and in-flight drawing tasks."""

    clients: List[ClientState] = field(default_factory=list)
    pending_tasks: Dict[str, PendingTask] = field(default_factory=dict)
    round_robin_index: int = 0
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)

    def _client_for_websocket(self, websocket) -> Optional[ClientState]:
        return next(
            (client for client in self.clients if client.websocket is websocket),
            None,
        )

    def _websocket_is_open(self, websocket) -> bool:
        state = getattr(websocket, "state", None)
        if state is None:
            return True
        return state == websockets.State.OPEN

    async def register_client(self, websocket) -> ClientState:
        async with self.condition:
            existing = self._client_for_websocket(websocket)
            if existing is not None:
                return existing

            client = ClientState(
                websocket=websocket,
                client_id=f"client-{uuid.uuid4().hex[:8]}",
            )
            self.clients.append(client)
            self.condition.notify_all()
            logger.info(
                "Registered %s from %s (clients=%s)",
                client.client_id,
                getattr(websocket, "remote_address", None),
                len(self.clients),
            )
            return client

    async def unregister_client(self, websocket) -> None:
        async with self.condition:
            client = self._client_for_websocket(websocket)
            if client is None:
                return

            self.clients.remove(client)
            if self.clients:
                self.round_robin_index %= len(self.clients)
            else:
                self.round_robin_index = 0

            disconnected = [
                request_id
                for request_id, pending in self.pending_tasks.items()
                if pending.client is client
            ]
            for request_id in disconnected:
                pending = self.pending_tasks.pop(request_id)
                if not pending.future.done():
                    pending.future.set_exception(
                        ConnectionError(
                            f"{client.client_id} disconnected while processing {request_id}"
                        )
                    )

            self.condition.notify_all()
            logger.info(
                "Unregistered %s (clients=%s, cancelled_tasks=%s)",
                client.client_id,
                len(self.clients),
                len(disconnected),
            )

    async def update_client_capacity(self, websocket, ready_tabs: int) -> None:
        async with self.condition:
            client = self._client_for_websocket(websocket)
            if client is None:
                return
            client.ready_tabs = max(int(ready_tabs), 0)
            self.condition.notify_all()
            logger.info(
                "%s reports %s ready tab(s), %s in flight",
                client.client_id,
                client.ready_tabs,
                client.in_flight,
            )

    def has_connected_client(self) -> bool:
        return any(
            self._websocket_is_open(client.websocket)
            for client in self.clients
        )

    def connection_snapshot(self) -> dict:
        connected = [
            client
            for client in self.clients
            if self._websocket_is_open(client.websocket)
        ]
        return {
            "connected": bool(connected),
            "client_count": len(connected),
            "ready_tabs": sum(client.ready_tabs for client in connected),
            "available_slots": sum(client.available_slots for client in connected),
            "active_tasks": sum(client.in_flight for client in connected),
        }

    def _pick_available_client_locked(self) -> Optional[ClientState]:
        if not self.clients:
            return None

        size = len(self.clients)
        start = self.round_robin_index % size
        for offset in range(size):
            index = (start + offset) % size
            client = self.clients[index]
            if not self._websocket_is_open(client.websocket):
                continue
            if client.available_slots <= 0:
                continue

            client.in_flight += 1
            self.round_robin_index = (index + 1) % size
            return client

        return None

    async def acquire_client(
        self,
        wait_timeout: float = CLIENT_SLOT_WAIT_SECONDS,
    ) -> Optional[ClientState]:
        async with self.condition:
            client = self._pick_available_client_locked()
            if client is not None:
                return client

            if not self.has_connected_client():
                return None

            deadline = time.monotonic() + max(wait_timeout, 0)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None

                try:
                    await asyncio.wait_for(self.condition.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    return None

                client = self._pick_available_client_locked()
                if client is not None:
                    return client

                if not self.has_connected_client():
                    return None

    async def release_client(self, client: ClientState) -> None:
        async with self.condition:
            if client.in_flight > 0:
                client.in_flight -= 1
            self.condition.notify_all()

    def create_pending_task(
        self,
        client: ClientState,
        request_id: str,
    ) -> asyncio.Future:
        future = asyncio.get_running_loop().create_future()
        self.pending_tasks[request_id] = PendingTask(client=client, future=future)
        return future

    def remove_pending_task(self, request_id: str) -> None:
        self.pending_tasks.pop(request_id, None)

    def _legacy_pending_for_websocket(self, websocket) -> Optional[str]:
        for request_id, pending in self.pending_tasks.items():
            if pending.client.websocket is websocket:
                return request_id
        return None

    def resolve_task(
        self,
        websocket,
        request_id: Optional[str],
        urls: List[str],
    ) -> bool:
        request_id = request_id or self._legacy_pending_for_websocket(websocket)
        pending = self.pending_tasks.get(request_id) if request_id else None
        if pending is None or pending.client.websocket is not websocket:
            return False
        if not pending.future.done():
            pending.future.set_result(urls)
        return True

    def fail_task(
        self,
        websocket,
        request_id: Optional[str],
        message: str,
    ) -> bool:
        request_id = request_id or self._legacy_pending_for_websocket(websocket)
        pending = self.pending_tasks.get(request_id) if request_id else None
        if pending is None or pending.client.websocket is not websocket:
            return False
        if not pending.future.done():
            pending.future.set_exception(RuntimeError(message))
        return True

    async def execute_task(self, prompt: str) -> List[str]:
        if not self.has_connected_client():
            raise ConnectionError("No WebSocket client connected")

        deadline = time.monotonic() + TASK_TIMEOUT_SECONDS
        last_disconnect: Optional[Exception] = None

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            client = await self.acquire_client(
                wait_timeout=min(CLIENT_SLOT_WAIT_SECONDS, remaining)
            )
            if client is None:
                if not self.has_connected_client():
                    if last_disconnect is not None:
                        raise ConnectionError(str(last_disconnect))
                    raise ConnectionError("No WebSocket client connected")
                continue

            request_id = uuid.uuid4().hex
            future = self.create_pending_task(client, request_id)
            payload = json.dumps(
                {
                    "type": "draw",
                    "request_id": request_id,
                    "prompt": prompt,
                },
                ensure_ascii=False,
            )

            try:
                await send_to_client(client.websocket, payload)
                logger.info(
                    "Dispatched request %s to %s (tabs=%s, in_flight=%s)",
                    request_id,
                    client.client_id,
                    client.ready_tabs,
                    client.in_flight,
                )
                task_remaining = max(deadline - time.monotonic(), 0.1)
                urls = await asyncio.wait_for(future, timeout=task_remaining)
                return list(urls)
            except ConnectionError as exc:
                last_disconnect = exc
                logger.warning(
                    "Client %s disconnected during request %s; retrying another client",
                    client.client_id,
                    request_id,
                )
            finally:
                self.remove_pending_task(request_id)
                await self.release_client(client)

        raise TimeoutError("Timeout waiting for image generation result")


async def websocket_handler(websocket, app_context: AppContext):
    client = await app_context.register_client(websocket)
    logger.info("Client connected from %s as %s", websocket.remote_address, client.client_id)

    try:
        async for message in websocket:
            logger.info(
                "Received from %s: %s...",
                websocket.remote_address,
                message[:200],
            )
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                logger.warning("Received non-JSON message: %s...", message[:200])
                continue

            try:
                if not isinstance(data, dict):
                    logger.warning("Ignoring non-object client message: %r", data)
                    continue

                message_type = data.get("type")
                if message_type == "clientState":
                    ready_tabs = data.get("readyTabs", data.get("ready_tabs", 0))
                    await app_context.update_client_capacity(websocket, ready_tabs)
                    continue

                if message_type == "scriptReady":
                    await app_context.update_client_capacity(websocket, 1)
                    continue

                if message_type == "collectedImageUrls":
                    urls = data.get("urls") or []
                    handled = app_context.resolve_task(
                        websocket,
                        data.get("request_id"),
                        urls,
                    )
                    if not handled:
                        logger.warning(
                            "Image result did not match an active request: %s",
                            data.get("request_id"),
                        )
                    continue

                if message_type == "error":
                    handled = app_context.fail_task(
                        websocket,
                        data.get("request_id"),
                        data.get("message") or "Browser client reported an error",
                    )
                    if not handled:
                        logger.warning(
                            "Client error did not match an active request: %s",
                            data.get("request_id"),
                        )
                    continue

                logger.warning(
                    "Unknown message type received: %s - Data: %s",
                    message_type,
                    data,
                )
            except Exception as exc:
                logger.error("Error processing message: %s", exc, exc_info=True)

    except websockets.exceptions.ConnectionClosedOK:
        logger.info("Client disconnected cleanly")
    except websockets.exceptions.ConnectionClosedError as exc:
        logger.warning("Client disconnected with error: %s", exc)
    except Exception as exc:
        logger.error("Unexpected error in handler: %s", exc, exc_info=True)
    finally:
        await app_context.unregister_client(websocket)
        logger.info("Client handler ending")


async def send_to_client(websocket, message: str):
    state = getattr(websocket, "state", None)
    if state is not None and state != websockets.State.OPEN:
        raise ConnectionError(f"WebSocket is not open: {state}")
    try:
        await websocket.send(message)
    except Exception as exc:
        logger.error("Error sending to client: %s", exc, exc_info=True)
        raise ConnectionError(str(exc)) from exc


async def main_async():
    logger.info("Starting application: WebSocket and FastMCP services...")
    app_context = AppContext()

    mcp = FastMCP(
        name="WebSocketMCP",
        instructions=f"""
        This MCP instance provides tools to interact with the WebSocket layer.
        The WebSocket server listens on ws://{SERVER_HOST}:{WS_PORT}.
        The MCP server (HTTP) listens on http://{SERVER_HOST}:{MCP_PORT}.

        Drawing requests are dispatched across connected browser clients in
        round-robin order. A browser client may expose multiple ready Doubao
        tabs, allowing multiple drawing requests to run concurrently.
        """,
        json_response=True,
    )

    @mcp.tool()
    async def draw_image(ctx: Context, prompt: str) -> str:
        try:
            urls = await app_context.execute_task(prompt)
            return json.dumps(
                {"status": "success", "image_urls": urls},
                ensure_ascii=False,
            )
        except ConnectionError as exc:
            return json.dumps(
                {"status": "error", "message": str(exc)},
                ensure_ascii=False,
            )
        except RuntimeError as exc:
            return json.dumps(
                {"status": "error", "message": str(exc)},
                ensure_ascii=False,
            )
        except TimeoutError:
            return json.dumps(
                {
                    "status": "error",
                    "message": (
                        f"Timeout waiting for image generation result "
                        f"after {TASK_TIMEOUT_SECONDS} seconds"
                    ),
                },
                ensure_ascii=False,
            )

    @mcp.tool()
    def get_connection_status(ctx: Context) -> str:
        return json.dumps(
            app_context.connection_snapshot(),
            ensure_ascii=False,
        )

    ws_server = await websockets.serve(
        lambda websocket: websocket_handler(websocket, app_context),
        SERVER_HOST,
        WS_PORT,
    )
    logger.info("WebSocket server started on ws://%s:%s", SERVER_HOST, WS_PORT)

    mcp_server_task = asyncio.create_task(
        mcp.run_async(transport="streamable-http", host=SERVER_HOST, port=MCP_PORT)
    )
    logger.info("FastMCP server started on http://%s:%s", SERVER_HOST, MCP_PORT)

    server_tasks = [asyncio.create_task(ws_server.wait_closed()), mcp_server_task]

    try:
        await asyncio.gather(*server_tasks)
    except asyncio.CancelledError:
        logger.info("Application tasks were cancelled.")
    except Exception as exc:
        logger.error("An unexpected error occurred: %s", exc, exc_info=True)
    finally:
        logger.info("Application shutting down...")
        ws_server.close()
        await ws_server.wait_closed()
        logger.info("Application shutdown complete.")


def main():
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            logger.info("Using WindowsSelectorEventLoopPolicy on Windows.")
        except AttributeError:
            logger.warning(
                "WindowsSelectorEventLoopPolicy not available, using default."
            )

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Application interrupted by user (Ctrl+C).")
    except Exception as exc:
        logger.error("An error occurred: %s", exc, exc_info=True)


if __name__ == "__main__":
    main()
