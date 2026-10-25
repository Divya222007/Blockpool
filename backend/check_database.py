
import database

database.initialize_database()

connection = database.get_connection()

tables = connection.execute(
    "SELECT name FROM sqlite_master WHERE type = ? ORDER BY name",
    ("table",)
).fetchall()

print("\nDatabase tables:")
for table in tables:
    print("-", table["name"])

connection.close()

