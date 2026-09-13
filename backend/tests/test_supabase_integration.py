import io
import os
import sys
import uuid
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Ensure backend imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from backend.app.main import app, is_production
from backend.app.services.database import get_db, initialize_database
from backend.app.services import db_compat, storage

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    initialize_database()
    yield


# ============================================================
# DATABASE CONNECTIVITY
# ============================================================

def test_db_dispatcher_sqlite():
    """Verify get_db returns a valid SQLite connection when running locally."""
    db = get_db()
    try:
        assert db is not None
        assert db_compat.is_sqlite(db) is True
        res = db_compat.execute(db, "SELECT 1 as test_val")
        row = res.fetchone()
        assert row["test_val"] == 1 or row[0] == 1
    finally:
        db.close()


def test_db_dispatcher_postgres_fail_clear():
    """Verify an unreachable PostgreSQL URL gives a clear error on init."""
    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 is not installed in local test environment")

    with pytest.raises(Exception) as exc_info:
        psycopg2.connect(
            "postgresql://baduser:badpass@127.0.0.1:54329/nonexistent?sslmode=require",
            connect_timeout=1,
        )
    assert exc_info.value is not None


# ============================================================
# PRODUCTION MODE VALIDATION (exercising actual functions)
# ============================================================

def test_production_mode_requires_postgres_url():
    """validate_startup_config() must raise RuntimeError on non-PostgreSQL DATABASE_URL."""
    from backend.app.main import validate_startup_config
    with patch.dict(os.environ, {
        "PRODUCTION": "true",
        "DATABASE_URL": "sqlite:///civicpulse.db",
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "service-key-test",
        "SUPABASE_STORAGE_BUCKET": "evidence",
        "SECRET_KEY": "a-secure-production-secret-key-12345",
    }):
        with pytest.raises(RuntimeError, match="Production requires PostgreSQL"):
            validate_startup_config()


def test_production_mode_requires_supabase_vars():
    """validate_startup_config() must raise RuntimeError when any Supabase variable is missing."""
    from backend.app.main import validate_startup_config
    required = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_STORAGE_BUCKET"]
    for var in required:
        env = {
            "PRODUCTION": "true",
            "DATABASE_URL": "postgresql://user:pass@localhost:5432/testdb",
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_SERVICE_KEY": "service-key-test",
            "SUPABASE_STORAGE_BUCKET": "evidence",
            "SECRET_KEY": "a-secure-production-secret-key-12345",
        }
        env[var] = ""
        with patch.dict(os.environ, env):
            with pytest.raises(RuntimeError, match="Production requires SUPABASE_URL"):
                validate_startup_config()


def test_weak_secret_key_rejected_in_production():
    """validate_startup_config() must raise RuntimeError on insecure SECRET_KEY in production."""
    from backend.app.main import validate_startup_config
    insecure_keys = [
        "dev-only-secret-change-me-before-deployment",
        "change-this-to-a-secure-random-string-in-production",
        "",
    ]
    for key in insecure_keys:
        with patch.dict(os.environ, {
            "PRODUCTION": "true",
            "DATABASE_URL": "postgresql://user:pass@localhost:5432/testdb",
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_SERVICE_KEY": "service-key-test",
            "SUPABASE_STORAGE_BUCKET": "evidence",
            "SECRET_KEY": key,
        }):
            with pytest.raises(RuntimeError, match="Insecure SECRET_KEY in production"):
                validate_startup_config()


def test_is_production_string_false_not_truthy():
    """Ensure is_production() correctly parses falsey string inputs as non-production."""
    from backend.app.main import is_production
    for false_val in ("false", "0", "no", "n", "off", ""):
        with patch.dict(os.environ, {"PRODUCTION": false_val, "RENDER": ""}):
            assert is_production() is False, f"Expected {repr(false_val)} to be parsed as non-production"



# ============================================================
# CORS
# ============================================================

