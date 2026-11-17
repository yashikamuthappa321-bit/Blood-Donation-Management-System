import os
from dotenv import load_dotenv
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
load_dotenv()

app.secret_key = os.getenv("SECRET_KEY")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

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

ALLOWED_URGENCY_LEVELS = [
    "Normal", "Urgent", "Emergency"
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
        additional_info = request.form.get("additional_info", "")

        urgency_level = request.form.get(
            "urgency_level", "Normal"
        ).strip()

        if urgency_level not in ALLOWED_URGENCY_LEVELS:
            return "Invalid urgency level."

        # All newly submitted emergency requests start unverified.
        emergency_verified = 0

        request_latitude = get_coordinate(
            request.form.get("latitude")
        )
        request_longitude = get_coordinate(
            request.form.get("longitude")
        )

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
                latitude, longitude,
                urgency_level, emergency_verified
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            patient_name, age, blood_group, units,
            hospital, location, phone, additional_info,
            request_latitude, request_longitude,
            urgency_level, emergency_verified
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
                    distance_message = (
                        f"You are approximately {distance:.2f} km away. "
                    )
                else:
                    continue

            else:
                distance_message = ""

            if urgency_level == "Emergency":
                urgency_message = (
                    "REPORTED EMERGENCY - awaiting administrator "
                    "verification. "
                )
            elif urgency_level == "Urgent":
                urgency_message = "URGENT REQUEST. "
            else:
                urgency_message = "Normal priority request. "

            message = (
                f"{urgency_message}"
                f"New {blood_group} blood request at {hospital}, "
                f"{location}. "
                f"{distance_message}"
                f"Please check the request details."
            )

            cursor.execute("""
                INSERT INTO notifications
                (donor_id, request_id, message)
                VALUES (?, ?, ?)
            """, (donor_id, request_id, message))

        connection.commit()
        connection.close()

        return redirect(
            url_for("track_request", request_id=request_id)
        )

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


# Protected Admin Dashboard + Analytics
@app.route("/admin")
def admin():

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    connection = sqlite3.connect("blood_donation.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

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

    cursor.execute("""
        SELECT
            blood_requests.*,
            COALESCE(SUM(
                CASE
                    WHEN donor_responses.response = 'Interested'
                    THEN 1 ELSE 0
                END
            ), 0) AS interested_count,
            COALESCE(SUM(
                CASE
                    WHEN donor_responses.response = 'Unable to Donate'
                    THEN 1 ELSE 0
                END
            ), 0) AS unable_count,
            (
                SELECT COUNT(DISTINCT notifications.donor_id)
                FROM notifications
                WHERE notifications.request_id = blood_requests.id
            ) AS notified_count
        FROM blood_requests
        LEFT JOIN donor_responses
            ON blood_requests.id = donor_responses.request_id
        GROUP BY blood_requests.id
        ORDER BY blood_requests.id DESC
    """)

    requests = [dict(item) for item in cursor.fetchall()]

    for item in requests:

        if item["status"] != "Pending":
            item["priority"] = "Closed"
        else:
            try:
                units_required = int(item["units"])
            except (ValueError, TypeError):
                units_required = 1

            if units_required >= 3:
                item["priority"] = "High"
            elif units_required == 2:
                item["priority"] = "Medium"
            else:
                item["priority"] = "Low"

        # Emergency verification is separate from unit-based priority.
        item["urgency_level"] = item.get("urgency_level") or "Normal"
        item["emergency_verified"] = int(
            item.get("emergency_verified") or 0
        )
        item["is_verified_emergency"] = (
            item["urgency_level"] == "Emergency"
            and item["emergency_verified"] == 1
        )

    for item in requests:

        item["total_responses"] = (
            item["interested_count"] + item["unable_count"]
        )

        if item["notified_count"] > 0:
            item["response_rate"] = round(
                (item["total_responses"] / item["notified_count"]) * 100,
                2
            )
        else:
            item["response_rate"] = 0

        item["low_response"] = (
            item["notified_count"] > 0
            and item["response_rate"] < 50
        )

    total_notified = sum(item["notified_count"] for item in requests)
    total_responses = sum(item["total_responses"] for item in requests)

    if total_notified > 0:
        overall_response_rate = round(
            (total_responses / total_notified) * 100, 2
        )
    else:
        overall_response_rate = 0

    low_response_requests = sum(
        1 for item in requests if item["low_response"]
    )

    # Donor Response Time Analytics
    cursor.execute("""
        SELECT
            COUNT(
                CASE
                    WHEN donor_responses.responded_at IS NOT NULL
                    AND julianday(donor_responses.responded_at)
                        >= julianday(notifications.created_at)
                    THEN 1
                END
            ) AS completed_responses,
            ROUND(
                AVG(
                    CASE
                        WHEN donor_responses.responded_at IS NOT NULL
                        AND julianday(donor_responses.responded_at)
                            >= julianday(notifications.created_at)
                        THEN (
                            julianday(donor_responses.responded_at)
                            - julianday(notifications.created_at)
                        ) * 1440
                    END
                ), 2
            ) AS average_response_minutes,
            ROUND(
                MIN(
                    CASE
                        WHEN donor_responses.responded_at IS NOT NULL
                        AND julianday(donor_responses.responded_at)
                            >= julianday(notifications.created_at)
                        THEN (
                            julianday(donor_responses.responded_at)
                            - julianday(notifications.created_at)
                        ) * 1440
                    END
                ), 2
            ) AS fastest_response_minutes,
            ROUND(
                MAX(
                    CASE
                        WHEN donor_responses.responded_at IS NOT NULL
                        AND julianday(donor_responses.responded_at)
                            >= julianday(notifications.created_at)
                        THEN (
                            julianday(donor_responses.responded_at)
                            - julianday(notifications.created_at)
                        ) * 1440
                    END
                ), 2
            ) AS slowest_response_minutes,
            SUM(
                CASE
                    WHEN donor_responses.id IS NULL THEN 1
                    ELSE 0
                END
            ) AS pending_notifications
        FROM notifications
        LEFT JOIN donor_responses
            ON notifications.donor_id = donor_responses.donor_id
            AND notifications.request_id = donor_responses.request_id
    """)

    response_time_result = cursor.fetchone()

    average_response_minutes = (
        response_time_result["average_response_minutes"] or 0
    )
    fastest_response_minutes = response_time_result[
        "fastest_response_minutes"
    ]
    slowest_response_minutes = response_time_result[
        "slowest_response_minutes"
    ]
    pending_notifications = (
        response_time_result["pending_notifications"] or 0
    )
    completed_responses = (
        response_time_result["completed_responses"] or 0
    )

    # Donor Engagement Analytics
    cursor.execute("""
        SELECT
            COUNT(
                CASE WHEN response = 'Interested' THEN 1 END
            ) AS interested_total,
            COUNT(
                CASE WHEN response = 'Unable to Donate' THEN 1 END
            ) AS unable_total,
            COUNT(DISTINCT donor_id) AS active_donors
        FROM donor_responses
    """)

    engagement_result = cursor.fetchone()

    engagement_interested = engagement_result["interested_total"] or 0
    engagement_unable = engagement_result["unable_total"] or 0
    active_donor_count = engagement_result["active_donors"] or 0

    cursor.execute("""
        SELECT COUNT(DISTINCT donor_id)
        FROM notifications
    """)

    total_notified_donors = cursor.fetchone()[0] or 0

    if total_notified_donors > 0:
        donor_participation_rate = round(
            (active_donor_count / total_notified_donors) * 100, 2
        )
    else:
        donor_participation_rate = 0

    cursor.execute("""
        SELECT
            donors.id,
            donors.fullname,
            donors.blood_group,
            (
                SELECT COUNT(*) FROM notifications
                WHERE notifications.donor_id = donors.id
            ) AS notifications_received,
            (
                SELECT COUNT(*) FROM donor_responses
                WHERE donor_responses.donor_id = donors.id
            ) AS total_responses,
            (
                SELECT COUNT(*) FROM donor_responses
                WHERE donor_responses.donor_id = donors.id
                AND donor_responses.response = 'Interested'
            ) AS interested_responses,
            (
                SELECT COUNT(*) FROM donor_responses
                WHERE donor_responses.donor_id = donors.id
                AND donor_responses.response = 'Unable to Donate'
            ) AS unable_responses
        FROM donors
        WHERE EXISTS (
            SELECT 1 FROM donor_responses
            WHERE donor_responses.donor_id = donors.id
        )
        ORDER BY total_responses DESC, donors.fullname ASC
        LIMIT 10
    """)

    donor_engagement = [dict(item) for item in cursor.fetchall()]

    # Donation Progress Monitoring
    cursor.execute("""
        SELECT
            donation_progress.id,
            donation_progress.donor_id,
            donation_progress.request_id,
            donation_progress.progress_status,
            donation_progress.updated_at,
            donors.fullname,
            donors.blood_group,
            blood_requests.patient_name,
            blood_requests.hospital,
            blood_requests.status AS request_status
        FROM donation_progress
        JOIN donors
            ON donation_progress.donor_id = donors.id
        JOIN blood_requests
            ON donation_progress.request_id = blood_requests.id
        ORDER BY donation_progress.updated_at DESC
    """)

    donation_progress_records = [
        dict(item) for item in cursor.fetchall()
    ]

    total_donors = len(donors)
    total_requests = len(requests)

    outdated_donors = sum(
        1 for donor in donors if donor["is_outdated"] == 1
    )

    # Blood Request Status Analytics
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

    # Blood Group-wise Donor Analytics
    blood_groups = [
        "A+", "A-", "B+", "B-",
        "AB+", "AB-", "O+", "O-"
    ]

    donor_group_counts = {
        group: {"Available": 0, "Not Available": 0}
        for group in blood_groups
    }

    cursor.execute("""
        SELECT blood_group, availability, COUNT(*) AS total
        FROM donors
        GROUP BY blood_group, availability
    """)

    for item in cursor.fetchall():

        group = item["blood_group"]
        availability = item["availability"]

        if group in donor_group_counts and availability in [
            "Available", "Not Available"
        ]:
            donor_group_counts[group][availability] = item["total"]

    # Monthly Donor Registration Analytics
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

    # Monthly Donor Growth Insights
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
            # Blood Request Progress Insights
    total_donor_responses = sum(
        item["interested_count"] + item["unable_count"]
        for item in requests
    )

    requests_with_interested_donors = sum(
        1 for item in requests if item["interested_count"] > 0
    )

    requests_without_interested_donors = sum(
        1 for item in requests if item["interested_count"] == 0
    )

    pending_requests_needing_attention = sum(
        1 for item in requests
        if item["status"] == "Pending"
        and item["interested_count"] == 0
    )

    # Priority Summary Counts
    high_priority_requests = sum(
        1 for item in requests if item["priority"] == "High"
    )
    medium_priority_requests = sum(
        1 for item in requests if item["priority"] == "Medium"
    )
    low_priority_requests = sum(
        1 for item in requests if item["priority"] == "Low"
    )

    # Donor Registration Insights
    age_group_counts = {
        "18-25": 0,
        "26-35": 0,
        "36-45": 0,
        "46-60": 0,
        "Above 60": 0,
        "Unknown": 0
    }

    for donor in donors:

        try:
            age = int(donor["age"])

            if 18 <= age <= 25:
                age_group_counts["18-25"] += 1
            elif 26 <= age <= 35:
                age_group_counts["26-35"] += 1
            elif 36 <= age <= 45:
                age_group_counts["36-45"] += 1
            elif 46 <= age <= 60:
                age_group_counts["46-60"] += 1
            elif age > 60:
                age_group_counts["Above 60"] += 1
            else:
                age_group_counts["Unknown"] += 1

        except (ValueError, TypeError):
            age_group_counts["Unknown"] += 1

    gender_counts = {
        "Male": 0,
        "Female": 0,
        "Other": 0,
        "Not Specified": 0
    }

    for donor in donors:

        gender = str(donor["gender"] or "").strip().lower()

        if gender == "male":
            gender_counts["Male"] += 1
        elif gender == "female":
            gender_counts["Female"] += 1
        elif gender == "other":
            gender_counts["Other"] += 1
        else:
            gender_counts["Not Specified"] += 1

    # Location-wise Donor Distribution
    location_counts = {}

    for donor in donors:

        location = str(donor["location"] or "").strip()

        if not location:
            location = "Not Specified"

        location_counts[location] = (
            location_counts.get(location, 0) + 1
        )

    location_counts = dict(
        sorted(
            location_counts.items(),
            key=lambda item: item[1],
            reverse=True
        )
    )

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
        growth_percentage=growth_percentage,
        total_donor_responses=total_donor_responses,
        requests_with_interested_donors=requests_with_interested_donors,
        requests_without_interested_donors=requests_without_interested_donors,
        pending_requests_needing_attention=pending_requests_needing_attention,
        high_priority_requests=high_priority_requests,
        medium_priority_requests=medium_priority_requests,
        low_priority_requests=low_priority_requests,
        age_group_counts=age_group_counts,
        gender_counts=gender_counts,
        location_counts=location_counts,
        total_notified=total_notified,
        total_responses=total_responses,
        overall_response_rate=overall_response_rate,
        low_response_requests=low_response_requests,
        average_response_minutes=average_response_minutes,
        fastest_response_minutes=fastest_response_minutes,
        slowest_response_minutes=slowest_response_minutes,
        pending_notifications=pending_notifications,
        completed_responses=completed_responses,
        engagement_interested=engagement_interested,
        engagement_unable=engagement_unable,
        active_donor_count=active_donor_count,
        total_notified_donors=total_notified_donors,
        donor_participation_rate=donor_participation_rate,
        donor_engagement=donor_engagement,
        donation_progress_records=donation_progress_records
    )


# Admin verifies an emergency blood request
@app.route(
    "/verify_emergency/<int:request_id>",
    methods=["POST"]
)
def verify_emergency(request_id):

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    connection = sqlite3.connect("blood_donation.db")
    cursor = connection.cursor()

    cursor.execute("""
        SELECT urgency_level, emergency_verified, status
        FROM blood_requests
        WHERE id = ?
    """, (request_id,))

    blood_request = cursor.fetchone()

    if blood_request is None:
        connection.close()
        return "Blood request not found."

    urgency_level, emergency_verified, status = blood_request

    if urgency_level != "Emergency":
        connection.close()
        return "Only requests marked as Emergency can be verified."

    if status in ["Fulfilled", "Cancelled"]:
        connection.close()
        return "Closed requests cannot be verified."

    if emergency_verified == 1:
        connection.close()
        return redirect(url_for("admin"))

    cursor.execute("""
        UPDATE blood_requests
        SET emergency_verified = 1,
            verified_by = ?,
            verified_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (ADMIN_USERNAME, request_id))

    # Update notifications so donors can distinguish a verified emergency.
    cursor.execute("""
        UPDATE notifications
        SET message = REPLACE(
            message,
            'REPORTED EMERGENCY - awaiting administrator verification.',
            'ADMIN-VERIFIED EMERGENCY.'
        )
        WHERE request_id = ?
    """, (request_id,))

    connection.commit()
    connection.close()

    return redirect(url_for("admin"))


# Download Blood Request Report as CSV
@app.route("/download_report")
def download_report():

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    connection = sqlite3.connect("blood_donation.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            blood_requests.*,
            COALESCE(SUM(
                CASE
                    WHEN donor_responses.response = 'Interested'
                    THEN 1 ELSE 0
                END
            ), 0) AS interested_count,
            COALESCE(SUM(
                CASE
                    WHEN donor_responses.response = 'Unable to Donate'
                    THEN 1 ELSE 0
                END
            ), 0) AS unable_count
        FROM blood_requests
        LEFT JOIN donor_responses
            ON blood_requests.id = donor_responses.request_id
        GROUP BY blood_requests.id
        ORDER BY blood_requests.id DESC
    """)

    report_requests = cursor.fetchall()
    connection.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Request ID", "Patient Name", "Age", "Blood Group",
        "Units Required", "Hospital", "Location", "Phone",
        "Additional Information", "Request Status", "Unit-Based Priority",
        "Urgency Level", "Emergency Verified", "Verified By",
        "Verified At", "Interested Donors",
        "Unable to Donate Responses"
    ])

    for item in report_requests:

        if item["status"] != "Pending":
            priority = "Closed"
        else:
            try:
                units_required = int(item["units"])
            except (ValueError, TypeError):
                units_required = 1

            if units_required >= 3:
                priority = "High"
            elif units_required == 2:
                priority = "Medium"
            else:
                priority = "Low"

        writer.writerow([
            item["id"],
            item["patient_name"],
            item["age"],
            item["blood_group"],
            item["units"],
            item["hospital"],
            item["location"],
            item["phone"],
            item["additional_info"],
            item["status"],
            priority,
            item["urgency_level"] or "Normal",
            "Yes" if item["emergency_verified"] else "No",
            item["verified_by"] or "",
            item["verified_at"] or "",
            item["interested_count"],
            item["unable_count"]
        ])

    csv_data = output.getvalue()
    output.close()

    return Response(
        "\ufeff" + csv_data,
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=blood_donation_report.csv"
        }
    )


