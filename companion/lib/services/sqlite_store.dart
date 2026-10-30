import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

import 'local_store.dart';
import 'offline_queue.dart';

/// Opens the device's store: SQLite in the app's support directory, which
/// the window and the menu bar popover both resolve to. Where there is no
/// SQLite plugin (Linux, Windows, the web) or the file won't open, a
/// [MemoryStore]: offline still works for the run, and nothing outlives it.
Future<LocalStore> openLocalStore() async {
  if (kIsWeb) return MemoryStore();
  try {
    final dir = await getApplicationSupportDirectory();
    await dir.create(recursive: true);
    final db = await openDatabase(
      '${dir.path}${Platform.pathSeparator}offline.db',
      version: 1,
      // The other engine may hold the write lock for a moment: wait for it
      // rather than fail the write.
      onConfigure: (db) => db.rawQuery('PRAGMA busy_timeout = 3000'),
      onCreate: (db, _) async {
        await db.execute('CREATE TABLE cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)');
        await db.execute('''
          CREATE TABLE queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            body TEXT NOT NULL,
            client_id TEXT NOT NULL,
            enqueued_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
          )''');
        await db.execute('''
          CREATE TABLE refused (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            body TEXT NOT NULL,
            refused_at TEXT NOT NULL,
            status INTEGER NOT NULL,
            code TEXT,
            detail TEXT NOT NULL
          )''');
      },
    );
    return SqliteStore(db);
  } catch (e) {
    debugPrint('Offline store unavailable, keeping it in memory: $e');
    return MemoryStore();
  }
}

class SqliteStore implements LocalStore {
  final Database _db;
  SqliteStore(this._db);

  @override
  Future<String?> read(String key) async {
    final rows = await _db.query('cache', columns: ['value'], where: 'key = ?', whereArgs: [key]);
    return rows.isEmpty ? null : rows.first['value'] as String;
  }

  @override
  Future<void> write(String key, String value) =>
      _db.insert('cache', {'key': key, 'value': value}, conflictAlgorithm: ConflictAlgorithm.replace);

  @override
  Future<void> prune(String prefix, String before) =>
      _db.delete('cache', where: 'substr(key, 1, ?) = ? AND key < ?', whereArgs: [prefix.length, prefix, before]);

  static QueuedWrite _queuedFrom(Map<String, Object?> r) => QueuedWrite(
        id: r['id'] as int,
        kind: WriteKind.values.byName(r['kind'] as String),
        body: jsonDecode(r['body'] as String) as Map<String, dynamic>,
        clientId: r['client_id'] as String,
        enqueuedAt: DateTime.parse(r['enqueued_at'] as String),
        attempts: r['attempts'] as int,
        lastError: r['last_error'] as String?,
      );

  @override
  Future<List<QueuedWrite>> queued() async =>
      [for (final r in await _db.query('queue', orderBy: 'id')) _queuedFrom(r)];

  @override
  Future<int> enqueue(QueuedWrite write) => _db.insert('queue', {
        'kind': write.kind.name,
        'body': jsonEncode(write.body),
        'client_id': write.clientId,
        'enqueued_at': write.enqueuedAt.toUtc().toIso8601String(),
        'attempts': write.attempts,
        'last_error': write.lastError,
      });

  @override
  Future<QueuedWrite?> markSent(int id) async {
    // Once the count is up neither cancelUnsent nor rewriteUnsent can touch
    // the row, so the read that follows sees what will be sent.
    if (await _db.rawUpdate('UPDATE queue SET attempts = attempts + 1 WHERE id = ?', [id]) != 1) return null;
    final rows = await _db.query('queue', where: 'id = ?', whereArgs: [id]);
    return rows.isEmpty ? null : _queuedFrom(rows.first);
  }

  @override
  Future<void> note(int id, String error) =>
      _db.update('queue', {'last_error': error}, where: 'id = ?', whereArgs: [id]);

  @override
  Future<void> remove(int id) => _db.delete('queue', where: 'id = ?', whereArgs: [id]);

  @override
  Future<bool> cancelUnsent(int id) async =>
      await _db.delete('queue', where: 'id = ? AND attempts = 0', whereArgs: [id]) == 1;

  @override
  Future<bool> rewriteUnsent(int id, Map<String, dynamic> body) async =>
      await _db.update('queue', {'body': jsonEncode(body)}, where: 'id = ? AND attempts = 0', whereArgs: [id]) == 1;

  @override
  Future<void> refuse(int id, RefusedWrite refusal) => _db.transaction((txn) async {
        await txn.delete('queue', where: 'id = ?', whereArgs: [id]);
        await txn.insert('refused', {
          'kind': refusal.kind.name,
          'body': jsonEncode(refusal.body),
          'refused_at': refusal.refusedAt.toUtc().toIso8601String(),
          'status': refusal.status,
          'code': refusal.code,
          'detail': refusal.detail,
        });
      });

  @override
  Future<List<RefusedWrite>> refused() async => [
        for (final r in await _db.query('refused', orderBy: 'id'))
          RefusedWrite(
            kind: WriteKind.values.byName(r['kind'] as String),
            body: jsonDecode(r['body'] as String) as Map<String, dynamic>,
            refusedAt: DateTime.parse(r['refused_at'] as String),
            status: r['status'] as int,
            code: r['code'] as String?,
            detail: r['detail'] as String,
          ),
      ];

  @override
  Future<void> clearRefused() => _db.delete('refused');

  @override
  Future<void> clear() => _db.transaction((txn) async {
        await txn.delete('cache');
        await txn.delete('queue');
        await txn.delete('refused');
      });
}