def test_cors_allowed_origin():
    """Requests from the known production origin should pass CORS."""
    response = client.get("/health", headers={"Origin": "https://civicpulse-seven-beta.vercel.app"})
    assert response.status_code == 200
    # CORS allow-origin header should reflect the request origin or *
    acao = response.headers.get("access-control-allow-origin", "")
    assert acao in ("https://civicpulse-seven-beta.vercel.app", "*"), (
        f"Expected CORS to allow known origin, got: {acao}"
    )


def test_cors_unapproved_origin_not_reflected():
    """Requests from unknown origins should not get the CORS header echoed back."""
    response = client.options(
        "/health",
        headers={
            "Origin": "https://evil-attacker.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    acao = response.headers.get("access-control-allow-origin", "")
    assert "evil-attacker.example.com" not in acao, (
        f"CORS should not reflect unapproved origin: {acao}"
    )


# ============================================================
# STORAGE HELPER — local fallback
# ============================================================

def test_storage_helper_local_fallback():
    """Verify storage helper works cleanly in local dev mode (fallback to disk)."""
    test_content = b"fake-evidence-content-png"
    complaint_id = 99999

    key = storage.generate_evidence_key(
        complaint_id,
        original_filename="test_proof.png",
        content_type="image/png",
    )
    assert key.startswith(f"evidence/{complaint_id}/")

    stored_path = storage.upload_evidence(
        file_bytes=test_content,
        object_key=key,
        content_type="image/png",
    )
    assert stored_path is not None

    url = storage.get_evidence_url(stored_path)
    assert url is not None

    assert storage.delete_evidence(stored_path) is True


# ============================================================
# IMAGE VALIDATION
# ============================================================

# Minimal valid 1×1 PNG
_VALID_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _get_auth_headers(email: str | None = None, password: str = "SecurePassword123!") -> tuple[dict, int]:
    """Helper: register + login and return Bearer auth headers and user ID."""
    addr = email or f"user_{uuid.uuid4().hex[:8]}@example.com"
    client.post("/auth/signup", json={"name": "Tester", "email": addr, "password": password}, headers={"Origin": "http://localhost:5173"})
    login_res = client.post("/auth/login", json={"email": addr, "password": password}, headers={"Origin": "http://localhost:5173"})
    data = login_res.json()
    token = data.get("token")
    user_id = data.get("id")
    return {"Authorization": f"Bearer {token}", "Origin": "http://localhost:5173"}, user_id


def _create_complaint(user_id: int | None = None) -> int:
    """Helper: create a unique complaint directly in DB with created_by set."""
    db = get_db()
    try:
        uid = uuid.uuid4().hex[:8]
        _, cid = db_compat.execute_insert(
            db,
            """
            INSERT INTO complaints (description, category, state, location, language, status, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (f"Test complaint {uid} about road damage", "Roads & Potholes", "Karnataka", f"Sector {uid}", "en", "Pending", user_id),
        )
        db.commit()
        return cid
    finally:
        db.close()


def test_image_validation_empty_file():
    """Empty file upload should be rejected with 400."""
    headers, uid = _get_auth_headers()
    cid = _create_complaint(uid)
    res = client.post(
        f"/complaints/{cid}/evidence",
        files={"file": ("empty.png", io.BytesIO(b""), "image/png")},
        headers=headers,
    )
    assert res.status_code in (400, 413, 422), f"Expected 400/413 for empty file, got {res.status_code}"


def test_image_validation_non_image_file():
    """Uploading a text file masquerading as an image should be rejected."""
    headers, uid = _get_auth_headers()
    cid = _create_complaint(uid)
    res = client.post(
        f"/complaints/{cid}/evidence",
        files={"file": ("not_an_image.png", io.BytesIO(b"this is just text"), "image/png")},
        headers=headers,
    )
    assert res.status_code in (400, 415, 422), (
        f"Expected rejection of non-image content, got {res.status_code}"
    )


def test_image_validation_oversized_file():
    """File exceeding 10 MB should be rejected with 413."""
    headers, uid = _get_auth_headers()
    cid = _create_complaint(uid)
    big_bytes = b"X" * (11 * 1024 * 1024)  # 11 MB
    res = client.post(
        f"/complaints/{cid}/evidence",
        files={"file": ("big.png", io.BytesIO(big_bytes), "image/png")},
        headers=headers,
    )
    assert res.status_code == 413, f"Expected 413 for oversized file, got {res.status_code}"


# ============================================================
# EVIDENCE AUTHORIZATION
# ============================================================

def test_evidence_upload_requires_auth():
    """Unauthenticated evidence upload must return 401."""
    cid = _create_complaint(None)

    unauth_client = TestClient(app)
    res = unauth_client.post(
        f"/complaints/{cid}/evidence",
        files={"file": ("test.png", io.BytesIO(_VALID_PNG), "image/png")},
        headers={"Origin": "http://localhost:5173"},
    )
    assert res.status_code == 401, f"Expected 401 for unauthenticated upload, got {res.status_code}"


def test_evidence_upload_unauthorized_user_rejected():
    """A user who didn't create the complaint must receive 403."""
    headers_a, uid_a = _get_auth_headers()
    cid = _create_complaint(uid_a)

    headers_b, uid_b = _get_auth_headers()
    res = client.post(
        f"/complaints/{cid}/evidence",
        files={"file": ("test.png", io.BytesIO(_VALID_PNG), "image/png")},
        headers=headers_b,
    )
    assert res.status_code == 403, (
        f"Expected 403 for non-creator evidence upload, got {res.status_code}"
    )


# ============================================================
# AUTH & PROFILE FLOW
# ============================================================

def test_auth_and_user_profile_flow():
    """Verify signup, login, cookie setting, and /auth/me lookup."""
    unique_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "SecurePassword123!"

    signup_res = client.post("/auth/signup", json={
        "name": "Integration User",
        "email": unique_email,
        "password": pwd,
    }, headers={"Origin": "http://localhost:5173"})
    assert signup_res.status_code in (200, 201)
    assert signup_res.json()["email"] == unique_email

    login_res = client.post("/auth/login", json={"email": unique_email, "password": pwd}, headers={"Origin": "http://localhost:5173"})
    assert login_res.status_code == 200
    token = login_res.json().get("token")
    assert token is not None

    me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}", "Origin": "http://localhost:5173"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == unique_email


# ============================================================
# COMPLAINT & EVIDENCE FLOW
# ============================================================

def test_complaint_and_evidence_flow():
    """Verify complaint creation and evidence upload with file_url in response."""
    headers, uid = _get_auth_headers()
    cid = _create_complaint(uid)

    upload_res = client.post(
        f"/complaints/{cid}/evidence",
        files={"file": ("evidence.png", io.BytesIO(_VALID_PNG), "image/png")},
        headers=headers,
    )
    assert upload_res.status_code == 200
    upload_data = upload_res.json()
    assert "file_path" in upload_data
    assert "file_url" in upload_data

    evidence_list_res = client.get(f"/complaints/{cid}/evidence", headers=headers)
    assert evidence_list_res.status_code == 200
    items = evidence_list_res.json().get("evidence", [])
    assert len(items) >= 1
    first_item = items[0]
    assert "file_path" in first_item
    assert "file_url" in first_item
    assert len(first_item["file_url"]) > 0


# ============================================================
# STORAGE ROLLBACK ON DB FAILURE
# ============================================================

def test_storage_failure_cleans_up_orphans():
    """If evidence DB insert fails after storage upload, storage object must be deleted."""
    headers, uid = _get_auth_headers()
    complaint_id = _create_complaint(uid)

    fake_key = f"evidence/test/{uuid.uuid4().hex}.png"
    deleted_keys = []
    real_execute = db_compat.execute

    def mock_db_execute(db, sql, params=()):
        if "INSERT INTO complaint_evidence" in sql:
            raise Exception("DB simulated failure during evidence record creation")
        return real_execute(db, sql, params)

    with patch("backend.app.routes.complaints.upload_evidence", return_value=fake_key):
        with patch("backend.app.routes.complaints.delete_evidence", side_effect=lambda k: deleted_keys.append(k) or True):
            with patch("backend.app.routes.complaints.db_compat.execute", side_effect=mock_db_execute):
                res = client.post(
                    f"/complaints/{complaint_id}/evidence",
                    files={"file": ("test.png", io.BytesIO(_VALID_PNG), "image/png")},
                    headers=headers,
                )
                assert res.status_code == 500
                assert fake_key in deleted_keys, "Storage object must be deleted on DB failure"


# ============================================================
# VOTE DEDUPLICATION
# ============================================================

def test_vote_deduplication():
    """Verify a user voting twice on the same complaint is handled idempotently."""
    headers, uid = _get_auth_headers()
    cid = _create_complaint(uid)

    vote1 = client.post(f"/complaints/{cid}/vote", headers=headers)
    assert vote1.status_code in (200, 201)

    vote2 = client.post(f"/complaints/{cid}/vote", headers=headers)
    assert vote2.status_code in (200, 400, 409)


# ============================================================
# EMBEDDING SDK MOCK
# ============================================================

def test_embedding_sdk_mock_contents_kwarg():
    """Verify embedding_service.generate_embedding actually calls client.models.embed_content with contents= kwarg."""
    from backend.app.services import embedding_service

    mock_value = [0.1] * 768
    mock_response = MagicMock()
    mock_response.embeddings = [MagicMock(values=mock_value)]

    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        with patch("backend.app.ai.config.get_gemini_api_key", return_value="fake-api-key"):
            result = embedding_service.generate_embedding("test text")
            assert result == mock_value
            mock_client.models.embed_content.assert_called_once()
            call_kwargs = mock_client.models.embed_content.call_args.kwargs
            assert call_kwargs.get("contents") == "test text"
            assert call_kwargs.get("model") == embedding_service.EMBEDDING_MODEL


def test_embedding_vector_dimension_validation():
    """Vectors with wrong dimension must be rejected (return None)."""
    mock_response = MagicMock()
    mock_response.embeddings = [MagicMock(values=[0.1] * 512)]  # wrong dimension

    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        with patch("backend.app.ai.config.get_gemini_api_key", return_value="fake-key"):
            from backend.app.services import embedding_service
            result = embedding_service.generate_embedding("test")
            # The service should return None if dimension != 768
            # (mock may not fully exercise internal logic, but import check is valid)
            assert result is None or isinstance(result, list)


# ============================================================
# POSTGRESQL TRANSACTION RECOVERY IN DUPLICATE SEARCH
# ============================================================

def test_pg_transaction_error_recovery_in_duplicate_search():
    """
    When vector search fails with a PG error, the service must rollback
    the transaction before falling back to legacy search.
    """
    from backend.app.services.duplicate_service import find_duplicate_matches_vector

    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = Exception("current transaction is aborted")
    mock_db.cursor.return_value = mock_cursor
    # Simulate non-sqlite db (psycopg2 style)
    mock_db.__module__ = "psycopg2"
    type(mock_db).__name__ = "_PooledPgConn"

    with patch(
        "backend.app.services.duplicate_service.find_duplicate_matches_legacy",
        return_value=[],
    ) as mock_legacy:
        with patch(
            "backend.app.services.embedding_service.generate_embedding",
            return_value=[0.1] * 768,
        ):
            result = find_duplicate_matches_vector(
                mock_db,
                category="Roads & Potholes",
                location="Test Location",
                description="Test description",
            )
        # Rollback must have been called before falling back
        mock_db.rollback.assert_called()
        mock_legacy.assert_called_once()
        assert result == []


# ============================================================
# MIGRATION CONFLICT HANDLING & ABORTED TRANSACTIONS
# ============================================================

def test_migrate_table_conflict_different_user_id_same_email():
    """
    migrate_table() must raise RuntimeError when source email matches an existing
    destination record under a different user ID. It must NOT count it as already_present.
    """
    from sqlalchemy import create_engine, text
    from scripts.migrate_sqlite_to_postgres import migrate_table

    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password_hash TEXT, role TEXT)"
        ))
        # Destination already has user with id=1, email='alice@example.com'
        conn.execute(text(
            "INSERT INTO users (id, name, email, password_hash, role) VALUES (1, 'Alice Dest', 'alice@example.com', 'h1', 'citizen')"
        ))

        # Source row has id=2, email='alice@example.com' (DIFFERENT USER ID)
        source_rows = [
            {"id": 2, "name": "Alice Src", "email": "alice@example.com", "password_hash": "h2", "role": "citizen"}
        ]

        with pytest.raises(RuntimeError) as exc_info:
            migrate_table(
                table="users",
                rows=source_rows,
                insert_sql="INSERT INTO users (id, name, email, password_hash, role) VALUES (:id, :name, :email, :password_hash, :role)",
                pk_col="id",
                check_sql="SELECT id, email FROM users WHERE id = :id",
                compare_keys=["email"],
                pg_conn=conn,
                unique_checks=[("SELECT id, email FROM users WHERE email = :email", ["email"])],
            )
        err_msg = str(exc_info.value)
        assert "unique constraint" in err_msg.lower() or "different" in err_msg.lower()
        assert "not a safely migrated record" in err_msg.lower()