# Download Donor Availability Report as CSV
@app.route("/download_donor_report")
def download_donor_report():

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    connection = sqlite3.connect("blood_donation.db")
    cursor = connection.cursor()

    blood_groups = [
        "A+", "A-", "B+", "B-",
        "AB+", "AB-", "O+", "O-"
    ]

    cursor.execute("""
        SELECT blood_group, availability, COUNT(*)
        FROM donors
        GROUP BY blood_group, availability
    """)

    results = cursor.fetchall()
    connection.close()

    donor_counts = {
        group: {"Available": 0, "Not Available": 0}
        for group in blood_groups
    }

    for group, availability, total in results:

        if group in donor_counts and availability in [
            "Available", "Not Available"
        ]:
            donor_counts[group][availability] = total

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Blood Group", "Available Donors",
        "Not Available Donors", "Total Donors"
    ])

    for group in blood_groups:

        available = donor_counts[group]["Available"]
        unavailable = donor_counts[group]["Not Available"]

        writer.writerow([
            group, available, unavailable,
            available + unavailable
        ])

    csv_data = output.getvalue()
    output.close()

    return Response(
        "\ufeff" + csv_data,
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=donor_availability_report.csv"
        }
    )


# Download Donor Registration Report as CSV
@app.route("/download_registration_report")
def download_registration_report():

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    connection = sqlite3.connect("blood_donation.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id, fullname, age, gender, blood_group,
            phone, email, location, availability, registered_at
        FROM donors
        ORDER BY registered_at DESC, id DESC
    """)

    donor_records = cursor.fetchall()
    connection.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Donor ID", "Full Name", "Age", "Gender",
        "Blood Group", "Phone Number", "Email", "Location",
        "Availability", "Registration Date"
    ])

    for donor in donor_records:
        writer.writerow([
            donor["id"], donor["fullname"], donor["age"],
            donor["gender"], donor["blood_group"], donor["phone"],
            donor["email"], donor["location"],
            donor["availability"], donor["registered_at"]
        ])

    csv_data = output.getvalue()
    output.close()

    return Response(
        "\ufeff" + csv_data,
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=donor_registration_report.csv"
        }
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


# GPS-Based Intelligent Donor Matching
@app.route("/match", methods=["GET", "POST"])
def match_donors():

    matched_donors = []
    blood_group = ""
    location = ""
    latitude = ""
    longitude = ""
    searched = False
    gps_search = False

    if request.method == "POST":

        blood_group = request.form.get("blood_group", "").strip()
        location = request.form.get("location", "").strip()
        latitude = request.form.get("latitude", "").strip()
        longitude = request.form.get("longitude", "").strip()
        searched = True

    elif request.args.get("blood_group"):

        blood_group = request.args.get("blood_group", "").strip()
        location = request.args.get("location", "").strip()
        latitude = request.args.get("latitude", "").strip()
        longitude = request.args.get("longitude", "").strip()
        searched = True

    if searched:

        if blood_group not in [
            "A+", "A-", "B+", "B-",
            "AB+", "AB-", "O+", "O-"
        ]:
            return "Please select a valid blood group."

        patient_latitude = get_coordinate(latitude)
        patient_longitude = get_coordinate(longitude)

        if (
            (patient_latitude is None and patient_longitude is not None)
            or
            (patient_latitude is not None and patient_longitude is None)
        ):
            return "Please provide both GPS coordinates."

        if patient_latitude is not None:

            if not (-90 <= patient_latitude <= 90):
                return "Invalid patient latitude."

            if not (-180 <= patient_longitude <= 180):
                return "Invalid patient longitude."

            gps_search = True

        connection = sqlite3.connect("blood_donation.db")
        cursor = connection.cursor()

        cursor.execute("""
            SELECT *
            FROM donors
            WHERE blood_group = ?
            AND availability = 'Available'
        """, (blood_group,))

        all_donors = cursor.fetchall()
        connection.close()

        if gps_search:

            for donor in all_donors:

                donor_latitude = get_coordinate(donor[12])
                donor_longitude = get_coordinate(donor[13])

                if (
                    donor_latitude is None
                    or donor_longitude is None
                ):
                    continue

                distance = calculate_distance(
                    patient_latitude,
                    patient_longitude,
                    donor_latitude,
                    donor_longitude
                )

                if distance <= MAX_DONOR_DISTANCE:
                    matched_donors.append(
                        donor + (round(distance, 2),)
                    )

            matched_donors.sort(key=lambda donor: donor[-1])

        else:

            def calculate_score(donor):

                donor_location = (
                    donor[7] or ""
                ).strip().lower()

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

            matched_donors = [
                donor + (None,)
                for donor in matched_donors
            ]

    return render_template(
        "match.html",
        donors=matched_donors,
        blood_group=blood_group,
        location=location,
        latitude=latitude,
        longitude=longitude,
        searched=searched,
        gps_search=gps_search
    )


# Donor Transport Submission with Pickup GPS
@app.route("/transport", methods=["GET", "POST"])
def transport():

    if request.method == "POST":

        donor_name = request.form["donor_name"].strip()
        phone = request.form["phone"].strip()
        pickup_location = request.form["pickup_location"].strip()
        destination = request.form["destination"].strip()
        travel_date = request.form["travel_date"]
        travel_time = request.form["travel_time"]
        available_seats = request.form["available_seats"]
        notes = request.form.get("notes", "")

        pickup_latitude = get_coordinate(
            request.form.get("pickup_latitude")
        )

        pickup_longitude = get_coordinate(
            request.form.get("pickup_longitude")
        )

        if pickup_latitude is None or pickup_longitude is None:
            return """
            <h1>GPS Location Required</h1>
            <p>Please capture your pickup GPS location before submitting.</p>
            <a href="/transport">Go Back</a>
            """

        if not (-90 <= pickup_latitude <= 90):
            return "Invalid pickup latitude."

        if not (-180 <= pickup_longitude <= 180):
            return "Invalid pickup longitude."

        connection = sqlite3.connect("blood_donation.db")
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO transport_requests
            (
                donor_name,
                phone,
                pickup_location,
                destination,
                travel_date,
                travel_time,
                available_seats,
                notes,
                pickup_latitude,
                pickup_longitude
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            donor_name,
            phone,
            pickup_location,
            destination,
            travel_date,
            travel_time,
            available_seats,
            notes,
            pickup_latitude,
            pickup_longitude
        ))

        connection.commit()
        connection.close()

        return redirect(url_for("available_rides"))

    return render_template("transport.html")


# Group nearby rides using K-Means clustering
# Rides must share travel date and destination.
# Every pair in a group must be within 5 km.
def cluster_rides_by_pickup(rides):

    rides_by_trip = {}
    rides_without_gps = []

    for ride in rides:
        latitude = get_coordinate(ride[9])
        longitude = get_coordinate(ride[10])

        if latitude is None or longitude is None:
            rides_without_gps.append(ride)
            continue

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            rides_without_gps.append(ride)
            continue

        trip_key = (
            str(ride[5] or "").strip(),
            str(ride[4] or "").strip().casefold()
        )

        rides_by_trip.setdefault(trip_key, []).append(
            (ride, latitude, longitude)
        )

    ride_groups = []
    group_number = 1

    for trip_key, trip_rides in rides_by_trip.items():

        if len(trip_rides) < 2:
            rides_without_gps.extend(item[0] for item in trip_rides)
            continue

        average_latitude = (
            sum(item[1] for item in trip_rides) / len(trip_rides)
        )

        longitude_scale = max(
            0.01,
            math.cos(math.radians(average_latitude))
        )

        coordinates_km = [
            [
                latitude * 111.32,
                longitude * 111.32 * longitude_scale
            ]
            for _, latitude, longitude in trip_rides
        ]

        best_clusters = []
        best_grouped_count = 0

        for cluster_count in range(1, len(trip_rides)):

            try:
                model = KMeans(
                    n_clusters=cluster_count,
                    random_state=42,
                    n_init=10
                )

                labels = model.fit_predict(coordinates_km)

            except (ValueError, TypeError):
                continue

            candidate_clusters = []
            grouped_count = 0

            for label in set(labels):

                member_indices = [
                    index
                    for index, assigned_label in enumerate(labels)
                    if assigned_label == label
                ]

                if len(member_indices) < 2:
                    continue

                maximum_pair_distance = 0.0

                for first_position in range(len(member_indices)):

                    for second_position in range(
                        first_position + 1,
                        len(member_indices)
                    ):

                        first = trip_rides[
                            member_indices[first_position]
                        ]

                        second = trip_rides[
                            member_indices[second_position]
                        ]

                        pair_distance = calculate_distance(
                            first[1], first[2],
                            second[1], second[2]
                        )

                        maximum_pair_distance = max(
                            maximum_pair_distance,
                            pair_distance
                        )

                if maximum_pair_distance <= MAX_PICKUP_GROUP_DISTANCE_KM:
                    candidate_clusters.append(member_indices)
                    grouped_count += len(member_indices)

            if grouped_count > best_grouped_count:
                best_grouped_count = grouped_count
                best_clusters = candidate_clusters

        grouped_indices = set()

        for cluster in best_clusters:

            grouped_rides = [
                trip_rides[index][0] for index in cluster
            ]

            grouped_indices.update(cluster)

            center_latitude = sum(
                trip_rides[index][1] for index in cluster
            ) / len(cluster)

            center_longitude = sum(
                trip_rides[index][2] for index in cluster
            ) / len(cluster)

            ride_groups.append({
                "group_name": f"Pickup Group {group_number}",
                "travel_date": trip_key[0],
                "destination": grouped_rides[0][4],
                "rides": grouped_rides,
                "center_latitude": round(center_latitude, 6),
                "center_longitude": round(center_longitude, 6)
            })

            group_number += 1

        for index, item in enumerate(trip_rides):

            if index not in grouped_indices:
                rides_without_gps.append(item[0])

    rides_without_gps.sort(
        key=lambda ride: (
            str(ride[5] or ""),
            str(ride[6] or "")
        )
    )

    ride_groups.sort(
        key=lambda group: (
            str(group["travel_date"]),
            str(group["destination"])
        )
    )

    return ride_groups, rides_without_gps


# View Available Rides and display K-Means pickup groups
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

    ride_groups, ungrouped_rides = cluster_rides_by_pickup(rides)

    return render_template(
        "rides.html",
        rides=rides,
        ride_groups=ride_groups,
        ungrouped_rides=ungrouped_rides,
        pickup_group_distance_km=MAX_PICKUP_GROUP_DISTANCE_KM
    )

# View Only Logged-in Donor's Notifications
@app.route("/notifications")
def view_notifications():

    if "donor_id" not in session:
        return redirect(url_for("login"))

    connection = sqlite3.connect("blood_donation.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    donor_id = session["donor_id"]

    cursor.execute("""
        INSERT OR IGNORE INTO donation_progress
            (donor_id, request_id, progress_status)
        SELECT donor_id, request_id, 'Interested'
        FROM donor_responses
        WHERE donor_id = ?
        AND response = 'Interested'
    """, (donor_id,))

    connection.commit()

    cursor.execute("""
        SELECT
            notifications.id AS notification_id,
            notifications.request_id,
            notifications.message,
            notifications.created_at,
            notifications.is_read,
            blood_requests.patient_name,
            blood_requests.age,
            blood_requests.blood_group,
            blood_requests.units,
            blood_requests.hospital,
            blood_requests.location,
            blood_requests.phone,
            blood_requests.additional_info,
            blood_requests.status,
            blood_requests.urgency_level,
            blood_requests.emergency_verified,
            donor_responses.response AS donor_response,
            donation_progress.progress_status,
            donation_progress.updated_at AS progress_updated_at
        FROM notifications
        JOIN blood_requests
            ON notifications.request_id = blood_requests.id
        LEFT JOIN donor_responses
            ON donor_responses.request_id = notifications.request_id
            AND donor_responses.donor_id = notifications.donor_id
        LEFT JOIN donation_progress
            ON donation_progress.request_id = notifications.request_id
            AND donation_progress.donor_id = notifications.donor_id
        WHERE notifications.donor_id = ?
        ORDER BY notifications.id DESC
    """, (donor_id,))

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


# Donor Responds to a Blood Request
@app.route("/respond/<int:request_id>", methods=["POST"])
def respond_to_request(request_id):

    if "donor_id" not in session:
        return redirect(url_for("login"))

    donor_id = session["donor_id"]
    response = request.form.get("response", "")

    if response not in ALLOWED_RESPONSES:
        return "Invalid response."

    connection = sqlite3.connect("blood_donation.db")
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id
        FROM notifications
        WHERE donor_id = ? AND request_id = ?
        LIMIT 1
    """, (donor_id, request_id))

    notification = cursor.fetchone()

    if notification is None:
        connection.close()
        return "You are not authorized to respond to this request."

    cursor.execute("""
        SELECT status
        FROM blood_requests
        WHERE id = ?
    """, (request_id,))

    blood_request = cursor.fetchone()

    if blood_request is None:
        connection.close()
        return "Blood request not found."

    if blood_request[0] in ["Fulfilled", "Cancelled"]:
        connection.close()
        return "This blood request is no longer accepting responses."

    cursor.execute("""
        INSERT INTO donor_responses
            (donor_id, request_id, response)
        VALUES (?, ?, ?)
        ON CONFLICT(donor_id, request_id)
        DO UPDATE SET
            response = excluded.response,
            responded_at = CURRENT_TIMESTAMP
    """, (donor_id, request_id, response))

    if response == "Interested":

        cursor.execute("""
            INSERT INTO donation_progress
                (donor_id, request_id, progress_status, updated_at)
            VALUES (?, ?, 'Interested', CURRENT_TIMESTAMP)
            ON CONFLICT(donor_id, request_id)
            DO UPDATE SET
                progress_status = 'Interested',
                updated_at = CURRENT_TIMESTAMP
        """, (donor_id, request_id))

    else:

        cursor.execute("""
            DELETE FROM donation_progress
            WHERE donor_id = ? AND request_id = ?
        """, (donor_id, request_id))

    connection.commit()
    connection.close()

    return redirect(url_for("view_notifications"))


