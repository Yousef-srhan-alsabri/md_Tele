from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import get_db
from app.dependencies import COOKIE_NAME, get_admin, get_current_user
from app.models import BalanceTransaction, Job, JobStatus, Link, LinkStatus, TelegramAccount, User
from app.schemas import ChargeRequest, CodeRequest, LinksRequest, LoginRequest, PhoneRequest, RegisterRequest, SettingsRequest
from app.security import create_access_token, encrypt_session, hash_password, verify_password
from app.services.telegram_service import begin_login, complete_login, extract_links

router = APIRouter(prefix="/api")
settings = get_settings()

def user_payload(user: User) -> dict:
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin, "balance": user.balance, "delay_seconds": user.delay_seconds, "rest_minutes": user.rest_minutes}

@router.post('/auth/register')
def register(data: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    if not settings.public_registration:
        raise HTTPException(403, 'التسجيل العام مغلق')
    user = User(username=data.username.lower(), password_hash=hash_password(data.password), balance=settings.default_user_balance)
    db.add(user)
    try: db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, 'اسم المستخدم مستخدم')
    db.refresh(user); response.set_cookie(COOKIE_NAME, create_access_token(user.id), httponly=True, secure=settings.environment=='production', samesite='lax', max_age=604800)
    return user_payload(user)

@router.post('/auth/login')
def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == data.username.lower()))
    if not user or not verify_password(data.password, user.password_hash): raise HTTPException(401, 'بيانات الدخول غير صحيحة')
    response.set_cookie(COOKIE_NAME, create_access_token(user.id), httponly=True, secure=settings.environment=='production', samesite='lax', max_age=604800)
    return user_payload(user)

@router.post('/auth/logout')
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME); return {'ok': True}

@router.get('/me')
def me(user: User = Depends(get_current_user)): return user_payload(user)

@router.get('/dashboard')
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accounts = db.scalars(select(TelegramAccount).where(TelegramAccount.user_id == user.id).order_by(TelegramAccount.id.desc())).all()
    links = db.scalars(select(Link).where(Link.user_id == user.id).order_by(Link.id.desc()).limit(100)).all()
    jobs = db.scalars(select(Job).where(Job.user_id == user.id).order_by(Job.id.desc()).limit(10)).all()
    return {'user': user_payload(user), 'accounts':[{'id':a.id,'phone':a.phone,'is_active':a.is_active} for a in accounts], 'links':[{'id':l.id,'value':l.value,'status':l.status,'message':l.last_message} for l in links], 'jobs':[{'id':j.id,'status':j.status,'processed':j.processed,'successful':j.successful,'failed':j.failed,'error':j.last_error} for j in jobs]}

@router.post('/telegram/login/start')
async def telegram_start(data: PhoneRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count()).select_from(TelegramAccount).where(TelegramAccount.user_id == user.id))
    if count >= settings.max_accounts_per_user: raise HTTPException(400, 'بلغت الحد الأقصى للحسابات')
    return {'login_id': await begin_login(user.id, data.phone)}

@router.post('/telegram/login/complete')
async def telegram_complete(data: CodeRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try: phone, session = await complete_login(user.id, data.login_id, data.code, data.password)
    except PermissionError: raise HTTPException(428, 'مطلوب رمز التحقق بخطوتين')
    except ValueError as exc: raise HTTPException(400, str(exc))
    db.query(TelegramAccount).filter(TelegramAccount.user_id==user.id).update({'is_active':False})
    account = TelegramAccount(user_id=user.id, phone=phone, encrypted_session=encrypt_session(session), is_active=True)
    db.add(account)
    try: db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409, 'الرقم مسجل مسبقاً')
    return {'ok':True}

@router.post('/accounts/{account_id}/activate')
def activate(account_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    account=db.scalar(select(TelegramAccount).where(TelegramAccount.id==account_id,TelegramAccount.user_id==user.id))
    if not account: raise HTTPException(404,'الحساب غير موجود')
    db.query(TelegramAccount).filter(TelegramAccount.user_id==user.id).update({'is_active':False}); account.is_active=True; db.commit(); return {'ok':True}

@router.delete('/accounts/{account_id}')
def remove_account(account_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    account=db.scalar(select(TelegramAccount).where(TelegramAccount.id==account_id,TelegramAccount.user_id==user.id))
    if not account: raise HTTPException(404,'الحساب غير موجود')
    db.delete(account); db.commit(); return {'ok':True}

@router.post('/links')
def add_links(data:LinksRequest,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    links=extract_links(data.text)[:settings.max_links_per_batch]
    added=0
    for value in links:
        if not db.scalar(select(Link.id).where(Link.user_id==user.id,Link.value==value)):
            db.add(Link(user_id=user.id,value=value)); added+=1
    db.commit(); return {'found':len(links),'added':added}

@router.delete('/links')
def clear_links(user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    db.execute(delete(Link).where(Link.user_id==user.id,Link.status!=LinkStatus.PROCESSING.value)); db.commit(); return {'ok':True}

@router.post('/jobs/start')
def start_job(user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    active=db.scalar(select(Job).where(Job.user_id==user.id,Job.status.in_([JobStatus.QUEUED.value,JobStatus.RUNNING.value])))
    if active: raise HTTPException(409,'توجد مهمة نشطة')
    account=db.scalar(select(TelegramAccount).where(TelegramAccount.user_id==user.id,TelegramAccount.is_active==True))
    if not account: raise HTTPException(400,'فعّل حساب Telegram أولاً')
    pending=db.scalar(select(func.count()).select_from(Link).where(Link.user_id==user.id,Link.status==LinkStatus.PENDING.value))
    if not pending: raise HTTPException(400,'لا توجد روابط معلقة')
    if not user.is_admin and user.balance<1: raise HTTPException(402,'الرصيد غير كافٍ')
    job=Job(user_id=user.id,account_id=account.id); db.add(job); db.commit(); return {'id':job.id,'status':job.status}

@router.post('/jobs/stop')
def stop_job(user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    jobs=db.scalars(select(Job).where(Job.user_id==user.id,Job.status.in_([JobStatus.QUEUED.value,JobStatus.RUNNING.value]))).all()
    for j in jobs: j.stop_requested=True
    db.commit(); return {'ok':True}

@router.put('/settings')
def update_settings(data:SettingsRequest,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    user.delay_seconds=data.delay_seconds; user.rest_minutes=data.rest_minutes; db.commit(); return user_payload(user)

@router.get('/admin/users')
def admin_users(admin:User=Depends(get_admin),db:Session=Depends(get_db)):
    users=db.scalars(select(User).order_by(User.id)).all(); return [user_payload(u) for u in users]

@router.post('/admin/charge')
def charge(data:ChargeRequest,admin:User=Depends(get_admin),db:Session=Depends(get_db)):
    user=db.get(User,data.user_id)
    if not user: raise HTTPException(404,'المستخدم غير موجود')
    user.balance+=data.amount; db.add(BalanceTransaction(user_id=user.id,amount=data.amount,kind='admin_charge',note=f'admin:{admin.id}')); db.commit(); return {'balance':user.balance}
