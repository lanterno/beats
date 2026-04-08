# Timer status (no auth for GET)
GET http://localhost:7999/api/timer/status
HTTP 200
[Asserts]
jsonpath "$.isBeating" exists

# Create a project for timer test
POST http://localhost:7999/api/projects/
X-API-Token: secret
Content-Type: application/json
{
  "name": "Timer Test Project",
  "description": "For timer contract tests"
}
HTTP 201
[Captures]
project_id: jsonpath "$.id"

# Start timer
POST http://localhost:7999/api/projects/{{project_id}}/start
X-API-Token: secret
Content-Type: application/json
{
  "time": "2026-04-08T10:00:00Z"
}
HTTP 200
[Asserts]
jsonpath "$.project_id" == "{{project_id}}"
jsonpath "$.end" == null

# Verify timer is running
GET http://localhost:7999/api/timer/status
HTTP 200
[Asserts]
jsonpath "$.isBeating" == true

# Stop timer
POST http://localhost:7999/api/projects/stop
X-API-Token: secret
Content-Type: application/json
{
  "time": "2026-04-08T11:00:00Z"
}
HTTP 200
[Asserts]
jsonpath "$.end" exists
