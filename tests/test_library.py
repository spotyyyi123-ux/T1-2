import asyncio
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from database.base import Base
from database.connection import get_db
from database.folder_store import FolderStore
from database.models import Document, ExtractedData, Log, User
from app.routers import documents, folders
from app.routers.users import get_current_user
from app.core.json_codec import dumps, loads
from app.services.extraction_format import normalize_ai_attributes
from app.services.extraction_format import AIServiceError
from app.services import document_processing as pipeline
from decimal import Decimal


@compiles(JSONB, 'sqlite')
def sqlite_jsonb(element, compiler, **kwargs):
    # Only the disposable test database uses SQLite; production schema is unchanged.
    return 'JSON'


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.uploads = self.root / 'uploads'
        self.uploads.mkdir()
        self.store = FolderStore(self.root / 'folders')
        self.engine = create_engine(f'sqlite:///{self.root / "test.sqlite"}', connect_args={'check_same_thread': False},
                                    json_serializer=dumps, json_deserializer=loads)
        self.addCleanup(self.engine.dispose)
        event.listen(self.engine, 'connect', lambda conn, _: conn.execute('PRAGMA foreign_keys=ON'))
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add_all([User(id=1, email='one@example.com', hashed_password='test'), User(id=2, email='two@example.com', hashed_password='test')])
            db.commit()
        for target, attribute, value in (
            (documents, 'folder_store', self.store), (folders, 'folder_store', self.store),
            (documents, 'UPLOAD_DIR', self.uploads),
        ):
            patcher = patch.object(target, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        app = FastAPI()
        app.include_router(documents.router, prefix='/api')
        app.include_router(folders.router, prefix='/api')

        def test_db():
            with self.sessions() as session:
                yield session

        def test_user(x_test_user: int = Header(default=1)):
            return SimpleNamespace(id=x_test_user)

        app.dependency_overrides[get_db] = test_db
        app.dependency_overrides[get_current_user] = test_user
        self.app = app
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def document(self, user=1, status='completed'):
        with self.sessions() as db:
            doc = Document(user_id=user, filename='contract.pdf', file_path='', status=status)
            db.add(doc)
            db.flush()
            path = self.uploads / f'{doc.id}.pdf'
            path.write_bytes(b'%PDF-1.7\ntest fixture')
            doc.file_path = str(path)
            db.add(Log(document_id=doc.id, message='Uploaded'))
            if status == 'completed':
                db.add(ExtractedData(document_id=doc.id, extracted_data={'amount': '100 RUB'}))
            db.commit()
            return doc.id, path

    def create_folder(self, name='Договоры'):
        response = self.client.post('/api/folders', json={'name': name})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['id']

    def test_canonical_money_survives_storage_and_http_without_precision_loss(self):
        doc_id, _ = self.document()
        data = normalize_ai_attributes({"amount": Decimal("9007199254740993.01"),
                                        "currency": "RUB", "contract_date": "20.09.2026"})
        with self.sessions() as db:
            db.get(Document, doc_id).extracted_data.extracted_data = data
            db.commit()
        with self.sessions() as db:
            self.assertEqual(db.get(Document, doc_id).extracted_data.extracted_data, data)
        response = self.client.get('/api/documents')
        self.assertEqual(response.status_code, 200)
        self.assertIn('"amount": 9007199254740993.01', response.text)
        record = loads(response.content)[0]
        self.assertEqual(record['extracted_data'], data)
        self.assertEqual(record['display_data']['amount'], '9 007 199 254 740 993,01')
        self.assertEqual(record['display_data']['contract_date'], '20.09.2026')

    def test_folders_persist_move_in_out_and_survive_rename(self):
        doc_id, path = self.document()
        folder_id = self.create_folder()
        self.assertEqual(self.client.patch(f'/api/documents/{doc_id}/folder', json={'folder_id': folder_id}).status_code, 200)
        self.assertEqual(self.client.get('/api/documents').json()[0]['folder_id'], folder_id)
        self.assertEqual(FolderStore(self.store.root).snapshot(1)['documents'][str(doc_id)], folder_id)
        self.assertEqual(self.client.patch(f'/api/folders/{folder_id}', json={'name': 'Архив'}).status_code, 200)
        self.assertEqual(self.client.get('/api/folders').json()[0]['name'], 'Архив')
        self.assertEqual(self.client.patch(f'/api/documents/{doc_id}/folder', json={'folder_id': None}).status_code, 200)
        self.assertIsNone(self.client.get('/api/documents').json()[0]['folder_id'])
        self.assertTrue(path.exists())

    def test_deleting_folder_preserves_documents_and_results(self):
        doc_id, path = self.document()
        folder_id = self.create_folder()
        self.client.patch(f'/api/documents/{doc_id}/folder', json={'folder_id': folder_id})
        self.assertEqual(self.client.delete(f'/api/folders/{folder_id}').status_code, 200)
        record = self.client.get('/api/documents').json()[0]
        self.assertIsNone(record['folder_id'])
        self.assertEqual(record['extracted_data']['amount'], 100)
        self.assertEqual(record['display_data']['amount'], '100,00')
        self.assertTrue(path.exists())

    def test_other_users_cannot_move_or_delete_documents_or_folders(self):
        doc_id, path = self.document()
        folder_id = self.create_folder()
        foreign = {'x-test-user': '2'}
        self.assertEqual(self.client.get('/api/folders', headers=foreign).json(), [])
        self.assertEqual(self.client.get('/api/documents', headers=foreign).json(), [])
        self.assertEqual(self.client.delete(f'/api/documents/{doc_id}', headers=foreign).status_code, 404)
        self.assertEqual(self.client.patch(f'/api/documents/{doc_id}/folder', json={'folder_id': None}, headers=foreign).status_code, 404)
        self.assertEqual(self.client.delete(f'/api/folders/{folder_id}', headers=foreign).status_code, 404)
        other_doc, _ = self.document(user=2)
        self.assertEqual(self.client.patch(f'/api/documents/{other_doc}/folder', json={'folder_id': folder_id}, headers=foreign).status_code, 404)
        self.assertTrue(path.exists())

    def test_deleting_document_removes_original_result_logs_and_membership(self):
        doc_id, path = self.document()
        folder_id = self.create_folder()
        self.client.patch(f'/api/documents/{doc_id}/folder', json={'folder_id': folder_id})
        response = self.client.delete(f'/api/documents/{doc_id}')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()['cleanup_pending'])
        self.assertFalse(path.exists())
        with self.sessions() as db:
            self.assertEqual(db.query(Document).count(), 0)
            self.assertEqual(db.query(ExtractedData).count(), 0)
            self.assertEqual(db.query(Log).count(), 0)
        self.assertNotIn(str(doc_id), self.store.snapshot(1)['documents'])
        self.assertEqual(self.client.delete(f'/api/documents/{doc_id}').status_code, 404)

    def test_invalid_names_duplicates_and_missing_folders(self):
        self.create_folder('Договоры')
        for name, code in [('  договоры  ', 409), ('   ', 400), ('../outside', 400)]:
            self.assertEqual(self.client.post('/api/folders', json={'name': name}).status_code, code)
        doc_id, _ = self.document()
        self.assertEqual(self.client.patch(f'/api/documents/{doc_id}/folder', json={'folder_id': 'missing'}).status_code, 404)

    def test_upload_in_folder_and_invalid_folder_cleanup(self):
        folder_id = self.create_folder()
        with patch.object(documents, 'process_document_background', new=AsyncMock()):
            response = self.client.post('/api/documents/upload', data={'folder_id': folder_id}, files={'file': ('a.pdf', b'%PDF-1.7\nfixture', 'application/pdf')})
            self.assertEqual(response.status_code, 202, response.text)
            self.assertEqual(self.client.get('/api/documents').json()[0]['folder_id'], folder_id)
            before = set(self.uploads.iterdir())
            invalid = self.client.post('/api/documents/upload', data={'folder_id': 'missing'}, files={'file': ('b.pdf', b'%PDF-1.7\nfixture', 'application/pdf')})
            self.assertEqual(invalid.status_code, 404)
            self.assertEqual(set(self.uploads.iterdir()), before)

    def test_in_flight_analysis_does_not_resurrect_deleted_document(self):
        doc_id, path = self.document(status='pending')

        async def delete_while_waiting(_, **kwargs):
            self.assertEqual(self.client.delete(f'/api/documents/{doc_id}').status_code, 200)
            return {'amount': '100,00'}

        with patch.object(documents, 'SessionLocal', self.sessions), patch.object(documents, 'extract_text', return_value='contract'), patch.object(documents, 'fetch_ai_attributes', side_effect=delete_while_waiting):
            asyncio.run(documents.process_document_background(doc_id, str(path)))
        self.assertFalse(path.exists())
        with self.sessions() as db:
            self.assertEqual(db.query(ExtractedData).count(), 0)
            self.assertEqual(db.query(Document).count(), 0)

    def test_full_pipeline_saves_coverage_and_progress_only_after_success(self):
        doc_id, path = self.document(status='pending')
        with patch.object(documents, 'SessionLocal', self.sessions), \
             patch.object(documents, 'extract_text', return_value='x' * 150), \
             patch.object(pipeline, 'MAX_PROMPT_CHARS', 100), \
             patch.object(pipeline, 'CHUNK_OVERLAP_CHARS', 10), \
             patch.object(pipeline, 'POLZA_API_KEY', 'test'), \
             patch.object(pipeline, 'POLZA_API_URL', 'https://provider.invalid'), \
             patch.object(pipeline, 'fetch_chunk_attributes', new=AsyncMock(side_effect=[{'amount': None}, {'amount': 12345}])):
            asyncio.run(documents.process_document_background(doc_id, str(path)))
        record = self.client.get('/api/documents').json()[0]
        self.assertEqual(record['status'], 'completed')
        self.assertEqual(record['extracted_data']['amount'], 12345)
        self.assertEqual(record['extracted_data']['processing']['chunks_completed'], 2)
        self.assertIn('Обработано частей: 2/2', record['logs'])

    def test_failed_chunk_persists_no_partial_extraction(self):
        doc_id, path = self.document(status='pending')
        with patch.object(documents, 'SessionLocal', self.sessions), \
             patch.object(documents, 'extract_text', return_value='x' * 150), \
             patch.object(pipeline, 'MAX_PROMPT_CHARS', 100), \
             patch.object(pipeline, 'CHUNK_OVERLAP_CHARS', 10), \
             patch.object(pipeline, 'POLZA_API_KEY', 'test'), \
             patch.object(pipeline, 'POLZA_API_URL', 'https://provider.invalid'), \
             patch.object(pipeline, 'fetch_chunk_attributes', new=AsyncMock(side_effect=[{'amount': 100}, AIServiceError('Сбой части 2/2')])):
            with self.assertLogs('app.routers.documents', level='ERROR'):
                asyncio.run(documents.process_document_background(doc_id, str(path)))
        record = self.client.get('/api/documents').json()[0]
        self.assertEqual(record['status'], 'failed')
        self.assertIsNone(record['extracted_data'])
        self.assertIn('Обработано частей: 1/2', record['logs'])
        self.assertTrue(any('Сбой части 2/2' in log for log in record['logs']))

    def test_delete_between_chunks_cancels_remaining_analysis(self):
        doc_id, path = self.document(status='pending')
        async def delete_during_chunk(*args):
            self.assertEqual(self.client.delete(f'/api/documents/{doc_id}').status_code, 200)
            return {'amount': 100}
        with patch.object(documents, 'SessionLocal', self.sessions), \
             patch.object(documents, 'extract_text', return_value='x' * 350), \
             patch.object(pipeline, 'MAX_PROMPT_CHARS', 100), \
             patch.object(pipeline, 'CHUNK_OVERLAP_CHARS', 10), \
             patch.object(pipeline, 'POLZA_API_KEY', 'test'), \
             patch.object(pipeline, 'POLZA_API_URL', 'https://provider.invalid'), \
             patch.object(pipeline, 'fetch_chunk_attributes', new=AsyncMock(side_effect=delete_during_chunk)) as request:
            asyncio.run(documents.process_document_background(doc_id, str(path)))
        self.assertEqual(request.await_count, 1)
        with self.sessions() as db:
            self.assertEqual(db.query(Document).count(), 0)
            self.assertEqual(db.query(ExtractedData).count(), 0)
            self.assertEqual(db.query(Log).count(), 0)

    def test_failed_db_delete_restores_original_file(self):
        doc_id, path = self.document()
        with self.sessions() as db:
            with patch.object(db, 'commit', side_effect=RuntimeError('test commit failure')):
                with self.assertRaises(RuntimeError):
                    documents.delete_document(doc_id, db=db, current_user=SimpleNamespace(id=1))
        self.assertTrue(path.exists())
        with self.sessions() as db:
            self.assertIsNotNone(db.get(Document, doc_id))

    def test_unauthenticated_requests_are_rejected(self):
        del self.app.dependency_overrides[get_current_user]
        self.assertEqual(self.client.get('/api/folders').status_code, 401)
        self.assertEqual(self.client.delete('/api/documents/1').status_code, 401)

    def test_concurrent_folder_updates_do_not_overwrite_each_other(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda index: self.store.create(1, f'Папка {index}'), range(12)))
        self.assertEqual(len(self.store.snapshot(1)['folders']), 12)


if __name__ == '__main__':
    unittest.main()
