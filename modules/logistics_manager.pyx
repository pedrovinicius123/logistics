from logistics.modules._logistics_node import LogisticsNode


cdef class Manager:
    """Cython coordinator that plans transfers across live colony nodes."""

    cdef dict _nodes
    cdef dict _snapshots
    cdef set resources

    def __cinit__(self, set resources):
        self._nodes = {}
        self._snapshots = {}
        self.resources = set(resources)

    cpdef void add_node(self, object node):
        if not isinstance(node, LogisticsNode):
            raise TypeError("node must be a LogisticsNode")
        self._nodes[id(node.planet)] = node

    cpdef void remove_node(self, object planet):
        self._nodes.pop(id(planet), None)
        self._snapshots.pop(id(planet), None)

    cpdef void update_nodes(self):
        cdef object key
        cdef object node
        self._snapshots = {}
        for key, node in self._nodes.items():
            self._snapshots[key] = node.snapshot(self.resources)

    cpdef object plan_transfer(self, str resource, double cargo_capacity):
        cdef object source_key
        cdef object destination_key
        cdef object source
        cdef object destination
        cdef double available
        cdef double stored
        cdef double capacity
        cdef double room
        cdef double amount
        cdef double imbalance
        cdef double best_imbalance = 0.0
        cdef object best_route = None

        if cargo_capacity <= 0.0:
            return None
        if resource not in self.resources:
            return None

        self.update_nodes()
        for source_key, source in self._nodes.items():
            available, _ = self._snapshots[source_key][resource]
            if available < cargo_capacity * 0.5:
                continue
            for destination_key, destination in self._nodes.items():
                if source_key == destination_key:
                    continue
                stored, capacity = self._snapshots[destination_key][resource]
                room = capacity - stored
                amount = min(cargo_capacity, available, room)
                if amount <= 0.0:
                    continue
                imbalance = available - stored
                if imbalance > best_imbalance:
                    best_imbalance = imbalance
                    best_route = (
                        source.planet, destination.planet, amount)
        return best_route
