from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import create_async_engine

from agent_memory.curation import CurationPolicy, curate
from agent_memory.models import MemoryItem, MemoryKind, utcnow
from agent_memory.retrieval import HashingEmbedder
from agent_memory.sql import SqlMemoryStore, memory_table
from agent_memory.store import InMemoryStore, MemoryStore, NamespaceViolationError, Query, ScopedMemory

EMBED = HashingEmbedder(64)
WORLD = ("user", "u1", "world")
PEDAGOGY = ("user", "u1", "pedagogy")


def item(ns: tuple[str, ...], text: str, kind: MemoryKind = MemoryKind.EPISODIC, **kw: object) -> MemoryItem:
    return MemoryItem(namespace=ns, kind=kind, content=text, embedding=EMBED.embed(text), **kw)  # type: ignore[arg-type]


@pytest.fixture(params=["memory", "postgres"])
async def store(request: pytest.FixtureRequest) -> AsyncIterator[MemoryStore]:
    if request.param == "memory":
        yield InMemoryStore()
        return
    async with request.getfixturevalue("pg_schema_factory")() as (url, schema):
        engine = create_async_engine(url, connect_args={"options": f"-csearch_path={schema},public"})
        metadata = MetaData(schema=schema)
        table = memory_table(metadata, EMBED.dimensions)
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        yield SqlMemoryStore(engine, table)
        await engine.dispose()


async def test_put_get_list_and_prefix_isolation(store: MemoryStore) -> None:
    a = await store.put(item(WORLD, "Told the barista my name is Ernest"))
    await store.put(item(PEDAGOGY, "Struggles with si + imparfait", MemoryKind.SEMANTIC))
    await store.put(item(("user", "u10", "world"), "other user, prefix trap"))
    fetched = await store.get(a.id)
    assert fetched is not None
    assert fetched.model_dump(exclude={"embedding"}) == a.model_dump(exclude={"embedding"})
    assert fetched.embedding == pytest.approx(a.embedding, abs=1e-6)  # pgvector stores float32
    assert [i.content for i in await store.list_items(WORLD)] == [a.content]
    assert len(await store.list_items(("user", "u1"))) == 2
    assert len(await store.list_items(("user", "u1"), [MemoryKind.SEMANTIC])) == 1


async def test_search_ranks_by_similarity_and_updates_access(store: MemoryStore) -> None:
    await store.put(item(WORLD, "The landlord Martin kept the deposit for the cracked wall"))
    await store.put(item(WORLD, "Bought croissants at the bakery on rue Saint-Paul"))
    results = await store.search(Query(namespace=WORLD, embedding=EMBED.embed("deposit landlord wall"), limit=1))
    assert len(results) == 1
    assert "landlord" in results[0].item.content
    refreshed = await store.get(results[0].item.id)
    assert refreshed is not None and refreshed.access_count == 1


async def test_expired_and_tag_filters(store: MemoryStore) -> None:
    now = utcnow()
    await store.put(item(WORLD, "old flyer", expires_at=now - timedelta(minutes=1)))
    await store.put(item(WORLD, "flat key under the mat", tags=["flat"]))
    found = await store.search(Query(namespace=WORLD, tags=("flat",)), now=now)
    assert [r.item.content for r in found] == ["flat key under the mat"]
    assert len(await store.search(Query(namespace=WORLD), now=now)) == 1


async def test_delete_namespace_cascade(store: MemoryStore) -> None:
    await store.put(item(WORLD, "a"))
    await store.put(item(PEDAGOGY, "b"))
    await store.put(item(("user", "u2", "world"), "c"))
    assert await store.delete_namespace(("user", "u1")) == 2
    assert await store.list_items(("user",)) != []
    assert await store.list_items(("user", "u1")) == []


async def test_curation_expires_merges_and_caps(store: MemoryStore) -> None:
    now = utcnow()
    await store.put(item(WORLD, "gone", expires_at=now - timedelta(hours=1)))
    await store.put(item(WORLD, "Martin the landlord is grumpy", importance=0.3))
    await store.put(item(WORLD, "Martin the landlord is grumpy", importance=0.9))
    for text in ("rent is due monthly", "bakery opens at seven", "metro line two is closed", "Chloé plays violin"):
        await store.put(item(WORLD, text, MemoryKind.SEMANTIC))
    report = await curate(store, WORLD, CurationPolicy(max_items_per_kind=2), now=now)
    assert (report.expired, report.merged, report.evicted) == (1, 1, 2)
    episodic = await store.list_items(WORLD, [MemoryKind.EPISODIC])
    assert len(episodic) == 1 and episodic[0].importance == 0.9


async def test_scoped_view_blocks_pedagogy() -> None:
    raw = InMemoryStore()
    npc_view = ScopedMemory(raw, [WORLD, ("user", "u1", "npc", "martin")])
    await npc_view.put(item(WORLD, "met at the harbour"))
    with pytest.raises(NamespaceViolationError):
        await npc_view.search(Query(namespace=PEDAGOGY))
    with pytest.raises(NamespaceViolationError):
        await npc_view.put(item(PEDAGOGY, "weak conditionals"))
    with pytest.raises(NamespaceViolationError):
        await npc_view.list_items(("user", "u1"))


def test_embedder_is_deterministic_and_accent_insensitive() -> None:
    assert EMBED.embed("dépôt") == EMBED.embed("DEPOT")
    assert len(EMBED.embed("")) == 64
