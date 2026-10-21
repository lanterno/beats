"""The headers every answer under /api/public/ carries (docs/billing.md,
phase 1c).

A report link's report is someone's billable hours, opened with no session,
perhaps on a shared computer or through a mail scanner: no cache may keep it,
no page may pass on where it came from, and no crawler may index it. So every
response under the prefix gets these, whatever produced it — the route's
200, its 404 and 429, the validation handler's 422, the auth middleware's
403 to a device token.

Pure ASGI rather than `BaseHTTPMiddleware`: it only rewrites the start
message's headers, and never buffers a body. Exception handlers run inside
user middleware, so their answers pass through here. A 500 is produced by
Starlette's `ServerErrorMiddleware`, outside every user middleware, and gets
none of them; it carries no data.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

PUBLIC_PATH_PREFIX = "/api/public/"

PUBLIC_RESPONSE_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    "X-Content-Type-Options": "nosniff",
}


class PublicResponseHeadersMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(PUBLIC_PATH_PREFIX):
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in PUBLIC_RESPONSE_HEADERS.items():
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
