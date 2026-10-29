import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.main import app

class TestPDFUploadAPI(unittest.TestCase):
    def setUp(self):
        from backend.app.db import database as db
        db.delete_all_uploaded_candidates()
        self.client = TestClient(app)
        self.samples_dir = project_root / "data" / "cvs" / "samples"

    def test_api_candidates_list(self):
        response = self.client.get("/api/candidates")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_pdf_upload_endpoint(self):
        pdf_path = self.samples_dir / "sample_alex_backend_lead.pdf"
        self.assertTrue(pdf_path.exists(), "Sample PDF file should exist")

        with open(pdf_path, "rb") as f:
            response = self.client.post(
                "/api/upload-cv?duplicate_action=replace",
                files={"file": ("sample_alex_backend_lead.pdf", f, "application/pdf")}
            )

        self.assertEqual(response.status_code, 200, f"Error: {response.text}")
        data = response.json()
        self.assertIn("candidate_id", data)

    def test_unsupported_file_type(self):
        response = self.client.post(
            "/api/upload-cv",
            files={"file": ("unsupported_document.xyz", b"fake binary data", "application/octet-stream")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file format", response.json()["detail"])

if __name__ == "__main__":
    unittest.main()
