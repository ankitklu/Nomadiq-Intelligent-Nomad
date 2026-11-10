import uvicorn

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel

from backend import run_travel_agent, init_travel_agent, close_travel_agent

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_travel_agent()
    yield
    await close_travel_agent()


app = FastAPI(
    title="Nomadiq Intelligent Nomad",
    description="An intelligent travel planning assistant that helps users plan trips, find flights, hotels, and create itineraries.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    message = payload.message.strip()

    if not message:
        return JSONResponse(status_code=400, content={"error": "Message cannot be empty."})

    try:
        result = await run_travel_agent(user_input=message, thread_id=payload.thread_id)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    return result


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
