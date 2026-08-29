from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.core.templates import templates
from app.routers import auth, health, pages

app = FastAPI(title="Support Ticketing")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(pages.router)


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "home.html")
