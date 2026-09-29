"""Day-0 import: every document lands once, with its own date, and PDFs go through retain_files."""

from dejavu.documents import day0_documents
from dejavu.memory.day0 import import_day0
from tests.memory.fakememory import FakeMemory


async def test_day0_import_keeps_original_dates_and_formats() -> None:
    memory = FakeMemory(pending_polls=1)
    docs = {d.id: d for d in day0_documents()}
    report = await import_day0(memory, "bank", timeout_s=5)

    retained = {i.document_id: i for i in memory.items["bank"]}
    files = {f.document_id: f for f in memory.files["bank"]}
    assert set(retained) == {i for i, d in docs.items() if d.format == "md"}
    assert set(files) == {i for i, d in docs.items() if d.format == "pdf"}
    assert len(files) == 2
    assert all(item.timestamp == docs[i].date for i, item in retained.items())
    assert all(f.timestamp == docs[i].date for i, f in files.items())
    assert not report.timed_out
    assert report.operations == 1 + len(files)


async def test_old_runbooks_are_tagged_by_service() -> None:
    memory = FakeMemory()
    await import_day0(memory, "bank", timeout_s=5)
    runbook = next(i for i in memory.items["bank"] if i.document_id == "RB-ledger-pool")
    assert "service:ledger-svc" in runbook.tags
    assert runbook.metadata["kind"] == "runbook"
    assert runbook.context == "runbook"
