
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import create_database
import sqlite3

app = Flask(__name__)
app.secret_key = "blood_donation_project_secret_key_2026"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Admin@123"

ALLOWED_STATUSES = [
    "Pending",
    "Donor Found",
    "Fulfilled",
    "Cancelled"
]

create_database()


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

        password_hash = generate_password_hash(password)

        connection = sqlite3.connect("blood_donation.db")
        cursor = connection.cursor()

        try:
            cursor.execute("""
                INSERT INTO donors
                (fullname, age, gender, blood_group, phone, email,
                 location, availability, password_hash,
                 availability_updated_at, registered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (
                fullname, age, gender, blood_group, phone,
                email, location, availability, password_hash
            ))

            connection.commit()
            connection.close()

            return """
            <h1>Registration Successful!</h1>
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

        connection = sqlite3.connect("blood_donation.db")
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO blood_requests
            (patient_name, age, blood_group, units, hospital,
             location, phone, additional_info)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            patient_name, age, blood_group, units, hospital,
            location, phone, additional_info
        ))

        request_id = cursor.lastrowid

        cursor.execute("""
            SELECT id FROM donors
            WHERE blood_group = ?
            AND availability = 'Available'
        """, (blood_group,))

        matching_donors = cursor.fetchall()

        message = (
            f"New {blood_group} blood request at {hospital}, "
            f"{location}. Please check the request details."
        )

        for donor in matching_donors:
            cursor.execute("""
                INSERT INTO notifications
                (donor_id, request_id, message)
                VALUES (?, ?, ?)
            """, (donor[0], request_id, message))

        connection.commit()
        connection.close()

        return redirect(url_for(
            "track_request",
            request_id=request_id
        ))

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

    cursor.execute("""
        SELECT * FROM blood_requests WHERE id = ?
    """, (request_id,))

    blood_request = cursor.fetchone()
    connection.close()

    if blood_request is None:
        return """
        <h1>Request Not Found</h1>
        <a href="/track">Try Again</a>
        """

    return render_template(
        "track.html",
        blood_request=blood_request
    )


