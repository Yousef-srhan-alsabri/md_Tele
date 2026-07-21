import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from app.config import get_settings
from app.database import SessionLocal
from app.models import User
from app.routers.api import router
from app.security import hash_password
from app.services.job_worker import start_worker, stop_worker

logging.basicConfig(level=logging.INFO)
settings=get_settings(); templates=Jinja2Templates(directory='app/templates')

@asynccontextmanager
async def lifespan(app:FastAPI):
    with SessionLocal.begin() as db:
        admin=db.scalar(select(User).where(User.username==settings.admin_username.lower()))
        if not admin: db.add(User(username=settings.admin_username.lower(),password_hash=hash_password(settings.admin_password),is_admin=True,balance=0))
    start_worker(); yield; await stop_worker()

app=FastAPI(title=settings.app_name,lifespan=lifespan)
app.mount('/static',StaticFiles(directory='app/static'),name='static'); app.include_router(router)
@app.get('/',response_class=HTMLResponse)
def index(request:Request): return templates.TemplateResponse('index.html',{'request':request,'app_name':settings.app_name,'registration':settings.public_registration})
@app.get('/health')
def health(): return {'status':'ok'}
