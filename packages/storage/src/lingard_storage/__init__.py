"""Object storage for audio (learner turns, voice samples, synthesis cache). S3-compatible; MinIO locally."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol

AUDIO_BUCKET = "audio"


def ref(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"


def parse_ref(value: str) -> tuple[str, str]:
    if not value.startswith("s3://"):
        raise ValueError(f"not an object ref: {value}")
    bucket, _, key = value[5:].partition("/")
    return bucket, key


def user_prefix(user_id: str) -> str:
    """Every object owned by a learner lives under this prefix, so deletion and export are one prefix operation."""
    return f"users/{user_id}/"


class ObjectStore(Protocol):
    async def put(self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...

    async def get(self, bucket: str, key: str) -> bytes: ...

    async def delete_prefix(self, bucket: str, prefix: str) -> int: ...

    async def list_keys(self, bucket: str, prefix: str) -> list[str]: ...


@dataclass
class MemoryObjectStore:
    objects: dict[tuple[str, str], bytes] = field(default_factory=dict)

    async def put(self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.objects[(bucket, key)] = data
        return ref(bucket, key)

    async def get(self, bucket: str, key: str) -> bytes:
        return self.objects[(bucket, key)]

    async def delete_prefix(self, bucket: str, prefix: str) -> int:
        doomed = [k for k in self.objects if k[0] == bucket and k[1].startswith(prefix)]
        for k in doomed:
            del self.objects[k]
        return len(doomed)

    async def list_keys(self, bucket: str, prefix: str) -> list[str]:
        return sorted(k for b, k in self.objects if b == bucket and k.startswith(prefix))


class S3ObjectStore:
    """boto3 in a worker thread (calls are short; audio objects are small)."""

    def __init__(self, endpoint_url: str, access_key: str, secret_key: str, region: str = "us-east-1") -> None:
        import boto3

        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    async def ensure_bucket(self, bucket: str) -> None:
        def run() -> None:
            existing = {b["Name"] for b in self._client.list_buckets().get("Buckets", [])}
            if bucket not in existing:
                self._client.create_bucket(Bucket=bucket)

        await asyncio.to_thread(run)

    async def put(self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        return ref(bucket, key)

    async def get(self, bucket: str, key: str) -> bytes:
        def run() -> bytes:
            body: bytes = self._client.get_object(Bucket=bucket, Key=key)["Body"].read()
            return body

        return await asyncio.to_thread(run)

    async def list_keys(self, bucket: str, prefix: str) -> list[str]:
        def run() -> list[str]:
            keys: list[str] = []
            for page in self._client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
                keys += [o["Key"] for o in page.get("Contents", [])]
            return sorted(keys)

        return await asyncio.to_thread(run)

    async def delete_prefix(self, bucket: str, prefix: str) -> int:
        keys = await self.list_keys(bucket, prefix)
        for start in range(0, len(keys), 1000):
            batch = [{"Key": k} for k in keys[start : start + 1000]]
            await asyncio.to_thread(self._client.delete_objects, Bucket=bucket, Delete={"Objects": batch})
        return len(keys)
