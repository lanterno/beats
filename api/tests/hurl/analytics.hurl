# Heatmap for current year
GET http://localhost:7999/api/analytics/heatmap?year=2026
HTTP 200
[Asserts]
jsonpath "$" isCollection

# Daily rhythm
GET http://localhost:7999/api/analytics/rhythm?period=week
HTTP 200
[Asserts]
jsonpath "$" count == 48

# Tags list
GET http://localhost:7999/api/analytics/tags
HTTP 200
[Asserts]
jsonpath "$" isCollection

# Device status
GET http://localhost:7999/api/device/status
HTTP 200
[Asserts]
jsonpath "$.clocked_in" exists
jsonpath "$.energy_level" exists
jsonpath "$.theme_accent_rgb" isCollection
