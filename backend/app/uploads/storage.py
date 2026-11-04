"""Private S3-compatible storage for customer photos (SeaweedFS in docker-compose locally, any S3 in production).

Keys: `incoming/<upload id>` is what the browser sends (presigned POST, size-limited by the storage itself, removed
after processing and expired by a lifecycle rule after a day); `photos/<upload id>.jpg` is the re-encoded photo. The
bucket is private: photos are only ever reached through short-lived signed links.

    uv run python -m app.uploads.storage setup   # create the bucket, block public access, expire incoming/ after 1 day,
                                                 # and let the web app (WEB_ORIGIN) post uploads to it (CORS)
"""

import sys
from typing import Protocol

from app.config import Settings


class StorageError(RuntimeError):
    pass


class Storage(Protocol):
    def presign_upload(self, key: str, max_bytes: int, ttl: int) -> dict: ...
    def presign_view(self, key: str, ttl: int) -> str: ...
    def size(self, key: str) -> int | None: ...
    def get(self, key: str) -> bytes: ...
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def delete(self, keys: list[str]) -> None: ...


class S3Storage:
    def __init__(self, settings: Settings):
        import boto3
        from botocore.config import Config

        if not settings.s3_access_key or not settings.s3_secret_key:
            raise StorageError("Set S3_ACCESS_KEY and S3_SECRET_KEY (see backend/.env.example)")
        common = {
            "aws_access_key_id": settings.s3_access_key,
            "aws_secret_access_key": settings.s3_secret_key,
            "region_name": settings.s3_region,
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 2}),
        }
        self.bucket = settings.s3_bucket
        self.web_origin = settings.web_origin
        self.client = boto3.client("s3", endpoint_url=settings.s3_endpoint_url, **common)
        # Links handed to browsers are signed for the address the browser uses.
        self.public = boto3.client(
            "s3", endpoint_url=settings.s3_public_endpoint_url or settings.s3_endpoint_url, **common
        )

    def _call(self, fn, **kwargs):
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            return fn(Bucket=self.bucket, **kwargs)
        except (BotoCoreError, ClientError) as e:
            raise StorageError(f"storage error: {type(e).__name__}") from None

    def presign_upload(self, key: str, max_bytes: int, ttl: int) -> dict:
        post = self.public.generate_presigned_post(
            self.bucket, key, Conditions=[["content-length-range", 1, max_bytes]], ExpiresIn=ttl
        )
        return {"url": post["url"], "fields": post["fields"]}

    def presign_view(self, key: str, ttl: int) -> str:
        return self.public.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key, "ResponseCacheControl": "private, no-store"},
            ExpiresIn=ttl,
        )

    def size(self, key: str) -> int | None:
        from botocore.exceptions import ClientError

        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"]
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise StorageError("storage error: head") from None

    def get(self, key: str) -> bytes:
        return self._call(self.client.get_object, Key=key)["Body"].read()

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._call(self.client.put_object, Key=key, Body=data, ContentType=content_type)

    def delete(self, keys: list[str]) -> None:
        for i in range(0, len(keys), 1000):
            batch = keys[i : i + 1000]
            out = self._call(self.client.delete_objects, Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True})
            if out.get("Errors"):
                raise StorageError(f"storage error: {len(out['Errors'])} objects not deleted")

    def setup(self) -> list[str]:
        """Create the bucket if needed; returns notes on optional settings the server does not support."""
        from botocore.exceptions import ClientError

        notes = []
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)
        try:
            self.client.put_bucket_lifecycle_configuration(
                Bucket=self.bucket,
                LifecycleConfiguration={
                    "Rules": [
                        {
                            "ID": "expire-incoming",
                            "Status": "Enabled",
                            "Filter": {"Prefix": "incoming/"},
                            "Expiration": {"Days": 1},
                        }
                    ]
                },
            )
        except ClientError:
            notes.append("lifecycle rules not supported: unfinished uploads under incoming/ are not expired")
        try:  # AWS S3; local S3-compatible servers keep buckets private and may not support this call
            self.client.put_public_access_block(
                Bucket=self.bucket,
                PublicAccessBlockConfiguration={
                    k: True
                    for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")
                },
            )
        except ClientError:
            notes.append("public access block not supported (the bucket has no public policy)")
        try:  # browsers post the presigned form straight to the bucket, from the web app only
            self.client.put_bucket_cors(Bucket=self.bucket, CORSConfiguration=cors_rules(self.web_origin))
            # Read it back: some servers (SeaweedFS 3.80) accept the call but keep nothing.
            self.client.get_bucket_cors(Bucket=self.bucket)
        except ClientError:
            notes.append(
                f"bucket CORS not supported: allow POST from {self.web_origin} in the storage's own settings "
                "(SeaweedFS: -s3.allowedOrigins, set from WEB_ORIGIN in docker-compose)"
            )
        return notes


def cors_rules(web_origin: str) -> dict:
    """Bucket CORS: the web app (WEB_ORIGIN) may POST the presigned upload form and GET signed links. Nothing else."""
    return {
        "CORSRules": [
            {
                "ID": "web-app-uploads",
                "AllowedOrigins": [web_origin.rstrip("/")],
                "AllowedMethods": ["POST", "GET", "HEAD"],
                "AllowedHeaders": ["*"],
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 3600,
            }
        ]
    }


class MemoryStorage:
    """In-process storage for tests (and a way to run the API without MinIO)."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.fail = False

    def _check(self) -> None:
        if self.fail:
            raise StorageError("storage error: unreachable")

    def presign_upload(self, key: str, max_bytes: int, ttl: int) -> dict:
        return {"url": "https://storage.test/upload", "fields": {"key": key, "policy": f"max={max_bytes};ttl={ttl}"}}

    def presign_view(self, key: str, ttl: int) -> str:
        return f"https://storage.test/{key}?expires={ttl}&signature=test"

    def size(self, key: str) -> int | None:
        self._check()
        return len(self.objects[key][0]) if key in self.objects else None

    def get(self, key: str) -> bytes:
        self._check()
        return self.objects[key][0]

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._check()
        self.objects[key] = (data, content_type)

    def delete(self, keys: list[str]) -> None:
        self._check()
        for k in keys:
            self.objects.pop(k, None)


def make_storage(settings: Settings) -> Storage:
    return S3Storage(settings)


if __name__ == "__main__":
    from app.config import get_settings

    if sys.argv[1:] != ["setup"]:
        sys.exit("usage: python -m app.uploads.storage setup")
    s = get_settings()
    notes = S3Storage(s).setup()
    print(f"Bucket {s.s3_bucket} ready at {s.s3_endpoint_url} (private)")
    for n in notes:
        print(f"  note: {n}")
