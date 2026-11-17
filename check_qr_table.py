import sqlite3

connection = sqlite3.connect("blood_donation.db")
cursor = connection.cursor()

cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    AND name = 'qr_verifications'
""")

result = cursor.fetchone()

if result:
    print("SUCCESS: QR verification table exists!")
else:
    print("ERROR: QR verification table not found.")

connection.close()