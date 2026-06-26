"""Post management endpoints — create, schedule, publish, retry."""

import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.database import get_db
from db.models import PostStatus
from services import posts as post_service
from services import zernio
from services.accounts import get_account

router = APIRouter(prefix="/api/posts", tags=["posts"])

UPLOAD_DIR = settings.data_dir / "uploads"


@router.get("/upload-url")
async def get_upload_url(filename: str = "video.mp4", content_type: str = "video/mp4"):
    """Get a Zernio presigned URL for uploading media.

    Returns { uploadUrl, publicUrl }. PUT your file to uploadUrl,
    then use publicUrl in the post's media_url field.
    """
    try:
        data = await zernio.get_presigned_url(filename=filename, content_type=content_type)
        if isinstance(data, dict):
            return data
        return {"uploadUrl": str(data), "publicUrl": str(data)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to get upload URL: {e}")


# --- Response Models ---


class PostResponse(BaseModel):
    id: int
    account_id: int
    zernio_post_id: str | None
    status: PostStatus
    caption: str | None
    media_path: str | None
    tiktok_settings: dict | None
    scheduled_at: datetime | None
    published_at: datetime | None
    failure_reason: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PostListResponse(BaseModel):
    posts: list[PostResponse]
    total: int


class CreatePostRequest(BaseModel):
    account_id: int
    caption: str | None = None
    tiktok_settings: dict | None = None
    scheduled_at: datetime | None = None


class UpdatePostRequest(BaseModel):
    caption: str | None = None
    tiktok_settings: dict | None = None
    scheduled_at: datetime | None = None


class ScheduleRequest(BaseModel):
    scheduled_at: datetime


class AccountCaption(BaseModel):
    account_id: int
    caption: str


class MultiPostRequest(BaseModel):
    """Post same video to multiple accounts with different captions."""
    accounts: list[AccountCaption]
    media_url: str | None = None
    tiktok_settings: dict | None = None
    scheduled_at: datetime | None = None
    publish_now: bool = False


class MultiPostResponse(BaseModel):
    zernio_post_id: str | None
    status: str
    accounts_count: int


# --- Routes ---


@router.get("", response_model=PostListResponse)
async def list_posts(
    account_id: int | None = None,
    status: PostStatus | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    posts, total = await post_service.list_posts(db, account_id, status, limit, offset)
    return PostListResponse(
        posts=[PostResponse.model_validate(p) for p in posts],
        total=total,
    )


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(post_id: int, db: AsyncSession = Depends(get_db)):
    post = await post_service.get_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return PostResponse.model_validate(post)


@router.post("", response_model=PostResponse, status_code=201)
async def create_post(body: CreatePostRequest, db: AsyncSession = Depends(get_db)):
    try:
        post = await post_service.create_draft(
            db,
            account_id=body.account_id,
            caption=body.caption,
            tiktok_settings=body.tiktok_settings,
            scheduled_at=body.scheduled_at,
        )
        return PostResponse.model_validate(post)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{post_id}", response_model=PostResponse)
async def update_post(
    post_id: int, body: UpdatePostRequest, db: AsyncSession = Depends(get_db)
):
    try:
        post = await post_service.update_post(
            db,
            post_id,
            caption=body.caption,
            tiktok_settings=body.tiktok_settings,
            scheduled_at=body.scheduled_at,
        )
        return PostResponse.model_validate(post)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{post_id}/upload", response_model=PostResponse)
async def upload_video(
    post_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a video file and attach it to a draft post."""
    post = await post_service.get_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.status not in (PostStatus.draft, PostStatus.ready):
        raise HTTPException(status_code=400, detail="Can only upload to draft/ready posts")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{post_id}_{file.filename}"
    file_path = UPLOAD_DIR / filename

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    post = await post_service.update_post(db, post_id, media_path=str(file_path))
    return PostResponse.model_validate(post)


@router.post("/{post_id}/ready", response_model=PostResponse)
async def mark_ready(post_id: int, db: AsyncSession = Depends(get_db)):
    """Mark a draft as ready for approval."""
    try:
        post = await post_service.mark_ready(db, post_id)
        return PostResponse.model_validate(post)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{post_id}/schedule", response_model=PostResponse)
async def schedule_post(
    post_id: int, body: ScheduleRequest, db: AsyncSession = Depends(get_db)
):
    """Approve and schedule a post."""
    try:
        post = await post_service.schedule_post(db, post_id, body.scheduled_at)
        return PostResponse.model_validate(post)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{post_id}/publish", response_model=PostResponse)
async def publish_post(post_id: int, db: AsyncSession = Depends(get_db)):
    """Immediately publish a ready/scheduled post."""
    try:
        post = await post_service.publish_now(db, post_id)
        return PostResponse.model_validate(post)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{post_id}/retry", response_model=PostResponse)
async def retry_post(post_id: int, db: AsyncSession = Depends(get_db)):
    """Retry a failed post."""
    try:
        post = await post_service.retry_failed(db, post_id)
        return PostResponse.model_validate(post)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{post_id}")
async def delete_post(post_id: int, db: AsyncSession = Depends(get_db)):
    try:
        success = await post_service.delete_post(db, post_id)
        if not success:
            raise HTTPException(status_code=404, detail="Post not found")
        return {"detail": "Post deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Multi-Account Post ---


@router.post("/multi", response_model=MultiPostResponse)
async def create_multi_account_post(
    body: MultiPostRequest, db: AsyncSession = Depends(get_db)
):
    """Post same video to multiple TikTok accounts with different captions.

    One Zernio API call — same media, different caption per account.
    """
    if len(body.accounts) < 1:
        raise HTTPException(status_code=400, detail="Need at least 1 account")

    # Resolve local account IDs to Zernio IDs
    account_captions = []
    for entry in body.accounts:
        account = await get_account(db, entry.account_id)
        if not account:
            raise HTTPException(status_code=404, detail=f"Account {entry.account_id} not found")
        account_captions.append({
            "account_id": account.zernio_id,
            "caption": entry.caption,
        })

    media = None
    if body.media_url:
        media = [{"type": "video", "url": body.media_url}]

    tiktok_settings = body.tiktok_settings or {
        "privacy_level": "PUBLIC_TO_EVERYONE",
        "allow_comment": True,
        "allow_duet": True,
        "allow_stitch": True,
    }

    try:
        result = await zernio.create_multi_account_post(
            account_captions=account_captions,
            tiktok_settings=tiktok_settings,
            media=media,
            scheduled_for=body.scheduled_at.isoformat() if body.scheduled_at else None,
            publish_now=body.publish_now,
        )

        zernio_id = result.get("_id") if isinstance(result, dict) else getattr(result, "field_id", None)

        # Create local Post records for tracking
        for entry in body.accounts:
            await post_service.create_draft(
                db,
                account_id=entry.account_id,
                caption=entry.caption,
                tiktok_settings=tiktok_settings,
            )
            # Update the last created post with the zernio ID and status
            posts, _ = await post_service.list_posts(db, account_id=entry.account_id, limit=1)
            if posts:
                posts[0].zernio_post_id = str(zernio_id) if zernio_id else None
                posts[0].status = PostStatus.published if body.publish_now else PostStatus.scheduled
                if body.publish_now:
                    posts[0].published_at = datetime.utcnow()
                elif body.scheduled_at:
                    posts[0].scheduled_at = body.scheduled_at
                await db.commit()

        return MultiPostResponse(
            zernio_post_id=str(zernio_id) if zernio_id else None,
            status="published" if body.publish_now else "scheduled",
            accounts_count=len(body.accounts),
        )

    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Zernio post failed: {e}")
