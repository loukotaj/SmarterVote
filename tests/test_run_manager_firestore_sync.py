from pipeline_client.backend.models import RunInfo, RunStatus
from pipeline_client.backend.run_manager import RunManager


def test_list_active_runs_merges_firestore_active_snapshots():
    manager = RunManager()
    manager._db = object()

    local_active = RunInfo(
        run_id="local-run",
        status=RunStatus.RUNNING,
        payload={"race_id": "ga-senate-2026"},
        options={},
        started_at="2026-04-26T00:02:00+00:00",
        steps=[],
    )
    manager.active_runs = {local_active.run_id: local_active}

    remote_active = RunInfo(
        run_id="remote-run",
        status=RunStatus.PENDING,
        payload={"race_id": "az-senate-2026"},
        options={},
        started_at="2026-04-26T00:01:00+00:00",
        steps=[],
    )
    remote_completed = RunInfo(
        run_id="done-run",
        status=RunStatus.COMPLETED,
        payload={"race_id": "mi-senate-2026"},
        options={},
        started_at="2026-04-26T00:00:00+00:00",
        steps=[],
    )

    class FakeDoc:
        def __init__(self, data, doc_id: str):
            self._data = data
            self.id = doc_id

        def to_dict(self):
            return self._data

    class FakeCollection:
        def stream(self):
            return [
                FakeDoc(remote_active.model_dump(mode="json"), remote_active.run_id),
                FakeDoc(remote_completed.model_dump(mode="json"), remote_completed.run_id),
            ]

    class FakeDb:
        def collection(self, name: str):
            assert name == "pipeline_runs"
            return FakeCollection()

    manager._db = FakeDb()

    active_runs = manager.list_active_runs()

    assert [run.run_id for run in active_runs] == ["local-run", "remote-run"]


def test_get_run_tolerates_cloud_function_legacy_doc_without_payload():
    manager = RunManager()

    class FakeDoc:
        exists = True

        def to_dict(self):
            return {
                "run_id": "run-cf",
                "race_id": "ga-senate-2026",
                "status": "running",
                "options": {},
                "started_at": "2026-05-17T23:00:00+00:00",
            }

    class FakeDocRef:
        def get(self):
            return FakeDoc()

    class FakeCollection:
        def document(self, run_id: str):
            assert run_id == "run-cf"
            return FakeDocRef()

    class FakeDb:
        def collection(self, name: str):
            assert name == "pipeline_runs"
            return FakeCollection()

    manager._db = FakeDb()

    run = manager.get_run("run-cf")

    assert run is not None
    assert run.payload == {"race_id": "ga-senate-2026"}
    assert run.steps == []
