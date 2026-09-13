"""Run the default regression suite on disposable local data, never production."""
import os
import tempfile

_test_directory = tempfile.TemporaryDirectory(prefix="civicpulse-tests-")
os.environ.update({
    "DATABASE_URL": "",
    "SQLITE_DB_PATH": os.path.join(_test_directory.name, "test.db"),
    "UPLOAD_DIR": os.path.join(_test_directory.name, "uploads"),
    "SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": "",
    "PRODUCTION": "false", "RENDER": "",
    "GEMINI_API_KEY": "", "OPENAI_API_KEY": "",
    "SECRET_KEY": "dev-only-secret-change-me-before-deployment",
    "COOKIE_SECURE": "false", "COOKIE_SAMESITE": "lax",
    "DUPLICATE_USE_VECTOR": "false", "DUPLICATE_SHADOW_MODE": "false",
})


def pytest_sessionfinish(session, exitstatus):
    _test_directory.cleanup()
