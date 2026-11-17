
import sqlite3


def create_database():

    connection = sqlite3.connect("blood_donation.db")
    cursor = connection.cursor()

    # Donors Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fullname TEXT NOT NULL,
            age INTEGER NOT NULL,
            gender TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT NOT NULL,
            location TEXT NOT NULL
        )
    """)

    cursor.execute("PRAGMA table_info(donors)")
    columns = [column[1] for column in cursor.fetchall()]

    if "availability" not in columns:
        cursor.execute("""
            ALTER TABLE donors
            ADD COLUMN availability TEXT NOT NULL DEFAULT 'Available'
        """)

    if "password_hash" not in columns:
        cursor.execute("""
            ALTER TABLE donors
            ADD COLUMN password_hash TEXT
        """)

    if "availability_updated_at" not in columns:
        cursor.execute("""
            ALTER TABLE donors
            ADD COLUMN availability_updated_at TEXT
        """)

    if "registered_at" not in columns:
        cursor.execute("""
            ALTER TABLE donors
            ADD COLUMN registered_at TEXT
        """)

    if "latitude" not in columns:
        cursor.execute("""
            ALTER TABLE donors
            ADD COLUMN latitude REAL
        """)

    if "longitude" not in columns:
        cursor.execute("""
            ALTER TABLE donors
            ADD COLUMN longitude REAL
        """)

    cursor.execute("""
        UPDATE donors
        SET registered_at = CURRENT_TIMESTAMP
        WHERE registered_at IS NULL
    """)

    # Blood Requests Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blood_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            age INTEGER NOT NULL,
            blood_group TEXT NOT NULL,
            units INTEGER NOT NULL,
            hospital TEXT NOT NULL,
            location TEXT NOT NULL,
            phone TEXT NOT NULL,
            additional_info TEXT
        )
    """)

    cursor.execute("PRAGMA table_info(blood_requests)")
    request_columns = [
        column[1] for column in cursor.fetchall()
    ]

    if "status" not in request_columns:
        cursor.execute("""
            ALTER TABLE blood_requests
            ADD COLUMN status TEXT NOT NULL DEFAULT 'Pending'
        """)

    if "latitude" not in request_columns:
        cursor.execute("""
            ALTER TABLE blood_requests
            ADD COLUMN latitude REAL
        """)

    if "longitude" not in request_columns:
        cursor.execute("""
            ALTER TABLE blood_requests
            ADD COLUMN longitude REAL
        """)

    # Emergency Blood Request Prioritization Migration

    if "urgency_level" not in request_columns:
        cursor.execute("""
            ALTER TABLE blood_requests
            ADD COLUMN urgency_level TEXT NOT NULL DEFAULT 'Normal'
        """)

    if "emergency_verified" not in request_columns:
        cursor.execute("""
            ALTER TABLE blood_requests
            ADD COLUMN emergency_verified INTEGER NOT NULL DEFAULT 0
        """)

    if "verified_by" not in request_columns:
        cursor.execute("""
            ALTER TABLE blood_requests
            ADD COLUMN verified_by TEXT
        """)

    if "verified_at" not in request_columns:
        cursor.execute("""
            ALTER TABLE blood_requests
            ADD COLUMN verified_at TEXT
        """)

    # Transport / Ride-Sharing Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transport_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donor_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            pickup_location TEXT NOT NULL,
            destination TEXT NOT NULL,
            travel_date TEXT NOT NULL,
            travel_time TEXT NOT NULL,
            available_seats INTEGER NOT NULL,
            notes TEXT
        )
    """)

    # Ride-Sharing GPS Coordinate Migration
    cursor.execute("PRAGMA table_info(transport_requests)")
    transport_columns = [
        column[1] for column in cursor.fetchall()
    ]

    if "pickup_latitude" not in transport_columns:
        cursor.execute("""
            ALTER TABLE transport_requests
            ADD COLUMN pickup_latitude REAL
        """)

    if "pickup_longitude" not in transport_columns:
        cursor.execute("""
            ALTER TABLE transport_requests
            ADD COLUMN pickup_longitude REAL
        """)

    if "destination_latitude" not in transport_columns:
        cursor.execute("""
            ALTER TABLE transport_requests
            ADD COLUMN destination_latitude REAL
        """)

    if "destination_longitude" not in transport_columns:
        cursor.execute("""
            ALTER TABLE transport_requests
            ADD COLUMN destination_longitude REAL
        """)

    # Donor Notifications Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donor_id INTEGER NOT NULL,
            request_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_read INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (donor_id) REFERENCES donors(id),
            FOREIGN KEY (request_id) REFERENCES blood_requests(id)
        )
    """)

    # Donor Responses Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donor_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donor_id INTEGER NOT NULL,
            request_id INTEGER NOT NULL,
            response TEXT NOT NULL
                CHECK(response IN ('Interested', 'Unable to Donate')),
            responded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(donor_id, request_id),
            FOREIGN KEY (donor_id) REFERENCES donors(id),
            FOREIGN KEY (request_id) REFERENCES blood_requests(id)
        )
    """)

    # Donation Progress Tracking Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS donation_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donor_id INTEGER NOT NULL,
            request_id INTEGER NOT NULL,

            progress_status TEXT NOT NULL DEFAULT 'Interested'
                CHECK(progress_status IN (
                    'Interested',
                    'On the Way',
                    'Reached Hospital',
                    'Donation Completed'
                )),

            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(donor_id, request_id),

            FOREIGN KEY (donor_id) REFERENCES donors(id),
            FOREIGN KEY (request_id) REFERENCES blood_requests(id)
        )
    """)
    # QR-Based Donation Verification Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS qr_verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donor_id INTEGER NOT NULL,
            request_id INTEGER NOT NULL,
            qr_token TEXT NOT NULL UNIQUE,
            is_verified INTEGER NOT NULL DEFAULT 0,
            generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            verified_at TEXT,
            FOREIGN KEY (donor_id) REFERENCES donors(id),
            FOREIGN KEY (request_id) REFERENCES blood_requests(id)
        )
    """)
    connection.commit()
    connection.close()

    print("Database and all tables created successfully!")


if __name__ == "__main__":
    create_database()
