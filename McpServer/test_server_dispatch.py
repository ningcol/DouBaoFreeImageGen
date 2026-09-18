from __future__ import annotations

import asyncio
import enum
import importlib.util
import pathlib
import sys
import types
import unittest


class FakeState(enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class FakeConnectionClosedOK(Exception):
    pass


class FakeConnectionClosedError(Exception):
    pass


fake_websockets = types.ModuleType("websockets")
fake_websockets.State = FakeState
fake_websockets.WebSocketServer = object
fake_websockets.exceptions = types.SimpleNamespace(
    ConnectionClosedOK=FakeConnectionClosedOK,
    ConnectionClosedError=FakeConnectionClosedError,
)
sys.modules["websockets"] = fake_websockets

fake_fastmcp = types.ModuleType("fastmcp")
fake_fastmcp.FastMCP = object
fake_fastmcp.Context = object
sys.modules["fastmcp"] = fake_fastmcp

SERVER_PATH = pathlib.Path(__file__).with_name("server.py")
spec = importlib.util.spec_from_file_location("doubao_mcp_server", SERVER_PATH)
server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = server
spec.loader.exec_module(server)


class FakeWebSocket:
    def __init__(self, name: str):
        self.name = name
        self.state = FakeState.OPEN
        self.remote_address = (name, 1234)
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        if self.state != FakeState.OPEN:
            raise ConnectionError(f"{self.name} closed")
        self.sent.append(message)


class ClientPoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_round_robin_across_clients(self) -> None:
        context = server.AppContext()
        first_ws = FakeWebSocket("first")
        second_ws = FakeWebSocket("second")
        first = await context.register_client(first_ws)
        second = await context.register_client(second_ws)
        await context.update_client_capacity(first_ws, 1)
        await context.update_client_capacity(second_ws, 1)

        selected1 = await context.acquire_client(wait_timeout=0)
        self.assertIs(selected1, first)
        await context.release_client(selected1)

        selected2 = await context.acquire_client(wait_timeout=0)
        self.assertIs(selected2, second)
        await context.release_client(selected2)

    async def test_single_client_single_tab_remains_capacity_one(self) -> None:
        context = server.AppContext()
        ws = FakeWebSocket("legacy-single")
        client = await context.register_client(ws)
        await context.update_client_capacity(ws, 1)

        selected = await context.acquire_client(wait_timeout=0)
        blocked = await context.acquire_client(wait_timeout=0)

        self.assertIs(selected, client)
        self.assertIsNone(blocked)
        await context.release_client(selected)

        selected_again = await context.acquire_client(wait_timeout=0)
        self.assertIs(selected_again, client)
        await context.release_client(selected_again)

    async def test_one_client_can_expose_multiple_tab_slots(self) -> None:
        context = server.AppContext()
        ws = FakeWebSocket("one-client")
        client = await context.register_client(ws)
        await context.update_client_capacity(ws, 2)

        slot1 = await context.acquire_client(wait_timeout=0)
        slot2 = await context.acquire_client(wait_timeout=0)
        slot3 = await context.acquire_client(wait_timeout=0)

        self.assertIs(slot1, client)
        self.assertIs(slot2, client)
        self.assertIsNone(slot3)
        self.assertEqual(client.in_flight, 2)

        await context.release_client(slot1)
        await context.release_client(slot2)
        self.assertEqual(client.in_flight, 0)

    async def test_disconnect_fails_only_tasks_owned_by_that_client(self) -> None:
        context = server.AppContext()
        ws = FakeWebSocket("disconnecting")
        other_ws = FakeWebSocket("healthy")
        client = await context.register_client(ws)
        await context.register_client(other_ws)

        future = context.create_pending_task(client, "req-1")
        await context.unregister_client(ws)

        with self.assertRaises(ConnectionError):
            await future

        self.assertTrue(context.has_connected_client())
        snapshot = context.connection_snapshot()
        self.assertEqual(snapshot["client_count"], 1)

    async def test_request_id_routes_result_to_matching_task(self) -> None:
        context = server.AppContext()
        ws = FakeWebSocket("client")
        client = await context.register_client(ws)

        first = context.create_pending_task(client, "first")
        second = context.create_pending_task(client, "second")

        handled = context.resolve_task(ws, "second", ["image-2"])
        self.assertTrue(handled)
        self.assertEqual(await second, ["image-2"])
        self.assertFalse(first.done())

        context.remove_pending_task("first")
        first.cancel()

    async def test_browser_reported_availability_blocks_stale_reconnect_capacity(self) -> None:
        context = server.AppContext()
        ws = FakeWebSocket("reconnected")
        client = await context.register_client(ws)

        # Browser may reconnect while two tabs are still busy with requests from
        # the previous socket. Total ready tabs alone must not advertise them free.
        await context.update_client_capacity(ws, ready_tabs=2, available_tabs=0)
        self.assertEqual(client.available_slots, 0)
        self.assertIsNone(await context.acquire_client(wait_timeout=0))

        await context.update_client_capacity(ws, ready_tabs=2, available_tabs=1)
        selected = await context.acquire_client(wait_timeout=0)
        self.assertIs(selected, client)
        await context.release_client(selected)

    async def test_zero_ready_tabs_are_not_schedulable(self) -> None:
        context = server.AppContext()
        ws = FakeWebSocket("client")
        await context.register_client(ws)
        await context.update_client_capacity(ws, 0)

        selected = await context.acquire_client(wait_timeout=0)
        self.assertIsNone(selected)
        snapshot = context.connection_snapshot()
        self.assertEqual(snapshot["ready_tabs"], 0)
        self.assertEqual(snapshot["available_slots"], 0)


if __name__ == "__main__":
    unittest.main()