# Donor Updates Donation Progress
@app.route(
    "/update_donation_progress/<int:request_id>",
    methods=["POST"]
)
def update_donation_progress(request_id):

    if "donor_id" not in session:
        return redirect(url_for("login"))

    donor_id = session["donor_id"]
    new_progress = request.form.get("progress_status", "")

    allowed_updates = [
        "On the Way",
        "Reached Hospital",
        "Donation Completed"
    ]

    if new_progress not in allowed_updates:
        return "Invalid donation progress status."

    connection = sqlite3.connect("blood_donation.db")
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id
        FROM notifications
        WHERE donor_id = ? AND request_id = ?
        LIMIT 1
    """, (donor_id, request_id))

    notification = cursor.fetchone()

    if notification is None:
        connection.close()
        return "You are not authorized to update this request."

    cursor.execute("""
        SELECT response
        FROM donor_responses
        WHERE donor_id = ? AND request_id = ?
    """, (donor_id, request_id))

    donor_response = cursor.fetchone()

    if donor_response is None or donor_response[0] != "Interested":
        connection.close()
        return "Please select Interested before updating donation progress."

    cursor.execute("""
        SELECT status
        FROM blood_requests
        WHERE id = ?
    """, (request_id,))

    blood_request = cursor.fetchone()

    if blood_request is None:
        connection.close()
        return "Blood request not found."

    if blood_request[0] in ["Fulfilled", "Cancelled"]:
        connection.close()
        return "This blood request is already closed."

    cursor.execute("""
        SELECT progress_status
        FROM donation_progress
        WHERE donor_id = ? AND request_id = ?
    """, (donor_id, request_id))

    current_progress = cursor.fetchone()

    if current_progress is None:
        connection.close()
        return (
            "Donation progress record not found. "
            "Please respond Interested again."
        )

    current_status = current_progress[0]

    progress_order = [
        "Interested",
        "On the Way",
        "Reached Hospital",
        "Donation Completed"
    ]

    current_index = progress_order.index(current_status)
    new_index = progress_order.index(new_progress)

    if new_index != current_index + 1:
        connection.close()
        return (
            "Invalid progress sequence. Please update to the next "
            "stage in order."
        )

    cursor.execute("""
        UPDATE donation_progress
        SET progress_status = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE donor_id = ? AND request_id = ?
    """, (new_progress, donor_id, request_id))

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


# Dijkstra and A* Route Optimization Demo
def optimize_sample_route(start, destination):

    graph_path = "road_data/demo_roads.graphml"

    try:
        G = nx.read_graphml(graph_path)

        if start not in G or destination not in G:
            return None

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

        def heuristic(node1, node2):

            x1, y1 = coordinates[node1]
            x2, y2 = coordinates[node2]

            return math.sqrt(
                (x2 - x1) ** 2 + (y2 - y1) ** 2
            )

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


@app.route("/optimize_route", methods=["GET", "POST"])
def optimize_route():

    result = None
    error = None
    start = "A"
    destination = "F"

    allowed_nodes = ["A", "B", "C", "D", "E", "F"]

    if request.method == "POST":

        start = request.form.get("start", "A").strip().upper()
        destination = request.form.get(
            "destination", "F"
        ).strip().upper()

        if start not in allowed_nodes or destination not in allowed_nodes:
            error = "Please select valid junctions."

        elif start == destination:
            error = "Starting point and destination must be different."

        else:
            result = optimize_sample_route(start, destination)

            if result is None:
                error = (
                    "Route could not be calculated. Check that the "
                    "sample road network exists."
                )

    start_options = "".join(
        f'<option value="{node}" '
        f'{"selected" if node == start else ""}>{node}</option>'
        for node in allowed_nodes
    )

    destination_options = "".join(
        f'<option value="{node}" '
        f'{"selected" if node == destination else ""}>{node}</option>'
        for node in allowed_nodes
    )

    result_html = ""

    if result:

        result_html = f"""
        <div class="result">
            <h3>Dijkstra Algorithm</h3>
            <p>Route: {" → ".join(result['dijkstra_route'])}</p>
            <p>Distance: {result['dijkstra_distance']} metres</p>

            <h3>A* Algorithm</h3>
            <p>Route: {" → ".join(result['astar_route'])}</p>
            <p>Distance: {result['astar_distance']} metres</p>
        </div>
        """

    error_html = (
        f'<p style="color:#b71c1c">{error}</p>'
        if error else ""
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Route Optimization</title>
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
            }}
            .result {{
                background: #f1f8e9;
                padding: 15px;
                margin-top: 15px;
                border-radius: 8px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Blood Donation Route Optimization</h2>
            <p>
                <b>Demonstration:</b> Uses a locally stored sample road
                network, not a live road map.
            </p>

            <form method="POST">
                <label>Starting Junction</label>
                <select name="start">{start_options}</select>

                <label>Destination Junction</label>
                <select name="destination">{destination_options}</select>

                <button type="submit">Calculate Shortest Route</button>
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
