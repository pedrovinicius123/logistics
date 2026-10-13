import networkx as nx
from ..logistics_node import Node 

d = {
    "consumer_goods":{
        "water" :  0.,
        "minerals":  1/2,
        "electronics":  0.3,
        "energy":  1.,

        "factory": {
            "name": "Consumer_goods_factory",
            "max_workers": 100,
            "construction": {
                "minerals": 200,
                "electronics": 30,
                "machines": 30,
                "energy": 100,                    
            }
        }
    },

    "life_suport": {
        "water":  1.,
        "energy":  1.,
        "factory": {
            "name": "life_suport_systems",
            "max_workers": 10,
            "construction": {
                "minerals": 100,
                "electronics": 10,
                "energy": 20,                    
            }
        }
    },
    
    "electronics": {
        "water":  1.0,
        "energy":  2/3,
        "rare_minerals": 1/6,
        "factory": {
            "name": "Electronics_factory",
            "max_workers": 100,
            "construction": {
                "minerals": 400,
                "electronics": 100,
                "machines": 30,
                "energy": 200,                    
            }
        }            
    },

    "food": {
        "water":  1.,
        "energy":  1.,
        "life_suport": 1.,
        "factory": {
            "name": "H_farm",
            "max_workers": 200,
            "construction": {
                "minerals": 200,
                "machines": 30,
                "water": 100,
                "food": 100,
                "energy": 30,
            }
        }
    },

    "water": {
        "factory": {
            "name": "Water_pump",
            "workers": 200,
            "construction": {
                "minerals": 200,
                "electronics": 20,
                "machines": 10,
            }
        }
    },

    "minerals": {
        "water": 0.1,
        "energy": 0.3,
        "factory": {
            "name": "Mine",
            "max_workers": 100,
            "construction": {
                "minerals": 300,
                "energy": 100,
                "machines": 30,

            }           
        }
    },

    "rare_minerals":{
        "water": 0.3,
        "energy": 0.6,
        "factory": {
            "name": "Mine",
            "max_workers": 100,
            "construction": {
                "minerals": 300,
                "energy": 100,
                "machines": 30,

            }           
        }
    },

    "energy": {
        "factory": {
            "name": "Power_plant",
            "max_workers": 100,
            "construction": {
                "minerals": 300,
                "machines": 30,
                "electronics": 10,
            }
        }
    }

}

def init_resources_prod():
    global d
    g = nx.DiGraph()
    edges = []

    def wrap_d() -> nx.DiGraph:  
        for k in d:
            g.add_node(k, factory=d[k]["factory"])
            for inc in d[k]:
                if inc != "factory":
                    edges.append((inc, k, {
                        "rate": d[k][inc]
                    }))

        g.add_edges_from(edges)
        return g

    return wrap_d()

G = init_resources_prod()

