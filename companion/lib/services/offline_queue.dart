import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:http/http.dart' as http;

import 'api_client.dart';

/// What a queued write does. Each is replayed through the matching
/// [ApiClient] call, with the write's own `X-Client-Id`.
enum WriteKind { start, stop, log, edit }

/// A write made while the API couldn't be reached, waiting to be replayed
/// (docs/companion-offline.md). [body] holds the API's own fields, every
/// instant an ISO string in UTC:
///
/// - start: `project_id`, `time`
/// - stop: `time`, `expected` (`project_id`, `start`: the timer it stops)
/// - log: `project_id`, `start`, `end`
/// - edit: `id`, `project_id`, `start`, `end`, `expected` (`project_id`,
///   `start`, `end`: the session as the edit was made against it)
class QueuedWrite {
  /// The row id once stored; null before.
  final int? id;
  final WriteKind kind;
  final Map<String, dynamic> body;

  /// The idempotency key, chosen once when the write is made and sent with
  /// every attempt, so a replay after a lost response is answered from the
  /// API's record instead of applied twice.
  final String clientId;
  final DateTime enqueuedAt;

  /// How many times a request for it may have left the device. Zero means
  /// never: only then may the write still be cancelled or rewritten here.
  final int attempts;
  final String? lastError;

  const QueuedWrite({
    this.id,
    required this.kind,
    required this.body,
    required this.clientId,
    required this.enqueuedAt,
    this.attempts = 0,
    this.lastError,
  });

  QueuedWrite copyWith({int? id, int? attempts, String? lastError, Map<String, dynamic>? body}) => QueuedWrite(
        id: id ?? this.id,
        kind: kind,
        body: body ?? this.body,
        clientId: clientId,
        enqueuedAt: enqueuedAt,
        attempts: attempts ?? this.attempts,
        lastError: lastError ?? this.lastError,
      );

  /// The session this write leaves behind, as the API would return it, for
  /// a caller that needs one before the API has answered. `queued` carries
  /// the row id, which is how an undo or a moved start finds the write.
  Map<String, dynamic> placeholder(int rowId) {
    final b = body;
    return switch (kind) {
      WriteKind.start => {'id': null, 'project_id': b['project_id'], 'start': b['time'], 'end': null, 'queued': rowId},
      WriteKind.stop => {
          'id': null,
          'project_id': (b['expected'] as Map)['project_id'],
          'start': (b['expected'] as Map)['start'],
          'end': b['time'],
          'queued': rowId,
        },
      WriteKind.log => {'id': null, 'project_id': b['project_id'], 'start': b['start'], 'end': b['end'], 'queued': rowId},
      WriteKind.edit => {'id': b['id'], 'project_id': b['project_id'], 'start': b['start'], 'end': b['end'], 'queued': rowId},
    };
  }
}

/// A queued write the API refused on replay. It is dropped from the queue,
/// since sending it again would be refused again, and kept here until the
/// person has read why.
class RefusedWrite {
  final WriteKind kind;
  final Map<String, dynamic> body;
  final DateTime refusedAt;
  final int status;
  final String? code;

  /// What the API said, without the client's "Stop timer failed: " prefix.
  final String detail;

  const RefusedWrite({
    required this.kind,
    required this.body,
    required this.refusedAt,
    required this.status,
    this.code,
    required this.detail,
  });

  factory RefusedWrite.from(QueuedWrite write, ApiException e, DateTime at) {
    final cut = e.message.indexOf(': ');
    return RefusedWrite(
      kind: write.kind,
      body: write.body,
      refusedAt: at,
      status: e.statusCode,
      code: e.code,
      detail: cut < 0 ? e.message : e.message.substring(cut + 2),
    );
  }
}

/// A random (version 4) UUID, the idempotency key of one write.
String newClientId([Random? random]) {
  final r = random ?? Random.secure();
  final bytes = List<int>.generate(16, (_) => r.nextInt(256));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-'
      '${hex.substring(16, 20)}-${hex.substring(20)}';
}

/// Whether the API answered and should be asked again later rather than
/// taken at its word. A 5xx is the server's trouble, a 429 or 408 its
/// pace, a 401 or 403 a pairing to mend (the write is still wanted), and
/// IDEMPOTENT_IN_PROGRESS the same write still running from another try.
/// Any other 4xx is final: replayed, it would be refused forever.
bool isRetryable(ApiException e) =>
    e.statusCode >= 500 ||
    e.statusCode == 401 ||
    e.statusCode == 403 ||
    e.statusCode == 408 ||
    e.statusCode == 429 ||
    e.code == 'IDEMPOTENT_IN_PROGRESS';

/// Whether a failed request certainly never reached the API: no address
/// for the host, nothing listening, no route. Anything else (a timeout, a
/// connection cut mid-answer) may have been applied with its answer lost.
bool definitelyNotSent(Object error) {
  if (error is TimeoutException) return false;
  final text = switch (error) {
    SocketException e => '${e.message} ${e.osError?.message ?? ''}',
    http.ClientException e => e.message,
    _ => '',
  }
      .toLowerCase();
  return const [
    'failed host lookup',
    'connection refused',
    'network is unreachable',
    'no route to host',
    'nodename nor servname',
    'no address associated',
  ].any(text.contains);
}
