# List webhooks (empty initially)
GET http://localhost:7999/api/webhooks/
X-API-Token: secret
HTTP 200
[Asserts]
jsonpath "$" isCollection

# Create a webhook
POST http://localhost:7999/api/webhooks/
X-API-Token: secret
Content-Type: application/json
{
  "url": "https://example.com/hook",
  "events": ["timer.start", "timer.stop"]
}
HTTP 201
[Asserts]
jsonpath "$.id" exists
jsonpath "$.url" == "https://example.com/hook"
jsonpath "$.active" == true
[Captures]
webhook_id: jsonpath "$.id"

# Verify it appears in list
GET http://localhost:7999/api/webhooks/
X-API-Token: secret
HTTP 200
[Asserts]
jsonpath "$" count >= 1

# Delete the webhook
DELETE http://localhost:7999/api/webhooks/{{webhook_id}}
X-API-Token: secret
HTTP 200
[Asserts]
jsonpath "$.deleted" == true
