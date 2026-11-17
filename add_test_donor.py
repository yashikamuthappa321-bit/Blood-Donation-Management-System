
import sqlite3
import math

DATABASE = "blood_donation.db"
REQUEST_ID = 7

connection = sqlite3.connect(DATABASE)
cursor = connection.cursor()

try:
    # Read the existing blood request
    cursor.execute("""
        SELECT blood_group, latitude, longitude
        FROM blood_requests
        WHERE id = ?
    """, (REQUEST_ID,))

    request = cursor.fetchone()

    if request is None:
        print("Test stopped: Blood Request #7 was not found.")
    elif request[1] is None or request[2] is None:
        print("Test stopped: Request GPS coordinates are missing.")
    else:
        blood_group, request_lat, request_lon = request

        # Check whether this temporary donor already exists
        test_email = "day40_test_donor@example.com"

        cursor.execute(
            "SELECT id FROM donors WHERE email = ?",
            (test_email,)
        )

        existing = cursor.fetchone()

        if existing:
            print("Temporary test donor already exists.")
            print("Donor ID:", existing[0])

        else:
            # Calculate longitude offset for approximately 30 km
            distance_km = 30

            longitude_offset = distance_km / (
                111.32 * math.cos(math.radians(request_lat))
            )

            test_latitude = request_lat
            test_longitude = request_lon + longitude_offset

            cursor.execute("""
                INSERT INTO donors (
                    fullname,
                    age,
                    gender,
                    blood_group,
                    phone,
                    email,
                    location,
                    availability,
                    latitude,
                    longitude,
                    registered_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                "DAY40 TEST DONOR",
                25,
                "Other",
                blood_group,
                "0000000000",
                test_email,
                "Temporary Distance Test",
                "Available",
                test_latitude,
                test_longitude
            ))

            connection.commit()

            print("Temporary test donor added successfully!")
            print("Donor ID:", cursor.lastrowid)
            print("Blood Group:", blood_group)
            print("Latitude:", test_latitude)
            print("Longitude:", test_longitude)
            print("Approximate distance: 30 km")

except Exception as error:
    connection.rollback()
    print("Test donor was not added.")
    print("Error:", error)

finally:
    connection.close()
