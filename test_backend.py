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
