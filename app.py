import uvicorn

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel

from backend import run_travel_agent

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Nomadiq Intelligent Nomad",
    description="An intelligent travel planning assistant that helps users plan trips, find flights, hotels, and create itineraries.",
    version="1.0.0",
)