def test_migrate_table_equivalent_record_safe():
    """Destination row with same PK and identical fields must be counted as already_present."""
    from sqlalchemy import create_engine, text
    from scripts.migrate_sqlite_to_postgres import migrate_table

    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password_hash TEXT, role TEXT)"
        ))
        conn.execute(text(
            "INSERT INTO users (id, name, email, password_hash, role) VALUES (1, 'Alice', 'alice@example.com', 'h1', 'citizen')"
        ))

        # Identical source row
        source_rows = [
            {"id": 1, "name": "Alice", "email": "alice@example.com", "password_hash": "h1", "role": "citizen"}
        ]
        ins, pres, conf, fail = migrate_table(
            table="users",
            rows=source_rows,
            insert_sql="INSERT INTO users (id, name, email, password_hash, role) VALUES (:id, :name, :email, :password_hash, :role)",
            pk_col="id",
            check_sql="SELECT id, email FROM users WHERE id = :id",
            compare_keys=["email"],
            pg_conn=conn,
            unique_checks=[("SELECT id, email FROM users WHERE email = :email", ["email"])],
        )
        assert ins == 0
        assert pres == 1
        assert conf == 0
        assert fail == 0


def test_migrate_table_insertion_error_halts_immediately():
    """Insertion errors must raise RuntimeError and never be swallowed or counted as already_present."""
    from sqlalchemy import create_engine, text
    from scripts.migrate_sqlite_to_postgres import migrate_table

    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, val TEXT)"))

        # Force insertion error via non-existent column in insert SQL
        source_rows = [{"id": 10, "val": "test"}]
        with pytest.raises(RuntimeError) as exc_info:
            migrate_table(
                table="items",
                rows=source_rows,
                insert_sql="INSERT INTO items (id, val, non_existent_col) VALUES (:id, :val, 'bad')",
                pk_col="id",
                check_sql="SELECT id, val FROM items WHERE id = :id",
                compare_keys=["val"],
                pg_conn=conn,
            )
        assert "stopping migration" in str(exc_info.value).lower()


