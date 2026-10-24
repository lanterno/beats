// A project as the API sends it, and the one line under its name: an
// organisation's project says whose it is, everywhere the kind is shown,
// and tracking on it reads the same JSON as any other (docs/organisations.md).

import 'package:beats_companion/state/timer_controller.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('a personal project is labelled by its kind alone', () {
    final project = Project.fromJson({'id': 'p1', 'name': 'Garden', 'kind': 'side_project'});
    expect(project.organisationName, isNull);
    expect(project.kindLabel, 'Side project');
  });

  test("an organisation's project carries the organisation's name", () {
    final project = Project.fromJson({
      'id': 'p2',
      'name': 'Platform',
      'kind': 'day_job',
      'organisation': {
        'id': 'o1',
        'name': 'Acme',
        'logo_url': null,
        'shared_from': '2026-03-03T23:00:00Z',
      },
    });
    expect(project.organisationName, 'Acme');
    expect(project.kindLabel, 'Day job · Acme');
  });

  test('an older API without the field, or an explicit null, is a personal project', () {
    expect(Project.fromJson({'id': 'p3', 'name': 'X', 'organisation': null}).kindLabel, 'Side project');
  });
}
