cimport cython

cpdef void update_prod(object prod):
    prod

cdef class Node:
    # Operational Parameters
    cdef int n = 0
    cdef dict demand
    cdef dict prod
    cdef dict rate
    cdef dict storage
    cdef dict neighbors
    
    # Label
    cdef str label
    
    # Pops
    cdef int pops
    
    # Floats
    cdef float max_storage
    cdef float growing_rate

    def __init__(self, dict initial_prod_rate, dict initial_demand_rate, float max_storage, object resources_prod):
        self.pops = 1000
        cdef str k
        cdef float v
       
        self.demand = {k: v*pops for k, v in initial_demand_rate.items()}
        self.prod = {k: v*pops for k, v in initial_prod_rate.items()}
        self.max_storage = max_storage

        self.growing_rate = 0.1    
        self.neighbors = {}
        self.label = "Center-"+Node.n
        self.resources_prod = resources_prod.copy()
        self.update_rate()
    
        Node.n += 1

    cpdef void update_rate(self, dict ext = {}):
        cdef str k
        cdef float v
        cdef set all_keys = set(self.prod.keys()) + set(self.demand.keys())

        for k in all_keys:
            v = self.prod.get(k, 0) - self.demand.get(k, 0)
            self.rate[k] = v 

        if len(ext) > 0:
            for k in ext.keys():
                if k not in self.rate:
                    self.rate[k] = ext[k]
                    continue

                self.rate[k] += ext[k]

    cpdef void update_neighbor(self, str n, str resource, float adding_rate):
        if n in self.neighbors:
            print(f"Added transaction from {n} to {self.label}: {abs(adding_rate)} of {resource}")
            if resource not in self.neighbors[n]:
                self.neighbors[n][resource] = adding_rate
            else:
                self.neighbors[n][resource] += adding_rate

    cpdef void prod(self, object resources_prod):
        for k, v in self.rate.items():
            self.storage[k] += v
            self.storage[k] = min(self.storage[k], max_storage)

        for k in self.prod.copy().keys():
            self.prod[k] = self.prod[k]*tanh(self.max_storage-self.storage) + self.demand[k]
        
        self.pops = self.pops*(1+self.growing_rate)
        self.growing_rate += 
                