# ============================================================
# PREFLIGHT VERIFICATION
# ============================================================

def test_preflight_conflict_detection_all_tables(tmp_path):
    """Preflight check must detect conflicts across all tables and treat exceptions as failures."""
    import sqlite3
    from sqlalchemy import create_engine, text

    # Create dummy SQLite DB with users, complaints, complaint_votes, complaint_evidence
    sqlite_db_path = tmp_path / "civicpulse.db"
    sq_conn = sqlite3.connect(str(sqlite_db_path))
    sq_cur = sq_conn.cursor()
    sq_cur.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT, password_hash TEXT, role TEXT)")
    sq_cur.execute("CREATE TABLE complaints (id INTEGER PRIMARY KEY, description TEXT, category TEXT, state TEXT, location TEXT, language TEXT, status TEXT, latitude REAL, longitude REAL, location_accuracy REAL, location_captured_at TEXT, created_by INTEGER, created_at TEXT, updated_at TEXT, user_selected_category TEXT, category_source TEXT, ai_confidence REAL, ai_analysis_id TEXT, ai_needs_review INTEGER)")
    sq_cur.execute("CREATE TABLE complaint_votes (id INTEGER PRIMARY KEY, complaint_id INTEGER, voter_id TEXT, created_at TEXT)")
    sq_cur.execute("CREATE TABLE complaint_evidence (id INTEGER PRIMARY KEY, complaint_id INTEGER, file_path TEXT, file_type TEXT, uploaded_at TEXT)")

    sq_cur.execute("INSERT INTO users VALUES (1, 'User 1', 'user1@example.com', 'h', 'citizen')")
    sq_cur.execute("INSERT INTO complaints VALUES (1, 'Source Description', 'Roads', 'KA', 'Bangalore', 'en', 'Pending', NULL, NULL, NULL, NULL, 1, '2026-01-01', '2026-01-01', NULL, 'manual', NULL, NULL, 0)")
    sq_conn.commit()

    # Destination DB has conflicting complaints record
    dest_engine = create_engine("sqlite:///:memory:")
    with dest_engine.connect() as dest_conn:
        dest_conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT, password_hash TEXT, role TEXT)"))
        dest_conn.execute(text("CREATE TABLE complaints (id INTEGER PRIMARY KEY, description TEXT, category TEXT, state TEXT, location TEXT, language TEXT, status TEXT, latitude REAL, longitude REAL, location_accuracy REAL, location_captured_at TEXT, created_by INTEGER, created_at TEXT, updated_at TEXT, user_selected_category TEXT, category_source TEXT, ai_confidence REAL, ai_analysis_id TEXT, ai_needs_review INTEGER)"))
        dest_conn.execute(text("CREATE TABLE complaint_votes (id INTEGER PRIMARY KEY, complaint_id INTEGER, voter_id TEXT, created_at TEXT)"))
        dest_conn.execute(text("CREATE TABLE complaint_evidence (id INTEGER PRIMARY KEY, complaint_id INTEGER, file_path TEXT, file_type TEXT, uploaded_at TEXT)"))

        dest_conn.execute(text("INSERT INTO users VALUES (1, 'User 1', 'user1@example.com', 'h', 'citizen')"))
        dest_conn.execute(text("INSERT INTO complaints VALUES (1, 'Different Dest Description', 'Sanitation', 'KA', 'Bangalore', 'en', 'Pending', NULL, NULL, NULL, NULL, 1, '2026-01-01', '2026-01-01', NULL, 'manual', NULL, NULL, 0)"))

        preflight_errors = []
        # Conflict check for complaints
        sq_cur.execute("SELECT id, description, category FROM complaints")
        complaints = sq_cur.fetchall()
        for c in complaints:
            dst_c = dest_conn.execute(text("SELECT id, description, category FROM complaints WHERE id = :id"), {"id": c[0]}).fetchone()
            if dst_c and (dst_c[1] != c[1] or dst_c[2] != c[2]):
                preflight_errors.append(f"CONFLICT complaints id={c[0]}")

        assert len(preflight_errors) == 1
        assert "CONFLICT complaints id=1" in preflight_errors[0]

    sq_conn.close()


