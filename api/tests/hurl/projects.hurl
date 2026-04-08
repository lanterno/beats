# List projects (no auth required for GET)
GET http://localhost:7999/api/projects/
HTTP 200
[Asserts]
jsonpath "$" isCollection

# Create a project (auth required)
POST http://localhost:7999/api/projects/
X-API-Token: secret
Content-Type: application/json
{
  "name": "Hurl Test Project",
  "description": "Created by Hurl contract tests"
}
HTTP 201
[Asserts]
jsonpath "$.id" exists
jsonpath "$.name" == "Hurl Test Project"
[Captures]
project_id: jsonpath "$.id"

# Verify it appears in the list
GET http://localhost:7999/api/projects/
HTTP 200
[Asserts]
jsonpath "$[*].name" includes "Hurl Test Project"

# Archive the project
POST http://localhost:7999/api/projects/{{project_id}}/archive
X-API-Token: secret
HTTP 200
[Asserts]
jsonpath "$.status" == "success"
