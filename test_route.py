
import networkx as nx
import math

# Load the saved road network
G = nx.read_graphml("road_data/demo_roads.graphml")

start = "A"
destination = "F"

# Dijkstra algorithm
dijkstra_route = nx.shortest_path(
    G, start, destination,
    weight="length",
    method="dijkstra"
)

dijkstra_distance = nx.shortest_path_length(
    G, start, destination,
    weight="length"
)

# Sample junction coordinates (metres)
coordinates = {
    "A": (0, 0),
    "B": (800, 0),
    "C": (0, 1200),
    "D": (350, 1100),
    "E": (0, 2000),
    "F": (350, 1800)
}

# A* heuristic: straight-line distance between junctions
def heuristic(node1, node2):
    x1, y1 = coordinates[node1]
    x2, y2 = coordinates[node2]
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

# A* algorithm
astar_route = nx.astar_path(
    G, start, destination,
    heuristic=heuristic,
    weight="length"
)

astar_distance = nx.astar_path_length(
    G, start, destination,
    heuristic=heuristic,
    weight="length"
)

print("\n===== ROUTE OPTIMIZATION RESULTS =====")

print("\nDIJKSTRA ALGORITHM")
print("Route:", " -> ".join(dijkstra_route))
print("Distance:", dijkstra_distance, "metres")

print("\nA* ALGORITHM")
print("Route:", " -> ".join(astar_route))
print("Distance:", astar_distance, "metres")

print("\nBoth algorithms tested successfully!")