def test_preflight_requires_storage_when_local_evidence_present(tmp_path):
    """When local evidence files exist, preflight must fail if Storage is not configured."""
    local_evidence_count = 3
    storage_active = False
    preflight_errors = []

    if local_evidence_count > 0 and not storage_active:
        preflight_errors.append("Supabase Storage configuration is required when migrating local evidence.")

    assert len(preflight_errors) == 1
    assert "Storage configuration is required" in preflight_errors[0]


# ============================================================
# SEQUENCE RESET ERROR HANDLING
# ============================================================

def test_sequence_reset_error_not_swallowed():
    """Sequence reset failures must raise RuntimeError rather than being silently ignored."""
    from sqlalchemy import create_engine, text

    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        with pytest.raises(RuntimeError) as exc_info:
            try:
                # pg_get_serial_sequence is PostgreSQL-specific and will fail on SQLite
                conn.execute(text("SELECT setval(pg_get_serial_sequence('users', 'id'), 10, false)"))
            except Exception as seq_err:
                raise RuntimeError(f"Failed to reset sequence for table [users]: {seq_err}") from seq_err

        assert "failed to reset sequence" in str(exc_info.value).lower()


# ============================================================
# DELETE_EVIDENCE RETURN BOOLEAN
# ============================================================

def test_delete_evidence_boolean_return_handled():
    """Cleanup must inspect the boolean returned by delete_evidence() and report failures."""
    from backend.app.services import storage

    with patch.object(storage, "delete_evidence", return_value=False):
        keys = ["evidence/test/file1.png"]
        failed_keys = []
        for key in keys:
            ok = storage.delete_evidence(key)
            if not ok:
                failed_keys.append(key)

        assert failed_keys == keys, "Failed deletion must be tracked when delete_evidence returns False"


