import sqlite3

connection = sqlite3.connect("blood_donation.db")
cursor = connection.cursor()

cursor.execute("""
    SELECT id, patient_name, blood_group, latitude, longitude
    FROM blood_requests
    ORDER BY id DESC
    LIMIT 5
""")

requests = cursor.fetchall()

print("\n===== LATEST BLOOD REQUESTS =====")

for request in requests:
    print(request)

connection.close()