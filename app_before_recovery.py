from flask import (
    Flask, render_template, request, redirect,
    url_for, session, Response
)
from werkzeug.security import generate_password_hash, check_password_hash
from database import create_database
import sqlite3
import csv
import io
import math
import networkx as nx
from sklearn.cluster import KMeans


app = Flask(__name__)
app.secret_key = "blood_donation_project_secret_key_2026"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Admin@123"

ALLOWED_STATUSES = [
    "Pending", "Donor Found", "Fulfilled", "Cancelled"
]

ALLOWED_RESPONSES = [
    "Interested", "Unable to Donate"
]

ALLOWED_PROGRESS_STATUSES = [
    "Interested",
    "On the Way",
    "Reached Hospital",
    "Donation Completed"
]

MAX_DONOR_DISTANCE = 20
MAX_PICKUP_GROUP_DISTANCE_KM = 5.0

create_database()


# Calculate distance between two GPS coordinates
def calculate_distance(lat1, lon1, lat2, lon2):

    earth_radius = 6371

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    latitude_difference = lat2 - lat1
    longitude_difference = lon2 - lon1

    a = (
        math.sin(latitude_difference / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(longitude_difference / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return earth_radius * c


# Safely read GPS coordinates
def get_coordinate(value):

    try:
        if value is None or str(value).strip() == "":
            return None

        return float(value)

    except (ValueError, TypeError):
        return None


# Dijkstra and A* Route Optimization
def optimize_sample_route(start, destination):

    graph_path = "road_data/demo_roads.graphml"

    try:
        G = nx.read_graphml(graph_path)

        if start not in G or destination not in G:
            return None

        # Sample junction coordinates (metres)
        coordinates = {
            "A": (0, 0),
            "B": (800, 0),
            "C": (0, 1200),
            "D": (350, 1100),
            "E": (0, 2000),
            "F": (350, 1800)
        }

        if start not in coordinates or destination not in coordinates:
            return None

        # Dijkstra algorithm
        dijkstra_route = nx.shortest_path(
            G,
            source=start,
            target=destination,
            weight="length",
            method="dijkstra"
        )

        dijkstra_distance = nx.shortest_path_length(
            G,
            source=start,
            target=destination,
            weight="length"
        )

        # A* heuristic
        def heuristic(node1, node2):

            x1, y1 = coordinates[node1]
            x2, y2 = coordinates[node2]

            return math.sqrt(
                (x2 - x1) ** 2 + (y2 - y1) ** 2
            )

        # A* algorithm
        astar_route = nx.astar_path(
            G,
            source=start,
            target=destination,
            heuristic=heuristic,
            weight="length"
        )

        astar_distance = nx.astar_path_length(
            G,
            source=start,
            target=destination,
            heuristic=heuristic,
            weight="length"
        )

        return {
            "dijkstra_route": dijkstra_route,
            "dijkstra_distance": round(dijkstra_distance, 2),
            "astar_route": astar_route,
            "astar_distance": round(astar_distance, 2)
        }

    except (
        nx.NetworkXNoPath,
        nx.NodeNotFound,
        FileNotFoundError
    ):
        return None


# Home Page
@app.route("/")
def home():
    return render_template("index.html")


# Donor Registration
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        fullname = request.form["fullname"]
        age = request.form["age"]
        gender = request.form["gender"]
        blood_group = request.form["blood_group"]
        phone = request.form["phone"]
        email = request.form["email"]
        password = request.form["password"]
        location = request.form["location"]
        availability = request.form["availability"]

        latitude = get_coordinate(request.form.get("latitude"))
        longitude = get_coordinate(request.form.get("longitude"))

        if latitude is None or longitude is None:
            return """
            <h1>Location Required</h1>
            <p>Please capture your current location before registering.</p>
            <a href="/register">Go Back</a>
            """

        if not (-90 <= latitude <= 90):
            return "Invalid latitude. Please try again."

        if not (-180 <= longitude <= 180):
            return "Invalid longitude. Please try again."

        password_hash = generate_password_hash(password)

        connection = sqlite3.connect("blood_donation.db")
        cursor = connection.cursor()

        try:
            cursor.execute("""
                INSERT INTO donors
                (
                    fullname, age, gender, blood_group,
                    phone, email, location, availability,
                    password_hash, availability_updated_at,
                    registered_at, latitude, longitude
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, ?
                )
            """, (
                fullname, age, gender, blood_group,
                phone, email, location, availability,
                password_hash, latitude, longitude
            ))

            connection.commit()
            connection.close()

            return """
            <h1>Registration Successful!</h1>
            <p>Your GPS location has been saved successfully.</p>
            <a href="/login">Login Here</a>
            """

        except sqlite3.IntegrityError:
            connection.close()

            return """
            <h1>Email Already Registered!</h1>
            <a href="/register">Try Again</a>
            """


    return render_template("register.html")


# Donor Login
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        connection = sqlite3.connect("blood_donation.db")
        cursor = connection.cursor()

        cursor.execute("""
            SELECT id, fullname, password_hash
            FROM donors
            WHERE email = ?
        """, (email,))

        donor = cursor.fetchone()
        connection.close()

        if donor and donor[2] and check_password_hash(donor[2], password):

            session.clear()
            session["donor_id"] = donor[0]
            session["donor_name"] = donor[1]

            return redirect(url_for("view_notifications"))

        return render_template(
            "login.html",
            error="Invalid email or password. Please try again."
        )

    return render_template("login.html")


# Donor Logout
@app.route("/logout")
def logout():

    session.clear()
    return redirect(url_for("home"))


# Admin Login
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:

            session.clear()
            session["admin_logged_in"] = True

            return redirect(url_for("admin"))

        return render_template(
            "admin_login.html",
            error="Invalid admin username or password."
        )

    return render_template("admin_login.html")


# Admin Logout
@app.route("/admin_logout")
def admin_logout():

    session.pop("admin_logged_in", None)
    return redirect(url_for("home"))


# Blood Request Submission + Automatic Notifications
@app.route("/request", methods=["GET", "POST"])
def request_blood():

    if request.method == "POST":

        patient_name = request.form["patient_name"]
        age = request.form["age"]
        blood_group = request.form["blood_group"]
        units = request.form["units"]
        hospital = request.form["hospital"]
        location = request.form["location"]
        phone = request.form["phone"]
        additional_info = request.form["additional_info"]

        request_latitude = get_coordinate(request.form.get("latitude"))
        request_longitude = get_coordinate(request.form.get("longitude"))

        if request_latitude is not None:
            if not (-90 <= request_latitude <= 90):
                return "Invalid request latitude."

        if request_longitude is not None:
            if not (-180 <= request_longitude <= 180):
                return "Invalid request longitude."

        if (
            (request_latitude is None and request_longitude is not None)
            or
            (request_latitude is not None and request_longitude is None)
        ):
            return """
            <h1>Invalid Location</h1>
            <p>Please provide both latitude and longitude.</p>
            <a href="/request">Go Back</a>
            """

        connection = sqlite3.connect("blood_donation.db")
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO blood_requests
            (
                patient_name, age, blood_group, units,
                hospital, location, phone, additional_info,
                latitude, longitude
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            patient_name, age, blood_group, units,
            hospital, location, phone, additional_info,
            request_latitude, request_longitude
        ))

        request_id = cursor.lastrowid

        cursor.execute("""
            SELECT id, latitude, longitude
            FROM donors
            WHERE blood_group = ?
            AND availability = 'Available'
        """, (blood_group,))

        matching_donors = cursor.fetchall()

        for donor in matching_donors:

            donor_id = donor[0]
            donor_latitude = donor[1]
            donor_longitude = donor[2]

            if (
                request_latitude is not None
                and request_longitude is not None
            ):

                if donor_latitude is None or donor_longitude is None:
                    continue

                distance = calculate_distance(
                    request_latitude,
                    request_longitude,
                    donor_latitude,
                    donor_longitude
                )

                if distance <= MAX_DONOR_DISTANCE:

                    message = (
                        f"New {blood_group} blood request at {hospital}, "
                        f"{location}. You are approximately "
                        f"{distance:.2f} km away. "
                        f"Please check the request details."
                    )

                else:
                    continue

            else:

                message = (
                    f"New {blood_group} blood request at {hospital}, "
                    f"{location}. Please check the request details."
                )

            cursor.execute("""
                INSERT INTO notifications
                (donor_id, request_id, message)
                VALUES (?, ?, ?)
            """, (donor_id, request_id, message))

        connection.commit()
        connection.close()

        return redirect(url_for("track_request", request_id=request_id))

    return render_template("request.html")


# Request Tracking Search
@app.route("/track", methods=["GET", "POST"])
def track_search():

    if request.method == "POST":

        request_id = request.form.get("request_id", "").strip()

        if not request_id.isdigit() or int(request_id) < 1:
            return "Please enter a valid Request ID."

        return redirect(url_for(
            "track_request",
            request_id=int(request_id)
        ))

    return render_template("track_search.html")


# Display Request Details and Status
@app.route("/track/<int:request_id>")
def track_request(request_id):

    connection = sqlite3.connect("blood_donation.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM blood_requests WHERE id = ?",
        (request_id,)
    )

    blood_request = cursor.fetchone()
    connection.close()

    if blood_request is None:

        return """
        <h1>Request Not Found</h1>
        <a href="/track">Try Again</a>
        """

    return render_template("track.html", blood_request=blood_request)

# Route Optimization Demo Page
@app.route("/optimize_route", methods=["GET", "POST"])
def optimize_route():

    result = None
    error = None
    start = "A"
    destination = "F"

    allowed_nodes = ["A", "B", "C", "D", "E", "F"]

    if request.method == "POST":
        start = request.form.get("start", "A").strip().upper()
        destination = request.form.get("destination", "F").strip().upper()

        if start not in allowed_nodes or destination not in allowed_nodes:
            error = "Please select valid junctions."

        elif start == destination:
            error = "Starting point and destination must be different."

        else:
            result = optimize_sample_route(start, destination)

            if result is None:
                error = "Route could not be calculated. Check that the sample road network exists."

    junction_options_start = "".join(
        f'<option value="{node}" {"selected" if node == start else ""}>{node}</option>'
        for node in allowed_nodes
    )

    junction_options_destination = "".join(
        f'<option value="{node}" {"selected" if node == destination else ""}>{node}</option>'
        for node in allowed_nodes
    )

    result_html = ""

    if result:
        result_html = f"""
        <div class="result">
            <h3>Dijkstra Algorithm</h3>
            <p>Route: {" → ".join(result["dijkstra_route"])}</p>
            <p>Distance: {result["dijkstra_distance"]} metres
            ({result["dijkstra_distance"] / 1000:.2f} km)</p>

            <h3>A* Algorithm</h3>
            <p>Route: {" → ".join(result["astar_route"])}</p>
            <p>Distance: {result["astar_distance"]} metres
            ({result["astar_distance"] / 1000:.2f} km)</p>
        </div>
        """

    error_html = f'<p class="error">{error}</p>' if error else ""

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Route Optimization - Blood Donation System</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">

        <style>
            body {{
                font-family: Arial;
                background: #f5f5f5;
                padding: 25px;
            }}

            .container {{
                max-width: 650px;
                margin: auto;
                background: white;
                padding: 25px;
                border-radius: 10px;
            }}

            select, button {{
                padding: 10px;
                margin: 8px 0;
                width: 100%;
            }}

            button {{
                background: #b71c1c;
                color: white;
                border: 0;
                border-radius: 5px;
                cursor: pointer;
            }}

            .result {{
                background: #f1f8e9;
                padding: 15px;
                margin-top: 15px;
                border-radius: 8px;
            }}

            .error {{
                color: #b71c1c;
            }}
        </style>
    </head>

    <body>
        <div class="container">

            <h2>Blood Donation Route Optimization</h2>

            <p>
                <b>Demonstration:</b> This page uses a locally stored
                sample road network with six junctions.
                It is not a live Mysuru road map.
            </p>

            <form method="POST">

                <label>Starting Junction</label>
                <select name="start">
                    {junction_options_start}
                </select>

                <label>Destination Junction</label>
                <select name="destination">
                    {junction_options_destination}
                </select>

                <button type="submit">
                    Calculate Shortest Route
                </button>

            </form>

            {error_html}
            {result_html}

            <p><a href="/">Return to Home</a></p>

        </div>
    </body>
    </html>
    """


if __name__ == "__main__":
    app.run(debug=True)