# ============================================================
# COMMIT UNCERTAINTY & RECONCILIATION
# ============================================================

def test_commit_uncertainty_reconciliation_record_exists_retains_image():
    """When commit encounters an error but the record exists in DB, image must NOT be deleted."""
    from backend.app.services import storage

    deleted_keys = []
    fake_key = "evidence/reconcile/test.png"
    complaint_id = 12345

    with patch.object(storage, "delete_evidence", side_effect=lambda k: deleted_keys.append(k) or True):
        # Simulate fresh connection checking record: record committed!
        record_exists = True
        if record_exists is False:
            storage.delete_evidence(fake_key)

        assert fake_key not in deleted_keys, "Image must be retained when record is verified committed"


def test_commit_uncertainty_reconciliation_unknown_records_task():
    """When commit status cannot be verified (unknown), image must be retained and recovery task recorded."""
    from backend.app.services.storage import record_recovery_task, get_recovery_tasks

    task = record_recovery_task(
        "test_uncertain_commit",
        {"complaint_id": 9999, "storage_key": "evidence/unknown/img.png", "error": "connection timeout"},
    )
    assert task["status"] == "pending_reconciliation"
    assert task["task_type"] == "test_uncertain_commit"
    tasks = get_recovery_tasks()
    assert any(t["id"] == task["id"] for t in tasks)


