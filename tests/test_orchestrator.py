"""End-to-end: submit -> plan (Mark) -> execute (tim) -> review -> report."""


def test_agents_registered(orchestrator):
    names = orchestrator.registry.names()
    assert "mark" in names
    assert "rita" in names
    assert "dev" in names
    assert "wren" in names
    assert "vera" in names


def test_full_flow(orchestrator):
    report = orchestrator.ask("Buat ringkasan tren AI 2026 untuk blog.")
    job = report.job

    assert job.status == "done"
    assert report.tasks_done >= 1
    assert job.final_report is not None

    tasks = orchestrator.tasks(job.id)
    assert all(t.status == "done" for t in tasks)
    docs = orchestrator.reports(job.id)
    assert any(d.doc_type == "plan" for d in docs)
    assert any(d.doc_type == "report" for d in docs)


def test_dependency_order_respected(orchestrator, storage):
    job = orchestrator.submit("Proyek bertahap untuk demo dependency.")
    tasks = orchestrator.tasks(job.id)
    assert tasks, "harus ada task hasil planning"

    # Semua task dengan dependency harus menunggu dependency done
    done: set[str] = set()
    for _ in range(20):
        ready = storage.get_ready_tasks(job.id)
        if not ready:
            break
        for t in ready:
            assert all(d in done for d in t.depends_on)
            storage.update_task(t.id, status="done")
            done.add(t.id)
    assert len(done) == len(tasks)


def test_review_flow_uses_vera(orchestrator):
    """Mock reviewer selalu approve; pastikan flow review jalan tanpa error."""
    job = orchestrator.submit("Misi dengan review.")
    report = orchestrator.run(job.id)
    assert report.job.status == "done"
