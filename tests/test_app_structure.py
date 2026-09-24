"""Package imports, static routes and paths; never connect to the real database."""

import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.settings import PROJECT_ROOT, FRONTEND_DIR, project_path
from database.base import Base


class AppStructureTests(unittest.TestCase):
    def test_import_does_not_initialize_database(self):
        with patch.object(Base.metadata, 'create_all') as create:
            module = importlib.import_module('app.main')
            importlib.reload(module)
        create.assert_not_called()

    def test_real_entrypoint_serves_frontend_and_static_assets_from_other_cwd(self):
        from app.main import app
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                with patch.object(Base.metadata, 'create_all') as create:
                    with TestClient(app) as client:
                        response = client.get('/')
                        self.assertEqual(response.status_code, 200)
                        self.assertIn('/static/registry-utils.js', response.text)
                        self.assertIn('/static/library.js', response.text)
                        for path in ('/static/registry-utils.js', '/static/library.js'):
                            self.assertEqual(client.get(path).status_code, 200)
                        self.assertEqual(client.get('/api/documents').status_code, 401)
                        self.assertEqual(client.get('/api/folders').status_code, 401)
                    create.assert_called_once()
            finally:
                os.chdir(previous)

    def test_storage_and_frontend_paths_remain_under_project(self):
        self.assertEqual(FRONTEND_DIR, PROJECT_ROOT / 'frontend')
        self.assertEqual(project_path('uploads/old.pdf'), PROJECT_ROOT / 'uploads/old.pdf')
        self.assertEqual(project_path('user_data/folders'), PROJECT_ROOT / 'user_data/folders')
        self.assertEqual(project_path('/tmp/example.pdf'), Path('/tmp/example.pdf'))
        self.assertTrue((PROJECT_ROOT / 'app/main.py').is_file())
        self.assertTrue((PROJECT_ROOT / 'database/models.py').is_file())


if __name__ == '__main__':
    unittest.main()