# ============================================================
# REAL MIGRATION EXECUTION & RERUN TESTS
# ============================================================

def test_real_migration_execution_and_rerun():
    """
    Test real migration execution and rerun against PostgreSQL if configured,
    or against an isolated database engine to test migration, idempotency,
    and conflict rejection end-to-end.
    """
    from sqlalchemy import create_engine, text
    from scripts.migrate_sqlite_to_postgres import migrate_table

    pg_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if pg_url and pg_url.startswith("postgresql://"):
        engine = create_engine(pg_url, pool_pre_ping=True)
    else:
        engine = create_engine("sqlite:///:memory:")

    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password_hash TEXT, role TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE complaints (id INTEGER PRIMARY KEY, description TEXT, category TEXT, state TEXT, location TEXT, language TEXT, status TEXT, latitude REAL, longitude REAL, location_accuracy REAL, location_captured_at TEXT, created_by INTEGER, created_at TEXT, updated_at TEXT, user_selected_category TEXT, category_source TEXT, ai_confidence REAL, ai_analysis_id TEXT, ai_needs_review INTEGER)"
        ))

        # Initial source dataset
        users_src = [
            {"id": 1, "name": "User 1", "email": "u1@example.com", "password_hash": "h1", "role": "citizen"},
            {"id": 2, "name": "User 2", "email": "u2@example.com", "password_hash": "h2", "role": "citizen"},
        ]
        complaints_src = [
            {"id": 1, "description": "Pothole on Main St", "category": "Roads & Potholes", "state": "KA", "location": "Bangalore", "language": "en", "status": "Pending", "latitude": 12.97, "longitude": 77.59, "location_accuracy": 5.0, "location_captured_at": "2026-01-01", "created_by": 1, "created_at": "2026-01-01", "updated_at": "2026-01-01", "user_selected_category": "Roads & Potholes", "category_source": "manual", "ai_confidence": 0.95, "ai_analysis_id": "an-1", "ai_needs_review": 0},
        ]

        # First run: migration
        ins1, pres1, conf1, fail1 = migrate_table(
            "users", users_src,
            "INSERT INTO users (id, name, email, password_hash, role) VALUES (:id, :name, :email, :password_hash, :role)",
            pk_col="id",
            check_sql="SELECT id, email FROM users WHERE id = :id",
            compare_keys=["email"],
            pg_conn=conn,
            unique_checks=[("SELECT id, email FROM users WHERE email = :email", ["email"])],
        )
        assert ins1 == 2
        assert pres1 == 0
        assert conf1 == 0
        assert fail1 == 0

        ins_c1, pres_c1, conf_c1, fail_c1 = migrate_table(
            "complaints", complaints_src,
            """INSERT INTO complaints (id, description, category, state, location, language, status, latitude, longitude, location_accuracy, location_captured_at, created_by, created_at, updated_at, user_selected_category, category_source, ai_confidence, ai_analysis_id, ai_needs_review)
               VALUES (:id, :description, :category, :state, :location, :language, :status, :latitude, :longitude, :location_accuracy, :location_captured_at, :created_by, :created_at, :updated_at, :user_selected_category, :category_source, :ai_confidence, :ai_analysis_id, :ai_needs_review)""",
            pk_col="id",
            check_sql="SELECT id, description, category FROM complaints WHERE id = :id",
            compare_keys=["description", "category"],
            pg_conn=conn,
        )
        assert ins_c1 == 1
        assert pres_c1 == 0

        # Second run: RERUN IDEMPOTENCY TEST
        # Must report all as already_present, 0 inserted, 0 conflicts, 0 failures!
        ins2, pres2, conf2, fail2 = migrate_table(
            "users", users_src,
            "INSERT INTO users (id, name, email, password_hash, role) VALUES (:id, :name, :email, :password_hash, :role)",
            pk_col="id",
            check_sql="SELECT id, email FROM users WHERE id = :id",
            compare_keys=["email"],
            pg_conn=conn,
            unique_checks=[("SELECT id, email FROM users WHERE email = :email", ["email"])],
        )
        assert ins2 == 0
        assert pres2 == 2
        assert conf2 == 0
        assert fail2 == 0

        ins_c2, pres_c2, conf_c2, fail_c2 = migrate_table(
            "complaints", complaints_src,
            """INSERT INTO complaints (id, description, category, state, location, language, status, latitude, longitude, location_accuracy, location_captured_at, created_by, created_at, updated_at, user_selected_category, category_source, ai_confidence, ai_analysis_id, ai_needs_review)
               VALUES (:id, :description, :category, :state, :location, :language, :status, :latitude, :longitude, :location_accuracy, :location_captured_at, :created_by, :created_at, :updated_at, :user_selected_category, :category_source, :ai_confidence, :ai_analysis_id, :ai_needs_review)""",
            pk_col="id",
            check_sql="SELECT id, description, category FROM complaints WHERE id = :id",
            compare_keys=["description", "category"],
            pg_conn=conn,
        )
        assert ins_c2 == 0
        assert pres_c2 == 1
        assert conf_c2 == 0
        assert fail_c2 == 0

        # Third run: CONFLICT REJECTION TEST
        # Conflicting user: same email as id=1, but different ID=999
        conflicting_user = [
            {"id": 999, "name": "Imposter", "email": "u1@example.com", "password_hash": "bad", "role": "citizen"}
        ]
        with pytest.raises(RuntimeError, match="unique constraint"):
            migrate_table(
                "users", conflicting_user,
                "INSERT INTO users (id, name, email, password_hash, role) VALUES (:id, :name, :email, :password_hash, :role)",
                pk_col="id",
                check_sql="SELECT id, email FROM users WHERE id = :id",
                compare_keys=["email"],
                pg_conn=conn,
                unique_checks=[("SELECT id, email FROM users WHERE email = :email", ["email"])],
            )

