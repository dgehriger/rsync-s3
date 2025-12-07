"""
FastAPI main application with HTTP API endpoints
"""

import logging
import mimetypes
import secrets
from contextlib import asynccontextmanager
from pathlib import PurePosixPath
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import (
    Settings,
    get_settings,
    get_remote_config,
    load_remote_config_from_sftp,
)
from .s3_client import S3Client, get_s3_client
from .sftp_client import SFTPClient, get_sftp_client
from .version_mapper import VersionMapper, get_version_mapper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Rsync.net S3 Browser")
    yield
    logger.info("Shutting down Rsync.net S3 Browser")


app = FastAPI(
    title="Rsync.net S3 Gateway Browser",
    description="Snapshot-aware browser for rsync.net S3 storage",
    version="1.1.0",
    lifespan=lifespan,
)

# Security
security = HTTPBasic(auto_error=False)


def get_current_user(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
    settings: Settings = Depends(get_settings),
) -> str:
    """
    Verify authentication based on auth_mode setting.
    
    Modes:
    - "basic": HTTP Basic Auth (default)
    - "cloudflare": Trust Cloudflare Access headers (Cf-Access-Authenticated-User-Email)
    - "none": No authentication (not recommended)
    """
    if settings.auth_mode == "none":
        return "anonymous"
    
    if settings.auth_mode == "cloudflare":
        # Cloudflare Access sets these headers after authentication
        cf_email = request.headers.get("Cf-Access-Authenticated-User-Email")
        if cf_email:
            return cf_email
        # Fallback: check if request came through Cloudflare
        cf_connecting_ip = request.headers.get("Cf-Connecting-Ip")
        if not cf_connecting_ip:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Request must come through Cloudflare Access",
            )
        return "cloudflare-user"
    
    # Default: basic auth
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    correct_username = secrets.compare_digest(
        credentials.username.encode("utf8"),
        settings.auth_username.encode("utf8"),
    )
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf8"),
        settings.auth_password.encode("utf8"),
    )
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# Templates
templates = Jinja2Templates(directory="app/templates")


