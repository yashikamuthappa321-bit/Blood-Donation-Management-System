
import sqlite3
import math


DATABASE = "blood_donation.db"
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
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return earth_radius * c


def test_distance_filter():

    # Simulated blood request location
    request_latitude = 12.2958
    request_longitude = 76.6394

    # Simulated donor locations
    test_donors = [
        {
            "name": "Nearby Donor",
            "latitude": 12.2958,
            "longitude": 76.7000
        },
        {
            "name": "Distant Donor",
            "latitude": 12.2958,
            "longitude": 76.9000
        }
    ]

    print("\n===== BLOOD DONATION DISTANCE TEST =====")

    for donor in test_donors:

        distance = calculate_distance(
            request_latitude,
            request_longitude,
            donor["latitude"],
            donor["longitude"]
        )

        print("\nDonor:", donor["name"])
        print("Distance:", round(distance, 2), "km")

        if distance <= MAX_DONOR_DISTANCE:
            print("Result: ELIGIBLE TO RECEIVE NOTIFICATION")
        else:
            print("Result: NOT ELIGIBLE - BEYOND 20 KM")

    print("\n===== TEST COMPLETED =====")


if __name__ == "__main__":
    test_distance_filter()
