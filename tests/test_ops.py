"""Operasional dashboard / maintenance: jobs, retry, cancel, delete, clear, logs."""


def test_all_jobs_returns_all(orchestrator):
    j1 = orchestrator.submit("Job pertama.")
    j2 = orchestrator.submit("Job kedua.")
    ids = {j.id for j in orchestrator.all_jobs()}
    assert {j1.id, j2.id} <= ids


def test_all_tasks_across_jobs(orchestrator):
    j1 = orchestrator.submit("Misi A.")
    j2 = orchestrator.submit("Misi B.")
    ids = {t.id for t in orchestrator.all_tasks()}
    assert {t.id for t in orchestrator.tasks(j1.id)} <= ids
    assert {t.id for t in orchestrator.tasks(j2.id)} <= ids


def test_retry_task_resets_failed(orchestrator):
    job = orchestrator.submit("Misi untuk cek retry.")
    target = orchestrator.tasks(job.id)[0]
    orchestrator.retry_task(target.id)
    orchestrator.storage.update_task(target.id, status="failed", error="gagal")

    after = orchestrator.retry_task(target.id)
    assert after.status == "ready"
    assert after.error is None


def test_retry_only_on_failed(orchestrator):
    job = orchestrator.submit("Misi untuk cek retry yang tidak cocok.")
    done = [t for t in orchestrator.tasks(job.id) if t.status == "done"]
    if done:
        after = orchestrator.retry_task(done[0].id)
        assert after.status == "done"


def test_cancel_job_marks_failed(orchestrator):
    job = orchestrator.submit("Misi yang akan dibatalkan.")
    updated = orchestrator.cancel_job(job.id)
    assert updated.status == "failed"
    for t in orchestrator.tasks(job.id):
        assert t.status == "failed"


def test_delete_job_removes_everything(orchestrator, storage):
    job = orchestrator.submit("Misi untuk dihapus.")
    assert orchestrator.delete_job(job.id) is True
    assert orchestrator.status(job.id) is None
    assert orchestrator.tasks(job.id) == []


def test_delete_job_unknown_returns_false(orchestrator):
    assert orchestrator.delete_job("tidak-ada") is False


def test_clear_all(orchestrator):
    orchestrator.submit("Misi satu.")
    orchestrator.submit("Misi dua.")
    orchestrator.clear_all()
    assert orchestrator.all_jobs() == []
    assert orchestrator.all_tasks() == []


def test_skill_log_records_entries(orchestrator):
    assert orchestrator.skill_log() == []
    orchestrator.run(orchestrator.submit("Misi untuk mencatat aktivitas skill.").id)
    log = orchestrator.skill_log()
    assert log, "harus ada entri log setelah eksekusi"
    assert all("skill" in e and "ok" in e and "time" in e for e in log)
