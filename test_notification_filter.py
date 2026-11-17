
import sqlite3
import math

DATABASE = "blood_donation.db"
REQUEST_ID = 8
MAX_DONOR_DISTANCE = 20


def calculate_distance(lat1, lon1, lat2, lon2):
    earth_radius = 6371

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return earth_radius * c


connection = sqlite3.connect(DATABASE)
cursor = connection.cursor()

cursor.execute("""
    SELECT id, blood_group, latitude, longitude
    FROM blood_requests
    WHERE id = ?
""", (REQUEST_ID,))

request = cursor.fetchone()

if not request:
    print("Request not found!")
    connection.close()
    raise SystemExit

request_id, blood_group, req_lat, req_lon = request

print("\n===== ACTUAL NOTIFICATION FILTER TEST =====")
print("Blood Request ID:", request_id)
print("Required Blood Group:", blood_group)

print("\nChecking donors and notifications...\n")

cursor.execute("""
    SELECT id, fullname, latitude, longitude
    FROM donors
    WHERE blood_group = ?
      AND availability = 'Available'
""", (blood_group,))

donors = cursor.fetchall()

for donor in donors:
    donor_id, name, lat, lon = donor

    if lat is None or lon is None or req_lat is None or req_lon is None:
        print(name, "- Missing GPS")
        continue

    distance = calculate_distance(req_lat, req_lon, lat, lon)

    cursor.execute("""
        SELECT COUNT(*)
        FROM notifications
        WHERE donor_id = ? AND request_id = ?
    """, (donor_id, request_id))

    notification_count = cursor.fetchone()[0]

    expected = (
        "Eligible" if distance <= MAX_DONOR_DISTANCE
        else "Excluded"
    )

    actual = (
        "Notification exists"
        if notification_count > 0
        else "No notification"
    )

    print("Donor:", name)
    print("Distance:", round(distance, 2), "km")
    print("Expected:", expected)
    print("Actual:", actual)
    print("----------------------------------")

connection.close()
