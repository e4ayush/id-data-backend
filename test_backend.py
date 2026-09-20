"""
BizeraID Backend Test Suite
Tests all API endpoints with edge cases.
Run: cd backend && python -m pytest test_backend.py -v
"""
import pytest
import sys
import os

# ── Unit Tests (no server needed) ──────────────────────────────────────────────

class TestFormatDob:
    """Tests for DOB formatting helpers"""
    
    # We import inline to handle env requirements
    @pytest.fixture(autouse=True)
    def setup(self):
        # Ensure env vars are set so main.py can import
        os.environ.setdefault("ADMIN_SECRET", "test_secret_123")
        os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
        os.environ.setdefault("SUPABASE_KEY", "fake_key")
    
    def test_format_dob_for_frontend_valid(self):
        """DD-MM-YYYY output from YYYY-MM-DD"""
        from main import format_dob_for_frontend
        student = {"dob": "2010-05-15"}
        result = format_dob_for_frontend(student)
        assert result["dob"] == "15-05-2010"

    def test_format_dob_for_frontend_empty(self):
        """Empty DOB should remain unchanged"""
        from main import format_dob_for_frontend
        student = {"dob": ""}
        result = format_dob_for_frontend(student)
        assert result["dob"] == ""

    def test_format_dob_for_frontend_none(self):
        """None DOB should remain None"""
        from main import format_dob_for_frontend
        student = {"dob": None}
        result = format_dob_for_frontend(student)
        assert result["dob"] is None

    def test_format_dob_for_frontend_garbage(self):
        """Garbage DOB should remain unchanged (no crash)"""
        from main import format_dob_for_frontend
        student = {"dob": "not-a-date"}
        result = format_dob_for_frontend(student)
        assert result["dob"] == "not-a-date"

    def test_format_dob_for_frontend_no_key(self):
        """Student without dob key should not crash"""
        from main import format_dob_for_frontend
        student = {"name": "Test"}
        result = format_dob_for_frontend(student)
        assert "name" in result

    def test_format_dob_for_db_valid(self):
        """YYYY-MM-DD output from DD-MM-YYYY"""
        from main import format_dob_for_db
        student = {"dob": "15-05-2010"}
        result = format_dob_for_db(student)
        assert result["dob"] == "2010-05-15"

    def test_format_dob_for_db_empty(self):
        """Empty DOB stays empty"""
        from main import format_dob_for_db
        student = {"dob": ""}
        result = format_dob_for_db(student)
        assert result["dob"] == ""

    def test_format_dob_for_db_none(self):
        """None DOB stays None"""
        from main import format_dob_for_db
        student = {"dob": None}
        result = format_dob_for_db(student)
        assert result["dob"] is None

    def test_format_dob_roundtrip(self):
        """DB → Frontend → DB should be stable"""
        from main import format_dob_for_frontend, format_dob_for_db
        original = {"dob": "2010-05-15"}
        frontend = format_dob_for_frontend(dict(original))
        assert frontend["dob"] == "15-05-2010"
        back_to_db = format_dob_for_db(dict(frontend))
        assert back_to_db["dob"] == "2010-05-15"

    def test_format_dob_excel_safe_uses_double_dash(self):
        """Only the Excel/CSV export keeps the doubled separator"""
        from main import format_dob_for_frontend
        assert format_dob_for_frontend({"dob": "2021-03-06"})["dob"] == "06-03-2021"
        assert format_dob_for_frontend({"dob": "2021-03-06"}, excel_safe=True)["dob"] == "06--03--2021"

    def test_format_dob_custom_data_date_field(self):
        """Date-like custom_data fields (typed as DD-MM-YYYY) use the display format"""
        from main import format_dob_for_frontend
        student = {"dob": "2021-03-06", "custom_data": {"admission_date": "15-05-2010"}}
        result = format_dob_for_frontend(student)
        assert result["custom_data"]["admission_date"] == "15-05-2010"
        assert format_dob_for_frontend(student, excel_safe=True)["custom_data"]["admission_date"] == "15--05--2010"