# Utility functions
def format_size(size: int) -> str:
    """Format byte size to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def build_breadcrumbs(bucket: str, prefix: str = "") -> list[dict]:
    """Build breadcrumb navigation items."""
    crumbs = [{"name": "Buckets", "url": "/buckets"}]
    crumbs.append({"name": bucket, "url": f"/b/{bucket}"})

    if prefix:
        parts = prefix.rstrip("/").split("/")
        current_path = ""
        for part in parts:
            current_path += part + "/"
            crumbs.append(
                {"name": part, "url": f"/b/{bucket}?prefix={current_path}"}
            )

    return crumbs


# Add template globals
templates.env.globals["format_size"] = format_size


# API Endpoints
@app.get("/", response_class=HTMLResponse)
async def root(request: Request, username: str = Depends(get_current_user)):
    """Redirect to buckets page."""
    return templates.TemplateResponse(
        "redirect.html",
        {"request": request, "redirect_url": "/buckets"},
    )


@app.get("/buckets", response_class=HTMLResponse)
async def list_buckets_page(
    request: Request,
    username: str = Depends(get_current_user),
    s3_client: S3Client = Depends(get_s3_client),
    sftp_client: SFTPClient = Depends(get_sftp_client),
):
    """List all buckets page."""
    try:
        # Load remote config if not already loaded
        remote_config = await load_remote_config_from_sftp(sftp_client)
        
        buckets = await s3_client.list_buckets()
        
        # Filter buckets based on remote configuration
        buckets = remote_config.filter_buckets(buckets)
        
        logger.info(f"Listed {len(buckets)} buckets (after filtering)")
        return templates.TemplateResponse(
            "buckets.html",
            {
                "request": request,
                "buckets": buckets,
                "username": username,
            },
        )
    except Exception as e:
        logger.error(f"Error listing buckets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/b/{bucket}", response_class=HTMLResponse)
async def list_objects_page(
    request: Request,
    bucket: str,
    prefix: str = Query("", description="Object prefix"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(None, description="Items per page (20, 50, or 100)"),
    username: str = Depends(get_current_user),
    s3_client: S3Client = Depends(get_s3_client),
    settings: Settings = Depends(get_settings),
):
    """List objects in a bucket page with pagination."""
    try:
        # Validate and set per_page
        valid_page_sizes = settings.page_size_options
        if per_page is None or per_page not in valid_page_sizes:
            per_page = settings.default_page_size
        
        result = await s3_client.list_objects(bucket, prefix)
        breadcrumbs = build_breadcrumbs(bucket, prefix)
        
        # Combine folders and files for pagination
        all_items = result["folders"] + result["files"]
        total_items = len(all_items)
        total_pages = max(1, (total_items + per_page - 1) // per_page)
        
        # Ensure page is within bounds
        page = min(page, total_pages)
        
        # Paginate
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_items = all_items[start_idx:end_idx]
        
        # Split back into folders and files
        paginated_folders = [item for item in paginated_items if item.get("type") == "folder"]
        paginated_files = [item for item in paginated_items if item.get("type") == "file"]

        return templates.TemplateResponse(
            "objects.html",
            {
                "request": request,
                "bucket": bucket,
                "prefix": prefix,
                "folders": paginated_folders,
                "files": paginated_files,
                "breadcrumbs": breadcrumbs,
                "username": username,
                # Pagination context
                "page": page,
                "per_page": per_page,
                "total_items": total_items,
                "total_pages": total_pages,
                "page_size_options": valid_page_sizes,
                "total_folders": len(result["folders"]),
                "total_files": len(result["files"]),
            },
        )
    except Exception as e:
        logger.error(f"Error listing objects in {bucket}/{prefix}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/b/{bucket}/o/{path:path}/download")
async def download_object(
    bucket: str,
    path: str,
    version: str = Query("current", description="Version ID or 'current'"),
    snapshot: Optional[str] = Query(None, description="Snapshot name for download"),
    username: str = Depends(get_current_user),
    s3_client: S3Client = Depends(get_s3_client),
    sftp_client: SFTPClient = Depends(get_sftp_client),
):
    """Download an object (current or specific version)."""
    try:
        filename = PurePosixPath(path).name
        content_type, _ = mimetypes.guess_type(filename)
        content_type = content_type or "application/octet-stream"

        # Determine if we're downloading current or a snapshot
        # Use snapshot param if provided, otherwise check version param
        is_current = version == "current" or version.endswith("(current)")
        snapshot_name = snapshot if snapshot else (None if is_current else version)

        if is_current or not snapshot_name:
            # Download entire file from S3
            logger.info(f"Downloading current version: {bucket}/{path}")
            try:
                content = await s3_client.get_object_bytes(bucket, path)
            except Exception as e:
                logger.error(f"S3 download error: {e}")
                raise HTTPException(status_code=404, detail="Object not found")
            
            return Response(
                content=content,
                media_type=content_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                },
            )
        else:
            # Download from snapshot via SFTP
            logger.info(
                f"Downloading snapshot version: {bucket}/{path} @ {snapshot_name}"
            )
            try:
                content = await sftp_client.get_snapshot_file_bytes(
                    snapshot_name, bucket, path
                )
            except Exception as e:
                logger.error(f"SFTP download error: {e}")
                raise HTTPException(status_code=404, detail="Version not found")
            
            return Response(
                content=content,
                media_type=content_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading {bucket}/{path} version {version}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/b/{bucket}/o/{path:path}", response_class=HTMLResponse)
async def object_detail_page(
    request: Request,
    bucket: str,
    path: str,
    username: str = Depends(get_current_user),
    s3_client: S3Client = Depends(get_s3_client),
    version_mapper: VersionMapper = Depends(get_version_mapper),
    settings: Settings = Depends(get_settings),
):
    """Object detail page with version history."""
    try:
        # Get current object metadata
        metadata = await s3_client.head_object(bucket, path)
        if not metadata:
            raise HTTPException(status_code=404, detail="Object not found")

        # Get all versions
        versions = await version_mapper.list_object_versions(bucket, path)

        # Build breadcrumbs
        prefix = str(PurePosixPath(path).parent)
        if prefix == ".":
            prefix = ""
        else:
            prefix += "/"
        breadcrumbs = build_breadcrumbs(bucket, prefix)
        breadcrumbs.append({"name": PurePosixPath(path).name, "url": None})

        return templates.TemplateResponse(
            "object_detail.html",
            {
                "request": request,
                "bucket": bucket,
                "key": path,
                "metadata": metadata,
                "versions": [v.to_dict() for v in versions],
                "breadcrumbs": breadcrumbs,
                "username": username,
                "s3_public_endpoint": settings.s3_public_endpoint,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting object detail {bucket}/{path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# JSON API Endpoints
@app.get("/api/buckets")
async def api_list_buckets(
    username: str = Depends(get_current_user),
    s3_client: S3Client = Depends(get_s3_client),
    sftp_client: SFTPClient = Depends(get_sftp_client),
):
    """JSON API: List all buckets."""
    try:
        # Load remote config if not already loaded
        remote_config = await load_remote_config_from_sftp(sftp_client)
        
        buckets = await s3_client.list_buckets()
        
        # Filter buckets based on remote configuration
        buckets = remote_config.filter_buckets(buckets)
        
        return {"buckets": buckets}
    except Exception as e:
        logger.error(f"API Error listing buckets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/b/{bucket}")
async def api_list_objects(
    bucket: str,
    prefix: str = Query("", description="Object prefix"),
    username: str = Depends(get_current_user),
    s3_client: S3Client = Depends(get_s3_client),
):
    """JSON API: List objects in a bucket."""
    try:
        result = await s3_client.list_objects(bucket, prefix)
        return result
    except Exception as e:
        logger.error(f"API Error listing objects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/b/{bucket}/o/{path:path}/versions")
async def api_object_versions(
    bucket: str,
    path: str,
    username: str = Depends(get_current_user),
    version_mapper: VersionMapper = Depends(get_version_mapper),
):
    """JSON API: List object versions."""
    try:
        versions = await version_mapper.list_object_versions(bucket, path)
        return {"versions": [v.to_dict() for v in versions]}
    except Exception as e:
        logger.error(f"API Error listing versions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/b/{bucket}/o/{path:path}")
async def api_object_detail(
    bucket: str,
    path: str,
    username: str = Depends(get_current_user),
    s3_client: S3Client = Depends(get_s3_client),
):
    """JSON API: Get object metadata."""
    try:
        metadata = await s3_client.head_object(bucket, path)
        if not metadata:
            raise HTTPException(status_code=404, detail="Object not found")
        return metadata
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API Error getting object: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/snapshots")
async def api_list_snapshots(
    username: str = Depends(get_current_user),
    sftp_client: SFTPClient = Depends(get_sftp_client),
):
    """JSON API: List available ZFS snapshots."""
    try:
        snapshots = await sftp_client.list_snapshots()
        return {
            "snapshots": [
                {
                    "name": s.name,
                    "timestamp": s.timestamp.isoformat() if s.timestamp else None,
                }
                for s in snapshots
            ]
        }
    except Exception as e:
        logger.error(f"API Error listing snapshots: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
