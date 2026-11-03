import test from 'node:test';
import assert from 'node:assert/strict';
import { validateImageFiles, storedAiMessages, imagePayload } from '../src/features/ai/aiImages.mjs';
const file = (name = 'image.png', type = 'image/png', size = 100) => ({ name, type, size });
test('accepts multiple JPG, PNG and WebP attachments', () => {
  assert.doesNotThrow(() => validateImageFiles([file(), file('a.jpg', 'image/jpeg'), file('b.webp', 'image/webp')]));
});
test('rejects invalid type, extension, empty, oversized and excess files', () => {
  for (const files of [[file('a.gif', 'image/gif')], [file('a.txt')], [file('a.png', 'image/png', 0)], [file('a.png', 'image/png', 3 * 1024 * 1024 + 1)], Array(5).fill(file())]) {
    assert.throws(() => validateImageFiles(files));
  }
  assert.throws(() => validateImageFiles([file()], 4));
});
test('image bytes and previews never enter persistent chat storage', () => {
  const messages = [{role: 'user', content: 'describe', images: [{data: 'secret', url: 'data:secret'}]}, {role: 'assistant', content: 'par', fullContent: 'partial reply', typing: true}];
  const stored = storedAiMessages(messages, 20);
  assert.equal(JSON.stringify(stored).includes('secret'), false);
  assert.equal(stored[1].content, 'partial reply');
  assert.equal(storedAiMessages(messages, 1).length, 1);
  assert.equal(messages[0].images[0].data, 'secret');
});
test('request includes only image MIME and base64', () => {
  assert.deepEqual(imagePayload([{mime_type: 'image/png', data: 'abc', name: 'a.png', url: 'data:abc'}]), [{mime_type: 'image/png', data: 'abc'}]);
});
