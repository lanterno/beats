import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from beats.settings import settings
from beats.routers.projects import router as projects_router
from beats.routers.beats import router as beats_router

logger = logging.getLogger(__name__)
app = FastAPI()
origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://localhost:8080",
    "https://lifepete.com",
    "http://lifepete.com"
    "http://site.lifepete.com/"
]

app.include_router(projects_router)
app.include_router(beats_router)


@app.middleware("http")
async def authenticate(request: Request, call_next):
    logger.error(request.method)
    PROTECTED_METHODS = ["POST", "PUT", "PATCH"]
    if request.method in PROTECTED_METHODS and "X-API-Token" not in request.headers:
        return JSONResponse(
            content={"error": "Header X-API-Token is required for all POST actions"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    if request.method in PROTECTED_METHODS and request.headers["X-API-Token"] != settings.access_token:
        return JSONResponse(
            content={"error": "your X-API-Token is not valid"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    response = await call_next(request)
    return response


@app.post("/talk/ding")
async def ding():
    return {"message": "dong"}


# Putting the middleware at the end fixes a CORS issue with 401 POST requests
# There is still an issue with 500's
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
