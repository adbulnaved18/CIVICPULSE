import sys
import os

sys.path.insert(0, os.path.abspath("."))

from fastapi.testclient import TestClient
from app.main import app
from app.services.database import initialize_database, get_db

print("Running database initialization...")
initialize_database()
print("Database initialized successfully.")

client = TestClient(app)

print("\nTesting GET /ai/health...")
response = client.get("/ai/health")
print("Response status:", response.status_code)
print("Response JSON:", response.json())

# Check if tables were created
db = get_db()
cursor = db.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row["name"] for row in cursor.fetchall()]
print("\nDatabase tables:", tables)

if "report_ai_analyses" in tables:
    print("report_ai_analyses table exists!")
else:
    print("report_ai_analyses table MISSING!")

cursor.execute("PRAGMA table_info(complaints)")
columns = [row["name"] for row in cursor.fetchall()]
print("\nComplaints columns:")
for col in columns:
    if col in ["user_selected_category", "category_source", "ai_confidence", "ai_analysis_id", "ai_needs_review"]:
        print(f" - {col} (AI COLUMN)")
    
db.close()
print("\nLocal tests completed.")
