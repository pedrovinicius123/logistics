import math
import threading
from functools import reduce

from logistics.modules.logistics_node import LogisticsNode


TRADABLE_RESOURCES = ('Food', 'Minerals', 'Energy', 'Electronics',
                      'Chemicals', 'Alloys')

MAX_TRANSPORTS = 8             # frota que um império pequeno mantém por padrão
MAX_TRANSPORTS_CEILING = 16    # teto absoluto da frota civil
OVERLOAD_RATIO = 1.25          # deficit/rotina que dispara o aviso
MIN_RUN_PAYLOAD = 5.0          # carga mínima para uma viagem valer o voo
AWAITING_BUILD_WEIGHT = 2.0    # colônia com obra parada puxa transporte
BUILD_DELIVERY_YEARS = 2.0     # prazo estimado para suprir uma obra
# Dimensões de um transporte padrão; servem de régua quando a frota está vazia.
REFERENCE_CARGO = 500.0
REFERENCE_SPEED = 5.0
# Histerese: o aviso só desliga quando o fluxo exigido cai abaixo disto, e
# liga/desliga no máximo uma vez a cada OVERLOAD_FLIP_MONTHS de jogo.
OVERLOAD_CLEAR_RATIO = 0.9
OVERLOAD_FLIP_MONTHS = 12.0

def get_faction_trade_partners(running_faction, trade_partners):
    for faction in running_faction.game_state.factions:
        if faction.name in trade_partners:
            yield faction

