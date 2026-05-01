"""MinIO storage browser — list buckets, objects, and metadata.

Uses botocore (already available via DVC[s3]) to talk to the MinIO S3 API.
"""

import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

MINIO_ENDPOINT = os.environ.get('DVC_MINIO_ENDPOINT', 'http://noted-minio:9000')
MINIO_ACCESS_KEY = os.environ.get('DVC_MINIO_ACCESS_KEY', 'admin')
MINIO_SECRET_KEY = os.environ.get('DVC_MINIO_SECRET_KEY', 'password')


class MinioManager:
    """Browse MinIO buckets and objects via S3 API."""

    def __init__(self):
        self._client = None

    def _s3(self):
        """Lazy-init botocore S3 client."""
        if self._client is None:
            import botocore.session
            session = botocore.session.get_session()
            self._client = session.create_client(
                's3',
                endpoint_url=MINIO_ENDPOINT,
                aws_access_key_id=MINIO_ACCESS_KEY,
                aws_secret_access_key=MINIO_SECRET_KEY,
            )
        return self._client

    def list_buckets(self) -> dict:
        """Return all buckets with creation dates."""
        resp = self._s3().list_buckets()
        buckets = []
        for b in resp.get('Buckets', []):
            created = b.get('CreationDate')
            buckets.append({
                'name': b['Name'],
                'created': created.isoformat() if isinstance(created, datetime) else str(created or ''),
            })
        return {'buckets': buckets}

    def list_objects(self, bucket: str, prefix: str = '', delimiter: str = '/') -> dict:
        """List objects and common prefixes (folders) in a bucket.

        Uses delimiter='/' for folder-style browsing.
        Returns up to 1000 items per call (S3 default page).
        """
        params = {'Bucket': bucket, 'MaxKeys': 1000}
        if prefix:
            params['Prefix'] = prefix
        if delimiter:
            params['Delimiter'] = delimiter

        resp = self._s3().list_objects_v2(**params)

        # Common prefixes (virtual folders)
        folders = []
        for cp in resp.get('CommonPrefixes', []):
            p = cp['Prefix']
            # Strip trailing slash for display name, keep full prefix for navigation
            name = p.rstrip('/').rsplit('/', 1)[-1] if '/' in p.rstrip('/') else p.rstrip('/')
            folders.append({'prefix': p, 'name': name})

        # Objects (files)
        objects = []
        for obj in resp.get('Contents', []):
            key = obj['Key']
            # Skip the prefix itself (S3 sometimes returns the folder key)
            if key == prefix:
                continue
            name = key.rsplit('/', 1)[-1] if '/' in key else key
            modified = obj.get('LastModified')
            objects.append({
                'key': key,
                'name': name,
                'size': obj.get('Size', 0),
                'modified': modified.isoformat() if isinstance(modified, datetime) else str(modified or ''),
            })

        return {
            'bucket': bucket,
            'prefix': prefix,
            'folders': folders,
            'objects': objects,
            'truncated': resp.get('IsTruncated', False),
        }

    def object_metadata(self, bucket: str, key: str) -> dict:
        """Get metadata for a single object (HEAD request)."""
        resp = self._s3().head_object(Bucket=bucket, Key=key)
        modified = resp.get('LastModified')
        return {
            'bucket': bucket,
            'key': key,
            'size': resp.get('ContentLength', 0),
            'content_type': resp.get('ContentType', ''),
            'modified': modified.isoformat() if isinstance(modified, datetime) else str(modified or ''),
            'etag': (resp.get('ETag') or '').strip('"'),
            'metadata': dict(resp.get('Metadata', {})),
        }

    def bucket_stats(self, bucket: str) -> dict:
        """Get total object count and size for a bucket."""
        paginator_params = {'Bucket': bucket}
        total_size = 0
        total_count = 0
        continuation = None

        while True:
            params = dict(paginator_params, MaxKeys=1000)
            if continuation:
                params['ContinuationToken'] = continuation
            resp = self._s3().list_objects_v2(**params)
            for obj in resp.get('Contents', []):
                total_count += 1
                total_size += obj.get('Size', 0)
            if not resp.get('IsTruncated'):
                break
            continuation = resp.get('NextContinuationToken')

        return {
            'bucket': bucket,
            'total_objects': total_count,
            'total_size': total_size,
        }

