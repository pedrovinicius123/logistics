cdef class LogisticsNode:
    """Cython adapter exposing live colony stock and storage limits."""

    cdef public object planet

    def __cinit__(self, object planet):
        self.planet = planet

    cpdef double quantity(self, str resource):
        return float(self.planet.planet_resources.get(resource, 0.0))

    cpdef double capacity(self, str resource):
        return float(self.planet.storage_capacity.get(resource, 0.0))

    cpdef tuple resource_state(self, str resource):
        return self.quantity(resource), self.capacity(resource)

    cpdef dict snapshot(self, set resources):
        cdef dict result = {}
        cdef str resource
        for resource in resources:
            result[resource] = self.resource_state(resource)
        return result


Node = LogisticsNode
