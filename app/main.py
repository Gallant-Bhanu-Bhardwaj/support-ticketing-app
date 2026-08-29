from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routers import health

app = FastAPI(title="Support Ticketing")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(health.router)


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "home.html")
