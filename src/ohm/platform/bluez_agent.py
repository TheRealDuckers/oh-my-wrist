# NOTE: do NOT add "from __future__ import annotations" to this file.
# dbus_next infers D-Bus type signatures from __annotations__ at runtime.
# The future import makes all annotations lazy strings, which breaks
# dbus_next's introspection (it sees "'s'" instead of "s", etc.).

"""
bluez_agent.py — BlueZ NoInputNoOutput pairing agent via dbus_next.

Registers a persistent D-Bus agent on the system bus that auto-accepts
all BLE pairing requests. Required on Linux so the Garmin watch can
complete pairDevice() without user interaction.

The agent interface is org.bluez.Agent1:
  https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc/agent-api.txt
"""

from loguru import logger


async def register_agent() -> object:
    """Register a NoInputNoOutput agent with BlueZ via dbus_next.

    Returns the open MessageBus connection — caller must keep it alive
    for the lifetime of the daemon (closing it unregisters the agent).

    Raises on failure so the caller can fall back to subprocess agent.
    """
    from dbus_next.aio import MessageBus
    from dbus_next.service import ServiceInterface, method
    from dbus_next.constants import BusType

    AGENT_PATH = "/org/bluez/OhMyWristAgent"

    class _NoInputNoOutputAgent(ServiceInterface):
        """Minimal BlueZ agent — accepts all pairing without user input."""

        def __init__(self):
            super().__init__("org.bluez.Agent1")

        @method()
        def Release(self) -> None:
            logger.debug("BlueZ agent: Release")

        @method()
        def AuthorizeService(self, device: "o", uuid: "s") -> None:
            logger.info("BlueZ agent: AuthorizeService dev={} uuid={}", device, uuid)

        @method()
        def RequestConfirmation(self, device: "o", passkey: "u") -> None:
            logger.info("BlueZ agent: auto-confirming passkey for {}", device)

        @method()
        def RequestAuthorization(self, device: "o") -> None:
            logger.info("BlueZ agent: auto-authorizing {}", device)

        @method()
        def Cancel(self) -> None:
            logger.debug("BlueZ agent: Cancel")

    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    agent = _NoInputNoOutputAgent()
    bus.export(AGENT_PATH, agent)

    introspection = await bus.introspect("org.bluez", "/org/bluez")
    proxy = bus.get_proxy_object("org.bluez", "/org/bluez", introspection)
    mgr = proxy.get_interface("org.bluez.AgentManager1")
    await mgr.call_register_agent(AGENT_PATH, "NoInputNoOutput")
    await mgr.call_request_default_agent(AGENT_PATH)

    logger.info("BlueZ: NoInputNoOutput agent registered ({})", AGENT_PATH)
    return bus
