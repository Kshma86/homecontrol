import base64
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'infra/backend'))
sys.path.insert(0, str(ROOT / 'apps/ai-server'))
from PIL import Image
from ai_images import validate_images
from ai_proxy_service import AiProxyService
spec = importlib.util.spec_from_file_location('hc_ai_server', ROOT / 'apps/ai-server/ai_server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def picture(fmt='PNG'):
    out = io.BytesIO()
    Image.new('RGB', (3, 2), 'red').save(out, format=fmt)
    return {'mime_type': {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}[fmt],
            'data': base64.b64encode(out.getvalue()).decode()}


class Response(io.BytesIO):
    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode())


class ImageChatTest(unittest.TestCase):
    def test_formats_and_multiple(self):
        images = [picture(fmt) for fmt in ['PNG', 'JPEG', 'WEBP']]
        self.assertEqual(validate_images(images), images)
        self.assertEqual(validate_images(None), [])

    def test_invalid_uploads(self):
        good = picture()
        for images in [good, [good] * 5, [{'mime_type': 'image/gif', 'data': good['data']}],
                       [{'mime_type': 'image/jpeg', 'data': good['data']}],
                       [{'mime_type': 'image/png', 'data': 'not base64'}],
                       [{'mime_type': 'image/png', 'data': base64.b64encode(b'not an image').decode()}],
                       [{'mime_type': 'image/png', 'data': 'A' * (4 * 1024 * 1024 + 1)}]]:
            with self.subTest(images=str(images)[:80]), self.assertRaises(ValueError):
                validate_images(images)

    def test_truncated_image(self):
        good = picture('JPEG')
        good['data'] = base64.b64encode(base64.b64decode(good['data'])[:-20]).decode()
        with self.assertRaises(ValueError):
            validate_images([good])

    def test_pixel_limit(self):
        image = picture()
        with patch('ai_images.Image.open') as opened:
            opened.return_value.__enter__.return_value.width = 20_000_001
            opened.return_value.__enter__.return_value.height = 1
            opened.return_value.__enter__.return_value.format = 'PNG'
            with self.assertRaises(ValueError):
                validate_images([image])

    def test_native_ollama_payload_and_text_regression(self):
        config = server.default_config()
        images = [picture()]
        with patch.object(server, 'ollama_json', return_value=Response({'message': {'content': 'ok'}})) as call:
            self.assertEqual(server.ollama_reply('describe', [], config, images=images), 'ok')
            args, kwargs = call.call_args
            self.assertEqual(args[0], '/api/chat')
            payload = args[1]
            self.assertEqual(payload['messages'][-1], {'role': 'user', 'content': 'describe', 'images': [i['data'] for i in images]})
            self.assertFalse(payload['stream'])
        self.assertNotIn('images', server.build_messages('hello', [], config)[-1])

    def run_chat(self, images, capabilities=None, error=None, provider='ollama'):
        config = {**server.default_config(), 'provider': provider}
        response = Response({'capabilities': capabilities or []})
        with patch.object(server, 'read_config', return_value=config), \
             patch.object(server, 'provider_health', return_value=(True, 'ready')), \
             patch.object(server, 'direct_context_reply', return_value='must not use') as direct, \
             patch.object(server, 'ollama_json', side_effect=error, return_value=response), \
             patch.object(server, 'ollama_reply', return_value='vision answer') as reply:
            result = server.chat_response('klíma', [], {'ok': True}, images)
            return result, direct.call_count, reply.call_count

    def test_vision_success_bypasses_direct_reply(self):
        (data, status), direct, reply = self.run_chat([picture()], ['completion', 'vision'])
        self.assertEqual(status, 200)
        self.assertEqual(data['reply'], '1. kép\nvision answer')
        self.assertEqual((direct, reply), (0, 1))

    def test_nonvision_rejected(self):
        (data, status), _, reply = self.run_chat([picture()], ['completion'])
        self.assertEqual(status, 400)
        self.assertIn('képfeldolgozást', data['error'])
        self.assertEqual(reply, 0)

    def test_other_provider_rejected(self):
        (data, status), _, reply = self.run_chat([picture()], provider='fallback')
        self.assertEqual(status, 400)
        self.assertEqual(reply, 0)

    def test_capability_error_never_falls_back(self):
        (data, status), _, reply = self.run_chat([picture()], error=URLError('offline'))
        self.assertEqual(status, 502)
        self.assertFalse(data['ok'])
        self.assertNotIn('reply', data)

    def test_provider_error_never_falls_back(self):
        with patch.object(server, 'read_config', return_value={**server.default_config(), 'provider': 'ollama'}), \
             patch.object(server, 'ollama_json', return_value=Response({'capabilities': ['vision']})), \
             patch.object(server, 'provider_health', return_value=(True, 'ready')), \
             patch.object(server, 'ollama_reply', side_effect=ValueError('Image processing failed')):
            data, status = server.chat_response('describe', [], {'ok': True}, [picture()])
            self.assertEqual(status, 502)
            self.assertIn('Image processing failed', data['error'])
            self.assertNotIn('reply', data)

    def test_gateway_invalid_image_is_400(self):
        (data, status), _, _ = self.run_chat([{'mime_type': 'image/png', 'data': '!'}])
        self.assertEqual(status, 400)

    def test_proxy_passes_images_without_audit_storage(self):
        images = [picture()]
        rows = []
        service = AiProxyService('http://ai', 10, context_summary=lambda: {'ok': True},
                                 json_ready=lambda x: x, audit_logger=rows.append)
        with patch.object(service, '_proxy', return_value=({'ok': True, 'reply': 'ok'}, 200)) as call, \
             patch.object(service, 'direct_context_reply') as direct:
            data, status = service.chat({'message': '', 'images': images})
            self.assertEqual(status, 200)
            self.assertEqual(call.call_args.args[1]['images'], images)
            direct.assert_not_called()
        self.assertNotIn(images[0]['data'], json.dumps(rows))

    def test_proxy_rejects_invalid_image_before_upstream(self):
        service = AiProxyService('http://ai', 10, context_summary=lambda: {}, json_ready=lambda x: x)
        with patch.object(service, '_proxy') as call:
            self.assertEqual(service.chat({'message': 'hello', 'images': [{}]})[1], 400)
            call.assert_not_called()

    def test_multi_image_requests_are_ordered_and_independent(self):
        images = [picture('PNG'), picture('JPEG'), picture('WEBP')]
        captured = []
        def send(path, payload, **kwargs):
            import copy
            captured.append(copy.deepcopy(payload))
            return Response({'message': {'content': f'answer {len(captured)}'}})
        with patch.object(server, 'ollama_json', side_effect=send):
            results = server.sequential_image_replies('same prompt', images, server.default_config())
        self.assertEqual([r['index'] for r in results], [1, 2, 3])
        self.assertEqual([r['reply'] for r in results], ['answer 1', 'answer 2', 'answer 3'])
        for i, payload in enumerate(captured):
            self.assertEqual(len(payload['messages']), 2)
            self.assertEqual(payload['messages'][-1], {'role': 'user', 'content': 'same prompt', 'images': [images[i]['data']]})
            self.assertFalse(payload['think'])
            self.assertFalse(any(m['role'] == 'assistant' for m in payload['messages']))
        self.assertEqual(server.image_results_reply(results), '1. kép\nanswer 1\n\n2. kép\nanswer 2\n\n3. kép\nanswer 3')

    def test_multi_image_partial_failure_continues_and_preserves_order(self):
        images = [picture(), picture('JPEG'), picture('WEBP')]
        calls = []
        def send(path, payload, **kwargs):
            calls.append(payload['messages'][-1]['images'])
            if len(calls) == 2:
                raise HTTPError('http://ollama', 500, 'bad image', {}, io.BytesIO(b'processing failed'))
            return Response({'message': {'content': f'answer {len(calls)}'}})
        with patch.object(server, 'read_config', return_value={**server.default_config(), 'provider': 'ollama'}), \
             patch.object(server, 'provider_health', return_value=(True, 'ready')), \
             patch.object(server, 'ollama_json', side_effect=lambda path, *args, **kwargs: Response({'capabilities': ['vision']}) if path == '/api/show' else send(path, *args, **kwargs)):
            data, status = server.chat_response('same prompt', [{'role': 'assistant', 'content': 'old answer'}], {'ok': True}, images)
        self.assertEqual(status, 200)
        self.assertTrue(data['partial'])
        self.assertEqual([r['ok'] for r in data['image_results']], [True, False, True])
        self.assertIn('2. kép\nHiba:', data['reply'])
        self.assertIn('3. kép\nanswer 3', data['reply'])
        self.assertEqual(calls, [[i['data']] for i in images])

    def test_single_image_excludes_old_history_and_context(self):
        with patch.object(server, 'ollama_reply', return_value='ok') as call:
            result = server.sequential_image_replies('question', [picture()], server.default_config())
        self.assertEqual(result, [{'index': 1, 'ok': True, 'reply': 'ok'}])
        self.assertEqual(call.call_args.args[1], [])
        self.assertNotIn('context', call.call_args.kwargs)
        self.assertEqual(len(call.call_args.kwargs['images']), 1)

    def test_low_level_rejects_multi_image_payload(self):
        with self.assertRaisesRegex(ValueError, 'pontosan egy'):
            server.ollama_reply('question', [], server.default_config(), images=[picture(), picture()])

    def test_empty_response_and_timeout_do_not_skip_later_images(self):
        with patch.object(server, 'ollama_reply', side_effect=['', TimeoutError('timeout'), 'ok']) as call:
            results = server.sequential_image_replies('question', [picture()] * 3, server.default_config())
        self.assertEqual([r['ok'] for r in results], [False, False, True])
        self.assertEqual(call.call_count, 3)
        self.assertLessEqual(call.call_args.kwargs['image_timeout'] * 2 * 3, server.REQUEST_TIMEOUT)

    def test_all_failed_images_return_numbered_errors(self):
        with patch.object(server, 'read_config', return_value={**server.default_config(), 'provider': 'ollama'}), \
             patch.object(server, 'provider_health', return_value=(True, 'ready')), \
             patch.object(server, 'ollama_json', return_value=Response({'capabilities': ['vision']})), \
             patch.object(server, 'ollama_reply', side_effect=[ValueError('first failed'), TimeoutError('second failed')]) as call:
            data, status = server.chat_response('question', [], {}, [picture(), picture('JPEG')])
        self.assertEqual(status, 502)
        self.assertFalse(data['ok'])
        self.assertEqual(call.call_count, 2)
        self.assertIn('1. kép\nHiba: first failed', data['error'])
        self.assertIn('2. kép\nHiba: second failed', data['error'])
        self.assertNotIn('reply', data)

    def test_text_chat_still_uses_history_and_context(self):
        history = [{'role': 'user', 'content': 'previous'}]
        context = {'ok': True}
        with patch.object(server, 'read_config', return_value={**server.default_config(), 'provider': 'ollama'}), \
             patch.object(server, 'provider_health', return_value=(True, 'ready')), \
             patch.object(server, 'direct_context_reply', return_value=''), \
             patch.object(server, 'ollama_reply', return_value='text reply') as call:
            data, status = server.chat_response('hello', history, context)
        self.assertEqual(status, 200)
        self.assertEqual(data['reply'], 'text reply')
        self.assertNotIn('image_results', data)
        self.assertEqual(call.call_args.args[1], history)
        self.assertEqual(call.call_args.args[3], context)

    def test_json_test_settings_reach_ollama(self):
        config = server.normalize_config({"format": "json", "temperature": 0, "num_predict": 256})
        with patch.object(server, 'ollama_json', return_value=Response({'message': {'content': '{"answer":"ok"}'}})) as call:
            server.ollama_reply('JSON választ kérek', [], config)
            payload = call.call_args.args[1]
            self.assertEqual(payload['format'], 'json')
            self.assertEqual(payload['options']['temperature'], 0)
            self.assertEqual(payload['options']['num_predict'], 256)
            self.assertFalse(payload['think'])
            self.assertFalse(payload['stream'])
        self.assertEqual(server.normalize_config({})['format'], '')

    def test_vision_context_and_history_are_bounded(self):
        config = server.default_config()
        context = {'knowledge_docs': {'content': 'x' * 100000}, 'house': {'status': 'y' * 100000}}
        messages = server.vision_messages('original question', [{'role': 'user', 'content': 'z' * 20000}] * 20, config, context)
        self.assertLess(sum(len(m['content']) for m in messages), 14000)
        self.assertEqual(messages[-1]['content'], 'original question')

    def test_context_overflow_retries_once_with_smaller_payload(self):
        captured = []
        images = [picture()]
        def send(path, payload, **kwargs):
            import copy
            captured.append(copy.deepcopy(payload))
            if len(captured) == 1:
                raise HTTPError('http://ollama', 400, 'bad request', {}, io.BytesIO(b'{"error":"request exceeds the available context size"}'))
            return Response({'message': {'content': 'red'}})
        with patch.object(server, 'ollama_json', side_effect=send):
            self.assertEqual(server.ollama_reply('question', [{'role': 'user', 'content': 'old'}], server.default_config(), {'ok': True}, images), 'red')
        self.assertEqual(len(captured), 2)
        self.assertEqual(len(captured[1]['messages']), 2)
        self.assertEqual(captured[1]['messages'][-1]['content'], 'question')
        self.assertEqual(captured[1]['options']['num_ctx'], captured[0]['options']['num_ctx'])
        self.assertEqual(images, [picture()])

    def test_repeated_context_overflow_is_friendly_and_bounded(self):
        def send(*args, **kwargs):
            raise HTTPError('http://ollama', 400, 'bad request', {}, io.BytesIO(b'exceed_context_size_error'))
        with patch.object(server, 'ollama_json', side_effect=send) as call:
            with self.assertRaisesRegex(ValueError, 'kevesebb képet'):
                server.ollama_reply('question', [], server.default_config(), images=[picture()])
            self.assertEqual(call.call_count, 2)

    def test_other_http_errors_are_not_retried_or_consumed(self):
        with patch.object(server, 'ollama_json', side_effect=HTTPError('http://ollama', 400, 'bad request', {}, io.BytesIO(b'invalid image'))) as call:
            with self.assertRaises(HTTPError) as raised:
                server.ollama_reply('question', [], server.default_config(), images=[picture()])
            self.assertEqual(raised.exception.read(), b'invalid image')
            self.assertEqual(call.call_count, 1)

    def test_retry_images_resized_without_changing_original(self):
        out = io.BytesIO()
        Image.new('RGB', (2400, 1800), 'red').save(out, format='PNG')
        original = base64.b64encode(out.getvalue()).decode()
        smaller = server.reduced_vision_images([{'data': original}])[0]
        with Image.open(io.BytesIO(base64.b64decode(smaller))) as img:
            self.assertEqual(img.size, (1024, 768))
        with Image.open(io.BytesIO(base64.b64decode(original))) as img:
            self.assertEqual(img.size, (2400, 1800))

    def test_gateway_request_body_limit(self):
        handler = type('Handler', (), {'headers': {'Content-Length': str(17 * 1024 * 1024 + 1)}, 'rfile': io.BytesIO()})()
        with self.assertRaises(ValueError):
            server.read_json(handler)

    def test_validator_copies_match(self):
        self.assertEqual((ROOT / 'infra/backend/ai_images.py').read_bytes(), (ROOT / 'apps/ai-server/ai_images.py').read_bytes())

if __name__ == '__main__':
    unittest.main()
