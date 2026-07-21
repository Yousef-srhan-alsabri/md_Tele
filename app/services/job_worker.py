import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import select, update
from app.database import SessionLocal
from app.models import BalanceTransaction, Job, JobStatus, Link, LinkStatus, TelegramAccount, User
from app.security import decrypt_session
from app.services.telegram_service import JoinKind, join_link

log = logging.getLogger(__name__)
_worker_task: asyncio.Task | None = None

async def worker_loop() -> None:
    while True:
        try:
            job_id = claim_next_job()
            if job_id:
                await process_job(job_id)
            else:
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Worker loop failed")
            await asyncio.sleep(3)

def claim_next_job() -> int | None:
    with SessionLocal.begin() as db:
        job = db.scalar(select(Job).where(Job.status == JobStatus.QUEUED.value).order_by(Job.id).with_for_update(skip_locked=True).limit(1))
        if not job:
            return None
        job.status = JobStatus.RUNNING.value
        job.started_at = datetime.now(timezone.utc)
        return job.id

async def process_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            return
        account = db.get(TelegramAccount, job.account_id)
        user = db.get(User, job.user_id)
        if not account or not user:
            job.status = JobStatus.FAILED.value
            job.last_error = "الحساب أو المستخدم غير موجود"
            db.commit()
            return
        session_string = decrypt_session(account.encrypted_session)
        delay_seconds = user.delay_seconds
        rest_minutes = user.rest_minutes

    success_since_rest = 0
    while True:
        with SessionLocal.begin() as db:
            job = db.get(Job, job_id)
            if not job or job.stop_requested:
                if job:
                    job.status = JobStatus.STOPPED.value
                    job.finished_at = datetime.now(timezone.utc)
                return
            link = db.scalar(select(Link).where(Link.user_id == job.user_id, Link.status == LinkStatus.PENDING.value).order_by(Link.id).with_for_update(skip_locked=True).limit(1))
            user = db.get(User, job.user_id)
            if not link:
                job.status = JobStatus.COMPLETED.value
                job.finished_at = datetime.now(timezone.utc)
                return
            if not user.is_admin and user.balance < 1:
                job.status = JobStatus.STOPPED.value
                job.last_error = "نفد الرصيد"
                job.finished_at = datetime.now(timezone.utc)
                return
            link.status = LinkStatus.PROCESSING.value
            link.attempts += 1
            link_id = link.id
            link_value = link.value

        result = await join_link(session_string, link_value)
        if result.kind == JoinKind.RETRY_WAIT:
            wait_for = min(max(result.retry_after or 60, 5), 86400)
            with SessionLocal.begin() as db:
                link = db.get(Link, link_id)
                link.status = LinkStatus.RETRY_WAIT.value
                link.last_message = result.message
            await asyncio.sleep(wait_for + 2)
            with SessionLocal.begin() as db:
                link = db.get(Link, link_id)
                if link and link.status == LinkStatus.RETRY_WAIT.value:
                    link.status = LinkStatus.PENDING.value
            continue

        chargeable = result.kind in {JoinKind.JOINED, JoinKind.REQUESTED}
        with SessionLocal.begin() as db:
            job = db.get(Job, job_id)
            link = db.get(Link, link_id)
            user = db.get(User, job.user_id)
            link.status = result.kind.value
            link.last_message = result.message
            job.processed += 1
            if result.kind in {JoinKind.JOINED, JoinKind.REQUESTED, JoinKind.ALREADY_MEMBER}:
                job.successful += 1
                success_since_rest += 1
            else:
                job.failed += 1
            if chargeable and not user.is_admin:
                updated = db.execute(update(User).where(User.id == user.id, User.balance >= 1).values(balance=User.balance - 1))
                if updated.rowcount == 1:
                    db.add(BalanceTransaction(user_id=user.id, amount=-1, kind="join", link_id=link.id, note=result.kind.value))
                else:
                    job.stop_requested = True
                    job.last_error = "نفد الرصيد أثناء التنفيذ"

        if success_since_rest >= 5 and rest_minutes > 0:
            await asyncio.sleep(rest_minutes * 60)
            success_since_rest = 0
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

def start_worker() -> None:
    global _worker_task
    if not _worker_task or _worker_task.done():
        _worker_task = asyncio.create_task(worker_loop(), name="job-worker")

async def stop_worker() -> None:
    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
