
import os
import osmnx as ox

# Use an alternative Overpass server
ox.settings.overpass_url = "https://overpass.private.coffee/api"
ox.settings.requests_timeout = 300

os.makedirs("road_data", exist_ok=True)

print("Downloading a 5 km road network around Mysuru...")
print("Please wait.")

# Mysuru city centre coordinates
G = ox.graph.graph_from_point(
    (12.2958, 76.6394),
    dist=5000,
    network_type="drive",
    simplify=True
)

file_path = os.path.join("road_data", "mysuru_roads.graphml")
ox.save_graphml(G, file_path)

print("\nRoad network downloaded successfully!")
print("Road intersections:", len(G.nodes))
print("Road connections:", len(G.edges))
print("Saved at:", file_path)
