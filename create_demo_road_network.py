import os
import networkx as nx

# Create a sample road network
G = nx.Graph()

# Add sample road junctions
G.add_node("A", name="Junction A")
G.add_node("B", name="Junction B")
G.add_node("C", name="Junction C")
G.add_node("D", name="Junction D")
G.add_node("E", name="Junction E")
G.add_node("F", name="Hospital")

# Add roads with distances in metres
G.add_edge("A", "B", length=1000)
G.add_edge("A", "C", length=1500)
G.add_edge("B", "D", length=1200)
G.add_edge("C", "D", length=500)
G.add_edge("C", "E", length=1000)
G.add_edge("D", "F", length=800)
G.add_edge("E", "F", length=700)

# Create storage folder
os.makedirs("road_data", exist_ok=True)

# Save the graph locally
file_path = "road_data/demo_roads.graphml"
nx.write_graphml(G, file_path)

print("Sample road network created successfully!")
print("Junctions:", G.number_of_nodes())
print("Road connections:", G.number_of_edges())
print("Saved at:", file_path)