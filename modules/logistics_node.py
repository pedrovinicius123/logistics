class LogisticsNode:
    """Python fallback for the optional Cython colony adapter."""

    def __init__(self, planet):
        self.planet = planet

    def quantity(self, resource):
        return float(self.planet.planet_resources.get(resource, 0.0))

    def capacity(self, resource):
        return float(self.planet.storage_capacity.get(resource, 0.0))

    def resource_state(self, resource):
        return self.quantity(resource), self.capacity(resource)

    def snapshot(self, resources):
        return {
            resource: self.resource_state(resource)
            for resource in resources
        }


try:
    from ._logistics_node import LogisticsNode as _CythonLogisticsNode
except ModuleNotFoundError as error:
    if error.name != 'logistics.modules._logistics_node':
        raise
else:
    LogisticsNode = _CythonLogisticsNode

Node = LogisticsNode