# Protected Admin Dashboard + Analytics
@app.route("/admin")
def admin():

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    connection = sqlite3.connect("blood_donation.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    # Donor Availability Monitoring
    cursor.execute("""
        SELECT *,
            CASE
                WHEN availability_updated_at IS NULL THEN 1
                WHEN julianday('now') - julianday(availability_updated_at) > 30 THEN 1
                ELSE 0
            END AS is_outdated
        FROM donors
        ORDER BY is_outdated DESC, fullname ASC
    """)

    donors = cursor.fetchall()

    # Fetch Blood Requests
    cursor.execute("""
        SELECT * FROM blood_requests
        ORDER BY id DESC
    """)

    requests = cursor.fetchall()

    # Total Counts
    total_donors = len(donors)
    total_requests = len(requests)

    # Count Outdated Donor Records
    outdated_donors = sum(
        1 for donor in donors if donor["is_outdated"] == 1
    )

    # Day 23: Blood Request Analytics
    cursor.execute("""
        SELECT status, COUNT(*) AS total
        FROM blood_requests
        GROUP BY status
    """)

    status_results = cursor.fetchall()

    status_counts = {
        "Pending": 0,
        "Donor Found": 0,
        "Fulfilled": 0,
        "Cancelled": 0
    }

    for item in status_results:
        if item["status"] in status_counts:
            status_counts[item["status"]] = item["total"]

    # Day 24: Blood Group-wise Donor Analytics
    blood_groups = [
        "A+", "A-", "B+", "B-",
        "AB+", "AB-", "O+", "O-"
    ]

    donor_group_counts = {
        group: {
            "Available": 0,
            "Not Available": 0
        }
        for group in blood_groups
    }

    cursor.execute("""
        SELECT blood_group, availability, COUNT(*) AS total
        FROM donors
        GROUP BY blood_group, availability
    """)

    group_results = cursor.fetchall()

    for item in group_results:
        group = item["blood_group"]
        availability = item["availability"]

        if group in donor_group_counts and availability in [
            "Available", "Not Available"
        ]:
            donor_group_counts[group][availability] = item["total"]

    # Day 25: Monthly Donor Registration Analytics
    cursor.execute("""
        SELECT
            strftime('%Y-%m', registered_at) AS registration_month,
            COUNT(*) AS total
        FROM donors
        WHERE registered_at IS NOT NULL
        GROUP BY strftime('%Y-%m', registered_at)
        ORDER BY registration_month ASC
    """)

    monthly_results = cursor.fetchall()

    monthly_labels = [
        item["registration_month"] for item in monthly_results
    ]

    monthly_donor_counts = [
        item["total"] for item in monthly_results
    ]

    # Day 26: Monthly Donor Growth Insights
    cursor.execute("""
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN strftime(
                        '%Y-%m',
                        datetime(registered_at, '+5 hours', '+30 minutes')
                    ) = strftime(
                        '%Y-%m',
                        datetime('now', '+5 hours', '+30 minutes')
                    )
                    THEN 1 ELSE 0
                END
            ), 0) AS current_month,

            COALESCE(SUM(
                CASE
                    WHEN strftime(
                        '%Y-%m',
                        datetime(registered_at, '+5 hours', '+30 minutes')
                    ) = strftime(
                        '%Y-%m',
                        datetime(
                            'now', '+5 hours', '+30 minutes',
                            'start of month', '-1 month'
                        )
                    )
                    THEN 1 ELSE 0
                END
            ), 0) AS previous_month

        FROM donors
        WHERE registered_at IS NOT NULL
    """)

    growth_result = cursor.fetchone()

    current_month_donors = growth_result["current_month"]
    previous_month_donors = growth_result["previous_month"]

    if previous_month_donors > 0:
        growth_percentage = round(
            (
                (current_month_donors - previous_month_donors)
                / previous_month_donors
            ) * 100,
            2
        )
    else:
        growth_percentage = None

    connection.close()

    return render_template(
        "admin.html",
        donors=donors,
        requests=requests,
        total_donors=total_donors,
        total_requests=total_requests,
        outdated_donors=outdated_donors,
        status_counts=status_counts,
        donor_group_counts=donor_group_counts,
        monthly_labels=monthly_labels,
        monthly_donor_counts=monthly_donor_counts,
        current_month_donors=current_month_donors,
        previous_month_donors=previous_month_donors,
        growth_percentage=growth_percentage
    )


# Update Blood Request Status (Admin Only)
@app.route("/update_request_status/<int:request_id>", methods=["POST"])
def update_request_status(request_id):

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    new_status = request.form.get("status", "")

    if new_status not in ALLOWED_STATUSES:
        return "Invalid request status."

    connection = sqlite3.connect("blood_donation.db")
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE blood_requests
        SET status = ?
        WHERE id = ?
    """, (new_status, request_id))

    connection.commit()

    updated_rows = cursor.rowcount
    connection.close()

    if updated_rows == 0:
        return "Blood request not found."

    return redirect(url_for("admin"))


# Intelligent Donor Matching
@app.route("/match", methods=["GET", "POST"])
def match_donors():
    matched_donors = []
    blood_group = ""
    location = ""
    searched = False

    if request.method == "POST":
        blood_group = request.form["blood_group"]
        location = request.form.get("location", "").strip()
        searched = True

    elif request.args.get("blood_group"):
        blood_group = request.args.get("blood_group")
        location = request.args.get("location", "").strip()
        searched = True

    if searched:
        connection = sqlite3.connect("blood_donation.db")
        cursor = connection.cursor()

        cursor.execute("""
            SELECT * FROM donors
            WHERE blood_group = ?
            AND availability = 'Available'
        """, (blood_group,))

        all_donors = cursor.fetchall()
        connection.close()

        def calculate_score(donor):
            donor_location = donor[7].strip().lower()
            search_location = location.strip().lower()

            if not search_location:
                return 50

            if donor_location == search_location:
                return 100

            if (
                search_location in donor_location
                or donor_location in search_location
            ):
                return 75

            return 50

        matched_donors = sorted(
            all_donors,
            key=calculate_score,
            reverse=True
        )

    return render_template(
        "match.html",
        donors=matched_donors,
        blood_group=blood_group,
        location=location,
        searched=searched
    )


# Donor Transport Submission
@app.route("/transport", methods=["GET", "POST"])
def transport():
    if request.method == "POST":
        donor_name = request.form["donor_name"]
        phone = request.form["phone"]
        pickup_location = request.form["pickup_location"]
        destination = request.form["destination"]
        travel_date = request.form["travel_date"]
        travel_time = request.form["travel_time"]
        available_seats = request.form["available_seats"]
        notes = request.form.get("notes", "")

        connection = sqlite3.connect("blood_donation.db")
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO transport_requests
            (donor_name, phone, pickup_location, destination,
             travel_date, travel_time, available_seats, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            donor_name, phone, pickup_location, destination,
            travel_date, travel_time, available_seats, notes
        ))

        connection.commit()
        connection.close()

        return redirect(url_for("available_rides"))

    return render_template("transport.html")


# View Available Rides
@app.route("/rides")
def available_rides():
    connection = sqlite3.connect("blood_donation.db")
    cursor = connection.cursor()

    cursor.execute("""
        SELECT * FROM transport_requests
        ORDER BY travel_date ASC, travel_time ASC
    """)

    rides = cursor.fetchall()
    connection.close()

    return render_template("rides.html", rides=rides)


# View Only Logged-in Donor's Notifications
@app.route("/notifications")
def view_notifications():

    if "donor_id" not in session:
        return redirect(url_for("login"))

    connection = sqlite3.connect("blood_donation.db")
    cursor = connection.cursor()

    cursor.execute("""
        SELECT notifications.id,
               donors.fullname,
               donors.blood_group,
               notifications.message,
               notifications.created_at,
               notifications.is_read
        FROM notifications
        JOIN donors
        ON notifications.donor_id = donors.id
        WHERE notifications.donor_id = ?
        ORDER BY notifications.id DESC
    """, (session["donor_id"],))

    notifications = cursor.fetchall()
    connection.close()

    return render_template(
        "notifications.html",
        notifications=notifications
    )


# Mark Only Own Notification as Read
@app.route("/mark_read/<int:notification_id>", methods=["POST"])
def mark_read(notification_id):

    if "donor_id" not in session:
        return redirect(url_for("login"))

    connection = sqlite3.connect("blood_donation.db")
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE notifications
        SET is_read = 1
        WHERE id = ? AND donor_id = ?
    """, (notification_id, session["donor_id"]))

    connection.commit()
    connection.close()

    return redirect(url_for("view_notifications"))


# Donor Availability Update
@app.route("/availability", methods=["GET", "POST"])
def update_availability():

    if "donor_id" not in session:
        return redirect(url_for("login"))

    connection = sqlite3.connect("blood_donation.db")
    cursor = connection.cursor()

    if request.method == "POST":
        new_availability = request.form.get("availability", "")

        if new_availability not in ["Available", "Not Available"]:
            connection.close()
            return "Invalid availability selection."

        cursor.execute("""
            UPDATE donors
            SET availability = ?,
                availability_updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_availability, session["donor_id"]))

        connection.commit()

    cursor.execute("""
        SELECT availability, availability_updated_at
        FROM donors
        WHERE id = ?
    """, (session["donor_id"],))

    donor_status = cursor.fetchone()
    connection.close()

    if donor_status is None:
        session.clear()
        return redirect(url_for("login"))

    return render_template(
        "availability.html",
        donor_status=donor_status
    )


if __name__ == "__main__":
    app.run(debug=True)
