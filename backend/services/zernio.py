"""Zernio integration using the official Python SDK.

SDK: git+https://github.com/zernio-dev/zernio-python.git (zernio-sdk)
Docs: https://docs.zernio.com

Accounts are already connected on Zernio's dashboard.
This service reads data and publishes posts via the SDK.
"""

import logging
from zernio import Zernio, Platform, TikTokPrivacyLevel

from config import settings

logger = logging.getLogger(__name__)


def _to_dict(obj) -> dict:
    """Convert SDK response object to dict recursively."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return {}


def get_client() -> Zernio:
    """Get a Zernio SDK client instance."""
    if not settings.zernio_api_key:
        raise RuntimeError("ZERNIO_API_KEY not set in .env")
    return Zernio(api_key=settings.zernio_api_key)


# --- Accounts ---


async def list_accounts() -> list[dict]:
    """List all connected accounts, filtered to TikTok only."""
    client = get_client()
    result = await client.accounts.alist()

    # SDK returns an AccountsListResponse object with .accounts attribute
    if hasattr(result, "accounts"):
        accounts_list = result.accounts
    elif isinstance(result, dict):
        accounts_list = result.get("data", result.get("accounts", []))
    elif isinstance(result, list):
        accounts_list = result
    else:
        accounts_list = []

    # Convert SDK objects to dicts, filter to TikTok
    tiktok = []
    for a in accounts_list:
        if hasattr(a, "platform"):
            platform = a.platform.value if hasattr(a.platform, "value") else str(a.platform)
        elif isinstance(a, dict):
            platform = a.get("platform", "")
        else:
            continue

        if platform == "tiktok":
            if hasattr(a, "__dict__"):
                d = {}
                d["_id"] = getattr(a, "field_id", getattr(a, "id", ""))
                d["platform"] = platform
                d["username"] = getattr(a, "username", "")
                d["displayName"] = getattr(a, "display_name", getattr(a, "displayName", ""))
                d["avatarUrl"] = getattr(a, "profile_picture", getattr(a, "profilePicture", ""))
                d["profileUrl"] = getattr(a, "profile_url", getattr(a, "profileUrl", ""))
                d["followersCount"] = getattr(a, "followers_count", getattr(a, "followersCount", 0))
                profile = getattr(a, "profile_id", getattr(a, "profileId", None))
                if profile and hasattr(profile, "field_id"):
                    d["profileId"] = profile.field_id
                elif isinstance(profile, str):
                    d["profileId"] = profile
                tiktok.append(d)
            else:
                tiktok.append(a)

    return tiktok


async def get_account_health(account_id: str) -> dict:
    """GET /v1/accounts/{id}/health"""
    client = get_client()
    return await client.accounts.aget_account_health(account_id)


async def get_all_accounts_health() -> dict:
    """GET /v1/accounts/health"""
    client = get_client()
    return await client.accounts.aget_all_accounts_health()


async def get_follower_stats(account_id: str) -> dict:
    """GET /v1/accounts/{id}/follower-stats (requires analytics add-on)"""
    client = get_client()
    result = await client.accounts.aget_follower_stats(account_ids=[account_id])
    if hasattr(result, "__dict__"):
        return _to_dict(result)
    return result if isinstance(result, dict) else {}


async def get_tiktok_creator_info(account_id: str, media_type: str = "video") -> dict:
    """GET /v1/accounts/{id}/tiktok-creator-info?mediaType={video|photo}"""
    client = get_client()
    return await client.accounts.aget_tik_tok_creator_info(
        account_id, media_type=media_type
    )


# --- Posts ---


async def create_post(
    content: str,
    account_id: str,
    tiktok_settings: dict,
    media: list[dict] | None = None,
    scheduled_for: str | None = None,
    publish_now: bool = False,
) -> dict:
    """Create a TikTok post for a single account.

    POST /v1/posts
    """
    client = get_client()

    ts = {
        "content_preview_confirmed": True,
        "express_consent_given": True,
        **tiktok_settings,
    }

    kwargs: dict = {
        "content": content,
        "platforms": [{"platform": "tiktok", "accountId": account_id}],
        "tiktok_settings": ts,
        "publish_now": publish_now,
    }

    if media:
        kwargs["media_items"] = media
    if scheduled_for:
        kwargs["scheduled_for"] = scheduled_for

    return await client.posts.acreate_post(**kwargs)


async def create_multi_account_post(
    account_captions: list[dict],
    tiktok_settings: dict,
    media: list[dict] | None = None,
    scheduled_for: str | None = None,
    publish_now: bool = False,
) -> dict:
    """Post same video to multiple accounts with different captions.

    POST /v1/posts

    account_captions: [{"account_id": "xxx", "caption": "custom caption"}, ...]
    Uses Zernio's platforms[] array with per-account customContent.
    """
    client = get_client()

    # First caption becomes the default content
    default_content = account_captions[0]["caption"] if account_captions else ""

    platforms = []
    for entry in account_captions:
        platform_entry: dict = {
            "platform": "tiktok",
            "accountId": entry["account_id"],
        }
        # If caption differs from default, set as customContent
        if entry["caption"] != default_content:
            platform_entry["customContent"] = entry["caption"]
        platforms.append(platform_entry)

    ts = {
        "content_preview_confirmed": True,
        "express_consent_given": True,
        **tiktok_settings,
    }

    kwargs: dict = {
        "content": default_content,
        "platforms": platforms,
        "tiktok_settings": ts,
        "publish_now": publish_now,
    }

    if media:
        kwargs["media_items"] = media
    if scheduled_for:
        kwargs["scheduled_for"] = scheduled_for

    return await client.posts.acreate_post(**kwargs)


async def get_post(post_id: str) -> dict:
    """GET /v1/posts/{id}"""
    client = get_client()
    return await client.posts.aget_post(post_id)


async def list_posts(**params) -> dict:
    """GET /v1/posts"""
    client = get_client()
    return await client.posts.alist_posts(**params)


async def update_post(post_id: str, **data) -> dict:
    """PATCH /v1/posts/{id}"""
    client = get_client()
    return await client.posts.aupdate_post(post_id, **data)


async def delete_post(post_id: str) -> dict:
    """DELETE /v1/posts/{id}"""
    client = get_client()
    return await client.posts.adelete_post(post_id)


async def retry_post(post_id: str) -> dict:
    """POST /v1/posts/{id}/retry"""
    client = get_client()
    return await client.posts.aretry_post(post_id)


# --- Media ---


async def upload_media(file_path: str) -> str:
    """Upload a file via presigned URL. Returns the public URL for use in posts."""
    client = get_client()
    result = await client.media.aupload(file_path)
    if isinstance(result, dict):
        return result.get("publicUrl", result.get("url", ""))
    return str(result)


async def get_presigned_url(filename: str = "video.mp4", content_type: str = "video/mp4") -> dict:
    """GET /v1/media/presigned-url"""
    client = get_client()
    result = await client.media.aget_media_presigned_url(filename, content_type)
    if isinstance(result, dict):
        return result
    return _to_dict(result)


# --- Analytics ---


async def get_analytics(**params) -> dict:
    """GET /v1/analytics (requires analytics add-on)"""
    client = get_client()
    result = await client.analytics.aget_analytics(**params)
    if isinstance(result, dict):
        return result
    return _to_dict(result)


async def get_best_time_to_post(**params) -> dict:
    """GET /v1/analytics/best-time"""
    client = get_client()
    result = await client.analytics.aget_best_time_to_post(**params)
    return result if isinstance(result, dict) else _to_dict(result)


async def get_content_decay(**params) -> dict:
    """GET /v1/analytics/content-decay"""
    client = get_client()
    result = await client.analytics.aget_content_decay(**params)
    return result if isinstance(result, dict) else _to_dict(result)


async def get_daily_metrics(**params) -> dict:
    """GET /v1/analytics/daily-metrics"""
    client = get_client()
    result = await client.analytics.aget_daily_metrics(**params)
    return result if isinstance(result, dict) else _to_dict(result)


async def get_posting_frequency(**params) -> dict:
    """GET /v1/analytics/posting-frequency"""
    client = get_client()
    result = await client.analytics.aget_posting_frequency(**params)
    return result if isinstance(result, dict) else _to_dict(result)


# --- Validation ---


async def validate_media(media_urls: list[str]) -> dict:
    """POST /v1/validate/media"""
    client = get_client()
    return await client.validate.avalidate_media(media=media_urls)


async def validate_post(post_data: dict) -> dict:
    """POST /v1/validate/post — dry-run validation"""
    client = get_client()
    return await client.validate.avalidate_post(**post_data)


# --- Profiles ---


async def list_profiles() -> list[dict]:
    """GET /v1/profiles"""
    client = get_client()
    return await client.profiles.alist_profiles()
