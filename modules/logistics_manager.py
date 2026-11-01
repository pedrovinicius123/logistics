import math
import threading

from logistics.modules.logistics_node import LogisticsNode


class Manager:
    """Python fallback for planning colony-to-colony resource transfers."""

    def __init__(self, resources):
        self.resources = set(resources)
        self.nodes = {}
        self.snapshots = {}

    def add_node(self, node):
        if not isinstance(node, LogisticsNode):
            raise TypeError("node must be a LogisticsNode")
        self.nodes[id(node.planet)] = node

    def remove_node(self, planet):
        self.nodes.pop(id(planet), None)
        self.snapshots.pop(id(planet), None)

    def update_nodes(self):
        self.snapshots = {
            key: node.snapshot(self.resources)
            for key, node in self.nodes.items()
        }

    def plan_transfer(self, resource, cargo_capacity):
        if cargo_capacity <= 0:
            return None

        if resource not in self.resources:
            return None
        self.update_nodes()
        best_route = None
        best_imbalance = 0.0
        for source_key, source in self.nodes.items():
            available, _ = self.snapshots[source_key][resource]
            if available < cargo_capacity * 0.5:
                continue
            for destination_key, destination in self.nodes.items():
                if source_key == destination_key:
                    continue
                stored, capacity = self.snapshots[destination_key][resource]
                amount = min(cargo_capacity, available, capacity - stored)
                imbalance = available - stored
                if amount > 0 and imbalance > best_imbalance:
                    best_imbalance = imbalance
                    best_route = source.planet, destination.planet, amount
        return best_route


try:
    from ._logistics_manager import Manager as _CythonManager
except ModuleNotFoundError as error:
    if error.name != 'logistics.modules._logistics_manager':
        raise
else:
    Manager = _CythonManager


class LogisticsManager:
    """Keep civilian cargo ships available and balance colony resources."""

    def __init__(self, faction):
        self.faction = faction
        self.lock = threading.RLock()
        self._pending_transport_ids = {}
        self._nodes = {}
        self.node_manager = Manager({
            'Minerals', 'Food', 'Energy', 'Electronics',
            'Chemicals', 'Alloys', 'Research',
        })

    def _sync_nodes(self):
        current_planets = {
            id(planet): planet
            for planet in self.faction.colonies.values()
        }
        for key, node in list(self._nodes.items()):
            if key not in current_planets:
                self.node_manager.remove_node(node.planet)
                del self._nodes[key]
        for key, planet in current_planets.items():
            if key not in self._nodes:
                node = LogisticsNode(planet)
                self._nodes[key] = node
                self.node_manager.add_node(node)
        self.node_manager.update_nodes()

    def update(self):
        faction = self.faction
        self._sync_nodes()
        if faction.eliminated or not faction.colonies:
            return

        now = faction.game_state.time if faction.game_state else 0.0
        live_ship_ids = set(faction.ships)
        queued_ship_ids = self._queued_ship_ids()
        for ship_id, expiry in list(self._pending_transport_ids.items()):
            if ship_id in live_ship_ids:
                self._pending_transport_ids.pop(ship_id, None)
            elif now >= expiry and ship_id not in queued_ship_ids:
                self._pending_transport_ids.pop(ship_id, None)

        colony_count = len(faction.colonies)
        desired = min(4, max(1, math.ceil(colony_count / 3)))
        active = sum(
            1 for ship in faction.ships.values()
            if ship.alive and ship.design_key == 'transport'
        )
        in_flight = set(self._pending_transport_ids) | queued_ship_ids
        if active + len(in_flight) >= desired:
            return

        if faction.build_ship('transport'):
            ship_id = f"{faction.name[:3].upper()}-{faction._ship_counter:03d}"
            build_time = 4.0
            self._pending_transport_ids[ship_id] = (
                now + build_time * 2.0
            )

    def _queued_ship_ids(self):
        queued = set()
        for planet in self.faction.colonies.values():
            queue = planet.const_queue
            with queue.mutex:
                queued.update(
                    task['id'] for task in queue.queue
                    if task.get('design_key') == 'transport'
                )
        return queued

    def plan_transport_trip(self, resource, cargo_capacity):
        self._sync_nodes()
        return self.node_manager.plan_transfer(resource, cargo_capacity)

    def plan_delivery(self, resource, cargo, origin=None):
        if cargo <= 0:
            return None
        destinations = [
            planet for planet in self.faction.colonies.values()
            if planet is not origin
            and min(
                cargo,
                planet.storage_capacity.get(resource, 0.0)
                - planet.planet_resources.get(resource, 0.0),
            ) > 0
        ]
        if not destinations:
            return None
        return min(
            destinations,
            key=lambda planet: planet.planet_resources.get(resource, 0.0),
        )

    def load_cargo(self, ship, source, amount):
        with self.lock, source.lock:
            if source.faction is not self.faction:
                return False
            available = source.planet_resources.get(ship.resource, 0.0)
            loaded = min(amount, available, ship.cargo)
            if loaded <= 0:
                return False
            source.planet_resources[ship.resource] = available - loaded
            ship.load = loaded
            return True

    def deliver_cargo(self, ship, destination):
        with self.lock, destination.lock:
            if destination.faction is not self.faction:
                return 0.0
            stored = destination.planet_resources.get(ship.resource, 0.0)
            capacity = destination.storage_capacity.get(ship.resource, 0.0)
            delivered = min(ship.load, max(0.0, capacity - stored))
            destination.planet_resources[ship.resource] = stored + delivered
            ship.load -= delivered
            return delivered