class LogisticsManager:
    """Keep civilian cargo ships available and balance colony resources.

    As necessidades vêm das colônias (reserva de consumo mais obras paradas) e
    as sobras também: um transporte só leva o que a origem pode emprestar e o
    destino ainda não tem.
    """

    def __init__(self, faction):
        self.faction = faction
        self.lock = threading.RLock()
        self._pending_transport_ids = {}
        self._nodes = {}
        self._plan_at = None
        self._needs = {}
        self._surplus = {}
        self._overload = {}
        self._overload_state = False
        self._announced_overload = False
        self._last_flip = 0.0

    def _sync_nodes(self):
        trade_partners = {faction_id for faction_id, treaties in self.faction.treaties.items() if 'trade' in treaties}
        all_planets = [colony for colony in self.faction.colonies.values()]
        partners = list(get_faction_trade_partners(self.faction, trade_partners))
        for p in partners:
            all_planets.extend(p.colonies.values())

        current_planets = {id(planet): planet for planet in all_planets}
        
        for key in list(self._nodes):
            if key not in current_planets:
                del self._nodes[key]
        for key, planet in current_planets.items():
            if key not in self._nodes:
                self._nodes[key] = LogisticsNode(planet)
        for key, planet in current_planets.items():
            if key not in self._nodes:
                self._nodes[key] = LogisticsNode(planet)

    # ---------- estimativas de necessidade ----------
    def inbound_by_destination(self):
        """Carga já prometida a cada colônia, somando missões e porões."""
        totals = {}
        for ship in list(self.faction.ships.copy().values()):
            if not getattr(ship, 'alive', False):
                continue
            if getattr(ship, 'design_key', None) != 'transport':
                continue
            for mission in getattr(ship, 'scheduled_missions', lambda: [])():
                if mission.get('kind') != 'freight':
                    continue
                destination = mission.get('destination')
                if destination is None:
                    continue
                entry = totals.setdefault(id(destination), {})
                for resource, amount in mission.get('legs', ()):
                    entry[resource] = entry.get(resource, 0.0) + amount
        return totals

    def _refresh_estimates(self):
        """Recalcula necessidade e sobra por colônia, já descontando o inbound."""
        inbound = self.inbound_by_destination()
        needs = {}
        surplus = {}
        for key, node in self._nodes.items():
            world = node.planet
            needs[key] = {
                resource: amount
                for resource, amount in world.import_need(
                    inbound.get(key)).items()
                if resource in TRADABLE_RESOURCES}
            surplus[key] = {
                resource: amount
                for resource, amount in world.export_surplus().items()
                if resource in TRADABLE_RESOURCES}
        self._needs = needs
        self._surplus = surplus
        self._plan_at = self._now()
        self._overload = self._measure_overload(needs)
        self._notify_overload()

    def _estimates_are_fresh(self):
        if self._plan_at is None:
            return False
        return self._now() - self._plan_at < 0.5

    def _now(self):
        state = getattr(self.faction, 'game_state', None)
        return state.time if state is not None else 0.0

    def _mean_colony_distance(self):
        colonies = list(self.faction.colonies.values())
        pairs = 0
        total_distance = 0.0
        for index, source in enumerate(colonies):
            for destination in colonies[index + 1:]:
                total_distance += math.dist(
                    source.parent_star.position,
                    destination.parent_star.position)
                pairs += 1
        return total_distance / max(1, pairs)

    def _ship_flow(self, cargo, speed, mean_distance):
        """Unidades/ano que uma nave move no ida-e-volta médio do império."""
        round_trip_years = 2.0 * mean_distance / (
            max(1e-6, speed) * 6.0 * 12.0)
        return cargo / max(0.1, round_trip_years)

    def _fleet_capacity_flow(self):
        """Capacidade anual da frota e a régua de um transporte típico."""
        transports = [
            ship for ship in self.faction.ships.values()
            if getattr(ship, 'alive', False)
            and getattr(ship, 'design_key', None) == 'transport']
        reference = self._ship_flow(
            REFERENCE_CARGO, REFERENCE_SPEED, self._mean_colony_distance())
        capacity = sum(
            self._ship_flow(ship.cargo, ship.speed,
                            self._mean_colony_distance())
            for ship in transports)
        return capacity, len(transports), reference

    def _measure_overload(self, needs):
        """Fluxo anual exigido pelas colônias versus o que a frota entrega."""
        required = 0.0
        starved = []
        awaiting = 0
        for key, need in needs.items():
            if not need:
                continue
            planet = self._nodes[key].planet
            required += self._annual_flow(planet, need)
            starved.append(planet)
            if planet.build_queue:
                awaiting += 1
        capacity, transports, reference = self._fleet_capacity_flow()
        if required <= 0.0:
            deficit = 0.0
        elif capacity > 0.0:
            deficit = required / capacity
        else:
            deficit = float('inf')
        threshold = (OVERLOAD_CLEAR_RATIO if self._overload_state
                     else OVERLOAD_RATIO)
        self._overload_state = bool(starved) and deficit > threshold
        return {
            'required_flow': required,
            'fleet_capacity': capacity,
            'deficit_ratio': deficit,
            'transports': transports,
            'starved': starved,
            'awaiting_colonies': awaiting,
            'missing_transports': min(
                self._fleet_limit(), max(0, math.ceil(
                    (required - capacity) / max(1e-6, reference)))),
            'overloaded': self._overload_state,
        }

    def _annual_flow(self, planet, need):
        """Unidades por ano que precisam *desembarcar* nesta colônia.

        O buraco entre consumo e produção própria é carga contínua; a obra
        parada é uma encomenda única, diluída no prazo de entrega. Assim a
        métrica não cresce com a profundidade da fila nem com a reserva-alvo.
        """
        consumption = planet.consumption()
        yearly = planet.resource_output()
        ongoing = sum(
            max(0.0, consumption.get(resource, 0.0)
                - yearly.get(resource, 0.0))
            for resource in need if resource in TRADABLE_RESOURCES)
        claim = planet.blocked_need()
        build = sum(min(amount, claim.get(resource, 0.0))
                    for resource, amount in need.items())
        return ongoing + build / BUILD_DELIVERY_YEARS

    def overload_status(self):
        if not self._estimates_are_fresh():
            self._sync_nodes()
            self._refresh_estimates()
        return self._overload

    def _notify_overload(self):
        state = getattr(self.faction, 'game_state', None)
        if state is None or not hasattr(state, 'log_event'):
            return
        overloaded = self._overload.get('overloaded', False)
        if overloaded == self._announced_overload:
            return
        now = self._now()
        if now - self._last_flip < OVERLOAD_FLIP_MONTHS:
            return
        self._announced_overload = overloaded
        self._last_flip = now
        if overloaded:
            state.log_event(
                f"{self.faction.name}: transportes sobrecarregados — "
                f"{len(self._overload.get('starved', []))} colônias "
                f"esperando carga com {self._overload.get('transports', 0)} "
                f"transporte(s)")
        else:
            state.log_event(
                f"{self.faction.name}: frotas de transporte normalizadas")

    # ---------- transporte ----------
    def plan_freight_runs(self, capacity, count=1, origin=None,
                          reachable=None):
        """Roteiriza `count` viagens multi-recurso, sem sobrepor contratos."""
        if capacity <= 0 or len(self.faction.colonies) < 2:
            return []
        if not self._estimates_are_fresh():
            self._sync_nodes()
            self._refresh_estimates()
        needs = {key: dict(value) for key, value in self._needs.items()}
        surplus = {key: dict(value)
                   for key, value in self._surplus.items()}
        runs = []
        for _ in range(max(1, int(count))):
            run = self._best_run(
                needs, surplus, capacity, origin, reachable)
            if run is None:
                break
            runs.append(run)
            origin = run['source'].parent_star
            for resource, amount in run['legs']:
                need = needs[id(run['destination'])]
                need[resource] = max(0.0, need.get(resource, 0.0) - amount)
                give = surplus[id(run['source'])]
                give[resource] = max(
                    0.0, give.get(resource, 0.0) - amount)
            needs = {key: value for key, value in needs.items() if value}
            surplus = {key: value for key, value in surplus.items() if value}
        return runs

    def plan_freight_run(self, capacity, origin=None, reachable=None):
        runs = self.plan_freight_runs(
            capacity, 1, origin=origin, reachable=reachable)
        return runs[0] if runs else None

    def _best_run(self, needs, surplus, capacity, origin, reachable):
        best = None
        best_score = 0.0
        for source_key, available in surplus.items():
            if not available:
                continue
            source = self._nodes[source_key].planet
            for destination_key, need in needs.items():
                if destination_key == source_key or not need:
                    continue
                destination = self._nodes[destination_key].planet
                if reachable is not None and not reachable(
                        source, destination):
                    continue
                legs, payload = self._fill_hold(
                    need, available, destination, capacity)
                if payload < min(MIN_RUN_PAYLOAD, capacity):
                    continue
                score = self._run_score(
                    legs, payload, source, destination, origin)
                if score > best_score:
                    best_score = score
                    best = {'source': source, 'destination': destination,
                            'legs': legs, 'payload': payload}
        return best

    def _fill_hold(self, need, available, destination, capacity):
        legs = []
        payload = 0.0
        node = self._nodes[id(destination)]
        for resource, amount in sorted(
                need.items(), key=lambda item: -self._priority(item[0])):
            room = capacity - payload
            if room <= 0.0:
                break
            headroom = max(
                0.0, node.capacity(resource) - node.quantity(resource))
            load = min(amount, available.get(resource, 0.0), room, headroom)
            if load <= 0.0:
                continue
            legs.append((resource, load))
            payload += load
        return legs, payload

    @staticmethod
    def _priority(resource):
        return 1.5 if resource == 'Food' else 1.0

    def _run_score(self, legs, payload, source, destination, origin):
        urgency = AWAITING_BUILD_WEIGHT if destination.build_queue else 1.0
        score = sum(amount * self._priority(resource)
                    for resource, amount in legs) * urgency
        if origin is not None:
            detour = math.dist(
                origin.position, source.parent_star.position) / 200.0
            score /= 1.0 + detour
        return score

    def plan_hold_release(self, ship):
        """Para onde despachar o que já está no porão (carga devolvida)."""
        if not self._estimates_are_fresh():
            self._sync_nodes()
            self._refresh_estimates()
        hold = ship.cargo_hold
        best, best_score = None, 0.0
        for key, need in self._needs.items():
            node = self._nodes[key]
            planet = node.planet
            if planet.parent_star is getattr(ship, 'current_position', None):
                continue
            score = 0.0
            for resource, carried in hold.items():
                headroom = max(
                    0.0, node.capacity(resource) - node.quantity(resource))
                score += min(
                    carried, need.get(resource, 0.0), headroom)
            if score > best_score:
                best_score = score
                best = planet
        return best if best_score > 0.0 else None

    def load_cargo(self, ship, source, legs):
        """Carrega todos os recursos da perna; o que faltar fica para trás."""
        loaded_total = 0.0
        with self.lock, source.lock:
            if source.faction is not self.faction:
                return 0.0
            for resource, amount in legs:
                available = source.planet_resources.get(resource, 0.0)
                room = max(0.0, ship.cargo - ship.used_cargo)
                loaded = min(amount, available, room)
                if loaded <= 0.0:
                    continue
                source.planet_resources[resource] = available - loaded
                ship.cargo_hold[resource] = (
                    ship.cargo_hold.get(resource, 0.0) + loaded)
                loaded_total += loaded
        return loaded_total

    def deliver_cargo(self, ship, destination):
        with self.lock, destination.lock:
            if destination.faction is not self.faction:
                return 0.0
            delivered_total = 0.0
            for resource, carried in list(ship.cargo_hold.items()):
                stored = destination.planet_resources.get(resource, 0.0)
                capacity = destination.storage_capacity.get(resource, 0.0)
                delivered = min(carried, max(0.0, capacity - stored))
                if delivered <= 0.0:
                    continue
                destination.planet_resources[resource] = stored + delivered
                remaining = carried - delivered
                if remaining > 0.0:
                    ship.cargo_hold[resource] = remaining
                else:
                    ship.cargo_hold.pop(resource, None)
                delivered_total += delivered
            return delivered_total

    def trips_serving(self, planet):
        """Transport ships currently routing cargo through one colony."""
        trips = []
        for ship in list(self.faction.ships.copy().values()):
            if not getattr(ship, 'alive', False):
                continue
            if getattr(ship, 'design_key', None) != 'transport':
                continue
            if ship.source is planet or ship.destination is planet:
                trips.append(ship)
        return trips

    # ---------- frota ----------
    def update(self):
        faction = self.faction
        self._sync_nodes()
        if faction.eliminated or not faction.colonies:
            return

        now = faction.game_state.time if faction.game_state else 0.0
        live_ship_ids = set(faction.ships)
        queued_ship_ids = self._queued_ship_ids()
        for ship_id, expiry in list(self._pending_transport_ids.items()):
            if ship_id in live_ship_ids or (now >= expiry and ship_id not in queued_ship_ids):            
                self._pending_transport_ids.pop(ship_id, None)

        desired = self._desired_fleet()
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

        for ship in faction.ships.copy().values():
            yield from ship.ai()

    def _desired_fleet(self):
        colony_count = len(self.faction.colonies)
        if colony_count < 2:
            return 0
        base = math.ceil(colony_count / 3)
        overload = self.overload_status()
        extra = overload.get('missing_transports', 0) if overload else 0
        return min(self._fleet_limit(), base + extra)

    def _fleet_limit(self):
        """Frota civil que o império pode manter, conforme o tamanho dele."""
        return min(MAX_TRANSPORTS_CEILING,
                   MAX_TRANSPORTS + len(self.faction.colonies) // 5)

    def _queued_ship_ids(self):
        queued = set()
        for planet in self.faction.colonies.values():
            queued.update(
                task['id'] for task in planet.queued_tasks()
                if task.get('design_key') == 'transport'
            )
        return queued
