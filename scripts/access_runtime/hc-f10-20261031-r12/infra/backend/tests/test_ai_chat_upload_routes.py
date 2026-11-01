"""HTTP contract tests; run with the backend's Flask dependencies."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
from api_route_modules import register_ai_routes


class AiChatUploadRouteTest(unittest.TestCase):
    def setUp(self):
        self.service = Mock()
        self.service.chat.return_value = ({'ok': True, 'reply': 'ok'}, 200)
        app = Flask(__name__)
        register_ai_routes(app, get_ai_proxy_service=lambda: self.service, get_ai_node_service=lambda: None)
        self.client = app.test_client()

    def test_image_contract_forwarded(self):
        body = {'message': '', 'history': [], 'images': [{'mime_type': 'image/png', 'data': 'abc'}]}
        response = self.client.post('/api/ai/chat', json=body)
        self.assertEqual(response.status_code, 200)
        self.service.chat.assert_called_once_with(body)

    def test_bad_json_and_nonobject(self):
        for raw in ['{', '[]', 'null']:
            response = self.client.post('/api/ai/chat', data=raw, content_type='application/json')
            self.assertEqual(response.status_code, 400)
            self.assertFalse(response.json['ok'])
        self.service.chat.assert_not_called()

    def test_request_size_limit(self):
        response = self.client.post('/api/ai/chat', data=b' ' * (17 * 1024 * 1024 + 1), content_type='application/json')
        self.assertEqual(response.status_code, 413)
        self.assertIn('17 MiB', response.json['error'])
        self.service.chat.assert_not_called()

    def test_image_errors_reach_client(self):
        self.service.chat.return_value = ({'ok': False, 'error': 'A kép sérült.'}, 400)
        response = self.client.post('/api/ai/chat', json={'message': 'describe', 'images': []})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json['error'], 'A kép sérült.')
