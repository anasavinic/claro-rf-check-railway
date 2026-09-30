"""S3/MinIO media storage with browser-reachable signed URLs.

django-storages skips signing when ``custom_domain`` is set. Private MinIO/OBS
buckets then return 403 for those unsigned URLs.

This backend keeps the Docker-internal ``endpoint_url`` for API I/O and signs
GET URLs against an optional public endpoint (host the browser can reach).
"""

from __future__ import annotations

from urllib.parse import urlparse

import boto3
from botocore.client import Config
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage
from storages.utils import clean_name


def public_endpoint_from_settings() -> str | None:
    """Browser-facing S3 API base, e.g. http://localhost:9120 (no bucket path)."""
    explicit = (getattr(settings, "OBS_PUBLIC_ENDPOINT", None) or "").strip()
    if explicit:
        return explicit.rstrip("/")

    custom = (getattr(settings, "OBS_CUSTOM_DOMAIN", None) or "").strip()
    if not custom:
        return None

    # OBS_CUSTOM_DOMAIN may be "localhost:9120/claro-rf-check" (host + bucket path).
    host = custom.split("/", 1)[0].strip()
    if not host:
        return None

    proto = (getattr(settings, "OBS_URL_PROTOCOL", None) or "").strip()
    if not proto:
        proto = "http:" if "localhost" in host or host.startswith("127.") else "https:"
    return f"{proto.rstrip(':')}://{host}"


class OBSMediaStorage(S3Boto3Storage):
    """Private-bucket storage that emits signed URLs on the public endpoint."""

    def __init__(self, **kwargs):
        # Never pass custom_domain into the parent — it disables querystring auth.
        kwargs.pop("custom_domain", None)
        self.public_endpoint_url = kwargs.pop("public_endpoint_url", None) or public_endpoint_from_settings()
        super().__init__(**kwargs)

    def _signing_client(self):
        endpoint = self.public_endpoint_url or self.endpoint_url
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_name or "us-east-1",
            config=Config(
                signature_version=self.signature_version or "s3v4",
                s3={"addressing_style": self.addressing_style or "virtual"},
            ),
        )

    def url(self, name, parameters=None, expire=None, http_method=None):
        name = self._normalize_name(clean_name(name))
        params = parameters.copy() if parameters else {}
        if expire is None:
            expire = self.querystring_expire

        if not self.querystring_auth:
            public = self.public_endpoint_url
            if public:
                parsed = urlparse(public)
                path = f"/{self.bucket_name}/{name}".replace("//", "/")
                return f"{parsed.scheme}://{parsed.netloc}{path}"
            return super().url(name, parameters=parameters, expire=expire, http_method=http_method)

        params["Bucket"] = self.bucket.name
        params["Key"] = name
        params.setdefault(
            "ResponseCacheControl",
            f"private, max-age={max(60, int(expire))}",
        )
        return self._signing_client().generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expire,
            HttpMethod=http_method,
        )
