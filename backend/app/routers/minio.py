"""MinIO storage browser API — browse buckets and objects."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.managers.minio_manager import MinioManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/minio", tags=["minio"])
minio_mgr = MinioManager()


class BucketRequest(BaseModel):
    bucket: str


class ListObjectsRequest(BaseModel):
    bucket: str
    prefix: str = ''


class ObjectMetadataRequest(BaseModel):
    bucket: str
    key: str


@router.get("/buckets")
def list_buckets():
    """List all MinIO buckets."""
    try:
        return minio_mgr.list_buckets()
    except Exception as e:
        logger.exception("MinIO list buckets failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/objects")
def list_objects(body: ListObjectsRequest):
    """List objects and folders in a bucket prefix."""
    try:
        return minio_mgr.list_objects(body.bucket, body.prefix)
    except Exception as e:
        logger.exception("MinIO list objects failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/object-metadata")
def object_metadata(body: ObjectMetadataRequest):
    """Get metadata for a single object."""
    try:
        return minio_mgr.object_metadata(body.bucket, body.key)
    except Exception as e:
        logger.exception("MinIO object metadata failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/bucket-stats")
def bucket_stats(body: BucketRequest):
    """Get total object count and size for a bucket."""
    try:
        return minio_mgr.bucket_stats(body.bucket)
    except Exception as e:
        logger.exception("MinIO bucket stats failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