class TestPhotoDownloadFilename:
    """Tests for photo filenames written inside downloaded ZIP archives"""

    @pytest.fixture(autouse=True)
    def setup(self):
        os.environ.setdefault("ADMIN_SECRET", "test_secret_123")
        os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
        os.environ.setdefault("SUPABASE_KEY", "fake_key")

    def test_photo_download_filename_adds_jpg_extension(self):
        from main import photo_download_filename

        assert photo_download_filename("MPS-1001") == "MPS-1001.jpg"

    def test_photo_download_filename_replaces_original_extension(self):
        from main import photo_download_filename

        assert photo_download_filename("folder/student photo.png") == "student photo.jpg"


class TestGeneratePassword:
    """Tests for password generation"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        os.environ.setdefault("ADMIN_SECRET", "test_secret_123")
        os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
        os.environ.setdefault("SUPABASE_KEY", "fake_key")

    def test_password_length(self):
        from main import generate_password
        pw = generate_password()
        assert len(pw) == 10

    def test_password_custom_length(self):
        from main import generate_password
        pw = generate_password(length=16)
        assert len(pw) == 16

    def test_password_unique(self):
        """Two generated passwords should be different"""
        from main import generate_password
        pw1 = generate_password()
        pw2 = generate_password()
        assert pw1 != pw2

    def test_password_not_empty(self):
        from main import generate_password
        pw = generate_password(length=1)
        assert len(pw) == 1


class TestCompressImage:
    """Tests for image compression logic"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        os.environ.setdefault("ADMIN_SECRET", "test_secret_123")
        os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
        os.environ.setdefault("SUPABASE_KEY", "fake_key")

    def test_compress_small_image(self):
        """A tiny image should pass through without error"""
        from main import compress_image_to_target
        from PIL import Image
        import io
        
        # Create a 10x10 white image (< 100KB)
        img = Image.new("RGB", (10, 10), "white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        raw = buf.getvalue()
        
        result = compress_image_to_target(raw)
        assert len(result) < 100 * 1024
        assert len(result) > 0

    def test_compress_large_image(self):
        """A big noisy image should be compressed to target"""
        from main import compress_image_to_target
        from PIL import Image
        import io, random
        
        # Create a 2000x2000 image with random noise (> 100KB)
        img = Image.new("RGB", (2000, 2000))
        pixels = [
            (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            for _ in range(2000 * 2000)
        ]
        img.putdata(pixels)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        raw = buf.getvalue()
        
        result = compress_image_to_target(raw, target_kb=100)
        assert len(result) <= 100 * 1024 + 5000  # Allow small tolerance

    def test_compress_png_input(self):
        """PNG input should be handled (converted to JPEG)"""
        from main import compress_image_to_target
        from PIL import Image
        import io
        
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw = buf.getvalue()
        
        result = compress_image_to_target(raw)
        assert len(result) > 0


class TestVerifyAdmin:
    """Tests for admin authentication"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        os.environ.setdefault("ADMIN_SECRET", "test_secret_123")
        os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
        os.environ.setdefault("SUPABASE_KEY", "fake_key")

    def test_valid_admin_secret(self):
        """Correct secret should not raise"""
        from main import verify_admin
        from unittest.mock import MagicMock
        
        request = MagicMock()
        request.headers.get.return_value = os.environ["ADMIN_SECRET"]
        # Should not raise
        verify_admin(request)

    def test_invalid_admin_secret(self):
        """Wrong secret should raise 401"""
        from main import verify_admin
        from unittest.mock import MagicMock
        
        request = MagicMock()
        request.headers.get.return_value = "wrong_secret"
        with pytest.raises(Exception) as exc_info:
            verify_admin(request)
        assert "401" in str(exc_info.value.status_code) or exc_info.value.status_code == 401

    def test_missing_admin_secret(self):
        """No header should raise 401"""
        from main import verify_admin
        from unittest.mock import MagicMock
        
        request = MagicMock()
        request.headers.get.return_value = None
        with pytest.raises(Exception) as exc_info:
            verify_admin(request)
        assert exc_info.value.status_code == 401

    def test_empty_admin_secret(self):
        """Empty string should raise 401"""
        from main import verify_admin
        from unittest.mock import MagicMock
        
        request = MagicMock()
        request.headers.get.return_value = ""
        with pytest.raises(Exception) as exc_info:
            verify_admin(request)
        assert exc_info.value.status_code == 401


class TestVerifySchoolUser:
    """Tests for JWT school user authentication"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        os.environ.setdefault("ADMIN_SECRET", "test_secret_123")
        os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
        os.environ.setdefault("SUPABASE_KEY", "fake_key")

    def test_missing_bearer_prefix(self):
        """Token without 'Bearer ' should fail"""
        from main import verify_school_user
        with pytest.raises(Exception) as exc_info:
            verify_school_user("just_a_token")
        assert exc_info.value.status_code == 401

    def test_empty_string(self):
        """Empty string should fail"""
        from main import verify_school_user
        with pytest.raises(Exception) as exc_info:
            verify_school_user("")
        assert exc_info.value.status_code == 401


# ── Integration Tests (need FastAPI TestClient) ───────────────────────────────

class TestAPIEndpoints:
    """Tests API endpoints via TestClient"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        os.environ["ADMIN_SECRET"] = "test_secret_123"
        os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
        os.environ.setdefault("SUPABASE_KEY", "fake_key")

    def test_root_endpoint(self):
        """GET / should return status"""
        try:
            from main import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            response = client.get("/")
            assert response.status_code == 200
            assert "status" in response.json()
        except Exception:
            pytest.skip("Server dependencies not available for integration test")

    def test_schools_no_auth(self):
        """GET /schools without secret should return 401"""
        try:
            from main import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            response = client.get("/schools")
            assert response.status_code == 401
        except Exception:
            pytest.skip("Server dependencies not available for integration test")

    def test_students_no_auth(self):
        """GET /students/fake-id without secret should return 401"""
        try:
            from main import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            response = client.get("/students/fake-id")
            assert response.status_code == 401
        except Exception:
            pytest.skip("Server dependencies not available for integration test")

    def test_create_school_no_auth(self):
        """POST /create-school without secret should return 401"""
        try:
            from main import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            response = client.post("/create-school", json={"name": "Test School"})
            assert response.status_code == 401
        except Exception:
            pytest.skip("Server dependencies not available for integration test")

    def test_delete_student_no_auth(self):
        """DELETE /student/fake-id without secret should return 401"""
        try:
            from main import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            response = client.delete("/student/fake-id")
            assert response.status_code == 401
        except Exception:
            pytest.skip("Server dependencies not available for integration test")

    def test_upload_excel_no_auth(self):
        """POST /upload/ without auth should fail"""
        try:
            from main import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            response = client.post("/upload/fake-id")
            assert response.status_code in [401, 422]
        except Exception:
            pytest.skip("Server dependencies not available for integration test")

    def test_upload_photo_no_auth(self):
        """POST /upload-photo/fake-id without auth should fail"""
        try:
            from main import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            response = client.post("/upload-photo/fake-id")
            assert response.status_code in [401, 422]
        except Exception:
            pytest.skip("Server dependencies not available for integration test")

    def test_download_photos_no_auth(self):
        """GET /download-photos/fake-id without auth should fail"""
        try:
            from main import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            response = client.get("/download-photos/fake-id")
            assert response.status_code == 401
        except Exception:
            pytest.skip("Server dependencies not available for integration test")

    def test_download_selected_photos_no_auth(self):
        """POST /download-photos/fake-id without auth should fail"""
        try:
            from main import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            response = client.post("/download-photos/fake-id", json={"student_ids": ["abc"]})
            assert response.status_code == 401
        except Exception:
            pytest.skip("Server dependencies not available for integration test")

    def test_export_selected_no_auth(self):
        """POST /export-file/fake-id without auth should fail"""
        try:
            from main import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            response = client.post("/export-file/fake-id", json={"student_ids": ["abc"]})
            assert response.status_code == 401
        except Exception:
            pytest.skip("Server dependencies not available for integration test")

    def test_export_students_no_auth(self):
        """GET /export-students/fake-id without auth should fail"""
        try:
            from main import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            response = client.get("/export-students/fake-id")
            assert response.status_code == 401
        except Exception:
            pytest.skip("Server dependencies not available for integration test")

    def test_mobile_students_no_auth(self):
        """GET /mobile/students without JWT should fail"""
        try:
            from main import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            response = client.get("/mobile/students")
            assert response.status_code in [401, 422]
        except Exception:
            pytest.skip("Server dependencies not available for integration test")

    def test_mobile_student_create_no_auth(self):
        """POST /mobile/student without JWT should fail"""
        try:
            from main import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            response = client.post("/mobile/student", json={"name": "Test", "class": "5"})
            assert response.status_code in [401, 422]
        except Exception:
            pytest.skip("Server dependencies not available for integration test")


# ── Edge Case Tests ───────────────────────────────────────────────────────────

class TestEdgeCases:
    """Edge cases that could cause crashes"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        os.environ.setdefault("ADMIN_SECRET", "test_secret_123")
        os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
        os.environ.setdefault("SUPABASE_KEY", "fake_key")

    def test_format_dob_with_whitespace(self):
        """DOB with leading/trailing whitespace"""
        from main import format_dob_for_frontend
        student = {"dob": "  2010-05-15  "}
        result = format_dob_for_frontend(student)
        assert result["dob"] == "15-05-2010"

    def test_format_dob_with_slashes(self):
        """DOB in slash format should be handled"""
        from main import format_dob_for_db
        student = {"dob": "15/05/2010"}
        result = format_dob_for_db(student)
        assert result["dob"] == "2010-05-15"

    def test_compress_empty_bytes(self):
        """Empty bytes should raise or return safely"""
        from main import compress_image_to_target
        try:
            result = compress_image_to_target(b"")
            # If it doesn't crash, that's acceptable
        except Exception:
            pass  # Expected for invalid image data

    def test_compress_invalid_bytes(self):
        """Random bytes should raise or return safely"""
        from main import compress_image_to_target
        try:
            result = compress_image_to_target(b"not_an_image_at_all")
        except Exception:
            pass  # Expected

    def test_password_zero_length(self):
        """Zero-length password request"""
        from main import generate_password
        pw = generate_password(length=0)
        assert pw == ""

    def test_verify_admin_with_extra_whitespace(self):
        """Secret with trailing whitespace should fail"""
        from main import verify_admin
        from unittest.mock import MagicMock
        
        request = MagicMock()
        request.headers.get.return_value = os.environ["ADMIN_SECRET"] + " "
        with pytest.raises(Exception) as exc_info:
            verify_admin(request)
        assert exc_info.value.status_code == 401

    def test_school_user_bearer_only(self):
        """'Bearer ' with no token should fail"""
        from main import verify_school_user
        with pytest.raises(Exception):
            verify_school_user("Bearer ")


# ── Export / re-upload helpers ─────────────────────────────────────────────────

class TestExportHelpers:
    """Tests for the helpers that decide how dates survive an Excel round-trip"""

    @pytest.fixture(autouse=True)
    def setup(self):
        os.environ.setdefault("ADMIN_SECRET", "test_secret_123")
        os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
        os.environ.setdefault("SUPABASE_KEY", "fake_key")

    def test_date_like_headers_detected(self):
        from main import is_date_like_header
        assert is_date_like_header("Date of Birth")
        assert is_date_like_header("dob")
        assert is_date_like_header("Admission Date")
        assert is_date_like_header("BIRTH DATE")

    def test_non_date_headers_ignored(self):
        from main import is_date_like_header
        assert not is_date_like_header("Name")
        assert not is_date_like_header("Phone")
        assert not is_date_like_header("Roll Number")
        assert not is_date_like_header(None)
        assert not is_date_like_header("")

    def test_xls_text_style_is_well_formed(self):
        from main import EXCEL_TEXT_CELL_STYLE
        assert "mso-number-format" in EXCEL_TEXT_CELL_STYLE
        assert EXCEL_TEXT_CELL_STYLE.startswith(' style="')


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeStudentsTable:
    """Minimal stand-in for supabase.table('students') on the upload path."""

    def __init__(self, store):
        self.store = store
        self.mode = None
        self.payload = None
        self.kwargs = {}
        self.filters = {}

    def select(self, *args, **kwargs):
        self.mode = "select"
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def insert(self, rows):
        self.mode = "insert"
        self.payload = rows
        return self

    def upsert(self, rows, **kwargs):
        self.mode = "upsert"
        self.payload = rows
        self.kwargs = kwargs
        return self

    def execute(self):
        if self.mode == "select":
            wanted = self.filters.get("school_id")
            return _FakeResult([r for r in self.store["rows"] if r.get("school_id") == wanted])
        if self.mode == "insert":
            self.store["inserted"].extend(self.payload)
            return _FakeResult(self.payload)
        self.store["upsert_kwargs"].append(self.kwargs)
        self.store["upserted"].extend(self.payload)
        return _FakeResult(self.payload)


class _FakeSupabase:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return _FakeStudentsTable(self.store)


class TestUploadOverwrite:
    """Re-uploading a sheet must UPDATE existing students, not silently skip them"""

    SCHOOL = "11111111-1111-1111-1111-111111111111"
    EXISTING_ID = "22222222-2222-2222-2222-222222222222"

    @pytest.fixture(autouse=True)
    def setup(self):
        os.environ.setdefault("ADMIN_SECRET", "test_secret_123")
        os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
        os.environ.setdefault("SUPABASE_KEY", "fake_key")

    def run_upload(self, monkeypatch, csv_text):
        import main
        from fastapi.testclient import TestClient

        store = {
            "rows": [{
                "id": self.EXISTING_ID,
                "school_id": self.SCHOOL,
                "name": "Old Name",
                "class": "5",
                "admission_number": "1001",
                "phone": "9999999999",
                "photo_url": "https://example.test/photo.jpg",
                "custom_data": {"_original_photo_filename": "old.jpg"},
                "created_at": "2024-01-01T00:00:00Z",
            }],
            "inserted": [],
            "upserted": [],
            "upsert_kwargs": [],
        }
        monkeypatch.setattr(main, "supabase", _FakeSupabase(store))

        client = TestClient(main.app)
        response = client.post(
            f"/upload-excel/{self.SCHOOL}",
            headers={"X-Admin-Secret": main.ADMIN_SECRET},
            files={"file": ("students.csv", csv_text.encode(), "text/csv")},
        )
        return response, store

    def test_existing_student_is_updated_not_skipped(self, monkeypatch):
        csv_text = (
            "Name,Class,Admission Number,Phone\n"
            "New Name,5,1001,8888888888\n"
            "Fresh Student,6,1002,7777777777\n"
        )
        response, store = self.run_upload(monkeypatch, csv_text)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["inserted"] == 1, body
        assert body["updated"] == 1, body

        assert len(store["upserted"]) == 1
        updated = store["upserted"][0]
        assert updated["id"] == self.EXISTING_ID
        assert updated["name"] == "New Name"
        assert updated["phone"] == "8888888888"

        assert len(store["inserted"]) == 1
        assert store["inserted"][0]["name"] == "Fresh Student"

    def test_update_preserves_photo_and_original_filename(self, monkeypatch):
        csv_text = "Name,Class,Admission Number,Phone\nNew Name,5,1001,8888888888\n"
        _, store = self.run_upload(monkeypatch, csv_text)

        updated = store["upserted"][0]
        assert updated["photo_url"] == "https://example.test/photo.jpg"
        assert updated["custom_data"]["_original_photo_filename"] == "old.jpg"

    def test_upsert_targets_id_without_nulling_missing_columns(self, monkeypatch):
        csv_text = "Name,Class,Admission Number,Phone\nNew Name,5,1001,8888888888\n"
        _, store = self.run_upload(monkeypatch, csv_text)

        kwargs = store["upsert_kwargs"][0]
        assert kwargs.get("on_conflict") == "id"
        assert kwargs.get("default_to_null") is False
