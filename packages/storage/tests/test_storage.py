import socket
import uuid

import pytest

from lingard_storage import MemoryObjectStore, ObjectStore, S3ObjectStore, parse_ref, user_prefix


def _minio_up() -> bool:
    try:
        with socket.create_connection(("localhost", 59000), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.fixture(params=["memory", "minio"])
async def store(request: pytest.FixtureRequest) -> ObjectStore:
    if request.param == "memory":
        return MemoryObjectStore()
    if not _minio_up():
        pytest.skip("minio not running (docker compose up -d minio)")
    s3 = S3ObjectStore("http://localhost:59000", "lingard", "lingard-local-only")
    await s3.ensure_bucket("test-audio")
    return s3


async def test_put_get_list_delete_prefix(store: ObjectStore) -> None:
    bucket = "test-audio"
    user = user_prefix(str(uuid.uuid4()))
    other = user_prefix(str(uuid.uuid4()))
    ref = await store.put(bucket, f"{user}turns/1.opus", b"abc", "audio/ogg")
    await store.put(bucket, f"{user}samples/clone.wav", b"def")
    await store.put(bucket, f"{other}turns/1.opus", b"ghi")
    assert parse_ref(ref) == (bucket, f"{user}turns/1.opus")
    assert await store.get(bucket, f"{user}turns/1.opus") == b"abc"
    assert len(await store.list_keys(bucket, user)) == 2
    assert await store.delete_prefix(bucket, user) == 2
    assert await store.list_keys(bucket, user) == []
    assert await store.list_keys(bucket, other) == [f"{other}turns/1.opus"]
    await store.delete_prefix(bucket, other)
