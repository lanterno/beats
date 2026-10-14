// decodeSse turns the coach's text/event-stream into JSON events. The
// network hands it chunks that split events and lines anywhere, so each
// case feeds the same body through different cuts.

import 'dart:convert';

import 'package:beats_companion/services/api_client.dart';
import 'package:flutter_test/flutter_test.dart';

Stream<List<int>> chunks(List<String> parts) =>
    Stream.fromIterable(parts.map(utf8.encode));

void main() {
  const body = 'data: {"type":"text","text":"Hi"}\n\n'
      'data: {"type":"done","conversation_id":"c1"}\n\n'
      'data: [DONE]\n\n';

  test('yields each event in order and stops at [DONE]', () async {
    final events = await decodeSse(chunks([body])).toList();
    expect(events, [
      {'type': 'text', 'text': 'Hi'},
      {'type': 'done', 'conversation_id': 'c1'},
    ]);
  });

  test('reassembles events split across chunks at any byte', () async {
    for (var cut = 1; cut < body.length; cut++) {
      final events = await decodeSse(chunks([body.substring(0, cut), body.substring(cut)])).toList();
      expect(events.length, 2, reason: 'cut at $cut');
      expect(events.first['text'], 'Hi', reason: 'cut at $cut');
    }
  });

  test('reassembles a multi-byte character split between chunks', () async {
    final bytes = utf8.encode('data: {"type":"text","text":"café"}\n\n');
    final split = bytes.indexOf(0xC3) + 1; // inside the two-byte é
    final events = await decodeSse(Stream.fromIterable([
      bytes.sublist(0, split),
      bytes.sublist(split),
    ])).toList();
    expect(events.single['text'], 'café');
  });

  test('accepts CRLF line endings', () async {
    final events = await decodeSse(chunks(['data: {"type":"text","text":"a"}\r\n\r\n'])).toList();
    expect(events.single['text'], 'a');
  });

  test('skips comments, other fields and payloads that are not JSON objects', () async {
    final events = await decodeSse(chunks([
      ': keep-alive\n\n',
      'event: ping\n\n',
      'data: not json\n\n',
      'data: [1, 2]\n\n',
      'data: {"type":"text","text":"kept"}\n\n',
    ])).toList();
    expect(events.single['text'], 'kept');
  });

  test('ignores a trailing event with no blank line after it', () async {
    final events = await decodeSse(chunks(['data: {"type":"text","text":"a"}\n\ndata: {"type":"te'])).toList();
    expect(events.single['text'], 'a');
  });
}
