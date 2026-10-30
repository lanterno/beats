import 'offline_queue.dart';

/// What the offline layer keeps on the device: the API's last answers, the
/// writes waiting to be replayed, and the ones the API refused
/// (docs/companion-offline.md). `SqliteStore` keeps them across launches;
/// [MemoryStore] for one run (the tests, and the platforms without SQLite).
///
/// The window and the menu bar popover are two engines over one store, so
/// the operations that decide a write's fate are single statements:
/// [markSent] counts an attempt before the request leaves, and
/// [cancelUnsent] / [rewriteUnsent] touch only a write never attempted. One
/// side can't cancel what the other is sending.
abstract interface class LocalStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);

  /// Drops the cached answers whose key starts with [prefix] and sorts
  /// before [before] (keys carry ISO dates, so that is "older than").
  Future<void> prune(String prefix, String before);

  /// The writes waiting, oldest first.
  Future<List<QueuedWrite>> queued();

  /// Stores [write] at the back of the queue and returns its row id.
  Future<int> enqueue(QueuedWrite write);

  /// Counts one attempt, before the request is sent, and returns the write
  /// as it stands then; null when it was cancelled meanwhile.
  Future<QueuedWrite?> markSent(int id);

  /// Notes why the last attempt didn't land, keeping the write queued.
  Future<void> note(int id, String error);

  /// Removes a write the API applied.
  Future<void> remove(int id);

  /// Removes a write that was never attempted. False when it was, or is
  /// gone: it may have landed, and only the API can say.
  Future<bool> cancelUnsent(int id);

  /// Replaces the body of a write that was never attempted; false otherwise.
  Future<bool> rewriteUnsent(int id, Map<String, dynamic> body);

  /// Moves a write the API refused out of the queue, into [refused].
  Future<void> refuse(int id, RefusedWrite refusal);

  /// The refused writes not yet dismissed, oldest first.
  Future<List<RefusedWrite>> refused();
  Future<void> clearRefused();

  /// Forgets everything: the store belongs to one pairing.
  Future<void> clear();
}

class MemoryStore implements LocalStore {
  final _cache = <String, String>{};
  final _queue = <QueuedWrite>[];
  final _refused = <RefusedWrite>[];
  var _nextId = 1;

  @override
  Future<String?> read(String key) async => _cache[key];

  @override
  Future<void> write(String key, String value) async => _cache[key] = value;

  @override
  Future<void> prune(String prefix, String before) async =>
      _cache.removeWhere((k, _) => k.startsWith(prefix) && k.compareTo(before) < 0);

  @override
  Future<List<QueuedWrite>> queued() async => List.of(_queue);

  @override
  Future<int> enqueue(QueuedWrite write) async {
    final id = _nextId++;
    _queue.add(write.copyWith(id: id));
    return id;
  }

  int _at(int id) => _queue.indexWhere((w) => w.id == id);

  @override
  Future<QueuedWrite?> markSent(int id) async {
    final i = _at(id);
    if (i < 0) return null;
    return _queue[i] = _queue[i].copyWith(attempts: _queue[i].attempts + 1);
  }

  @override
  Future<void> note(int id, String error) async {
    final i = _at(id);
    if (i >= 0) _queue[i] = _queue[i].copyWith(lastError: error);
  }

  @override
  Future<void> remove(int id) async => _queue.removeWhere((w) => w.id == id);

  @override
  Future<bool> cancelUnsent(int id) async {
    final i = _at(id);
    if (i < 0 || _queue[i].attempts > 0) return false;
    _queue.removeAt(i);
    return true;
  }

  @override
  Future<bool> rewriteUnsent(int id, Map<String, dynamic> body) async {
    final i = _at(id);
    if (i < 0 || _queue[i].attempts > 0) return false;
    _queue[i] = _queue[i].copyWith(body: body);
    return true;
  }

  @override
  Future<void> refuse(int id, RefusedWrite refusal) async {
    _queue.removeWhere((w) => w.id == id);
    _refused.add(refusal);
  }

  @override
  Future<List<RefusedWrite>> refused() async => List.of(_refused);

  @override
  Future<void> clearRefused() async => _refused.clear();

  @override
  Future<void> clear() async {
    _cache.clear();
    _queue.clear();
    _refused.clear();
  }
}
