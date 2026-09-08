import pytest
from fastapi.testclient import TestClient
import os
import sys

# Ensure we can import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from backend.app.main import app
from backend.app.services.database import get_db, initialize_database

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    # Initialize the database before running tests
    initialize_database()
    yield
    # Cleanup logic can go here if needed, but since it's SQLite, 
    # we can just use the existing state or a test DB.
    # For now, we'll use the main one or just let it be.

def test_ai_health():
    response = client.get("/ai/health")
    assert response.status_code == 200
    assert "ai_available" in response.json()

def test_auth_signup_and_login():
    # Attempt signup
    signup_data = {
        "name": "Test Citizen",
        "email": "citizen@test.com",
        "password": "password123"
    }
    # It might already exist from previous runs, so we just try to login if it does
    res = client.post("/auth/signup", json=signup_data)
    assert res.status_code in (200, 400)

    # Login
    login_data = {
        "email": "citizen@test.com",
        "password": "password123"
    }
    res = client.post("/auth/login", json=login_data)
    assert res.status_code == 200
    assert "email" in res.json()
    assert res.cookies.get("access_token") is not None

import uuid
def test_submit_complaint():
    login_data = {
        "email": "citizen@test.com",
        "password": "password123"
    }
    client.post("/auth/login", json=login_data)

    unique_id = uuid.uuid4().hex
    complaint_data = {
        "description": f"Unique pothole {unique_id} completely random text here.",
        "category": "Roads & Potholes",
        "state": "Karnataka",
        "location": f"Unique Area {unique_id}",
        "language": "en"
    }
    res = client.post("/complaints/", json=complaint_data)
    assert res.status_code in (200, 409)
    if res.status_code == 200:
        data = res.json()
        assert "complaint_id" in data
    
def test_check_duplicate():
    login_data = {
        "email": "citizen@test.com",
        "password": "password123"
    }
    client.post("/auth/login", json=login_data)

    res = client.get("/complaints/check-duplicate", params={
        "category": "Roads & Potholes",
        "location": "MG Road, Bangalore",
        "description": "There is a massive pothole on MG Road."
    })
    
    assert res.status_code == 200
    data = res.json()
    assert "is_duplicate" in data
    assert data["is_duplicate"] == True # Because we just submitted one
    assert len(data["matches"]) > 0

def test_get_complaints():
    res = client.get("/complaints/")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) > 0

def test_api_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json().get("status") == "ok"

def test_bearer_token_auth():
    login_data = {
        "email": "citizen@test.com",
        "password": "password123"
    }
    res = client.post("/auth/login", json=login_data)
    assert res.status_code == 200
    token = res.json().get("token")
    assert token is not None

    # Test /auth/me with Authorization: Bearer header
    client_no_cookie = TestClient(app, cookies={})
    me_res = client_no_cookie.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "citizen@test.com"

def test_check_duplicate_with_geo():
    res = client.get("/complaints/check-duplicate", params={
        "category": "Roads & Potholes",
        "location": "MG Road, Bangalore",
        "description": "Pothole near metro station",
        "latitude": 12.9716,
        "longitude": 77.5946
    })
    assert res.status_code == 200
    assert "is_duplicate" in res.json()
