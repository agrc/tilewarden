from tilewarden import gcs


class FakeBlob:
    def __init__(self, name, *, time_created=None, updated=None):
        self.name = name
        self.time_created = time_created
        self.updated = updated


class FakeBucket:
    def __init__(self):
        self.listed_prefix = None

    def list_blobs(self, prefix=None):
        self.listed_prefix = prefix
        return [
            FakeBlob("Terrain/1/0/0", time_created="created-0", updated="updated-0"),
            FakeBlob("Terrain/1/0/1", time_created="created-1", updated="updated-1"),
        ]


class FakeClient:
    created_with_project = None
    bucket_instance = FakeBucket()

    def __init__(self, project=None):
        self.__class__.created_with_project = project

    def bucket(self, bucket_name):
        self.bucket_name = bucket_name
        return self.__class__.bucket_instance


def test_list_source_objects_uses_storage_client_bucket_and_prefix(monkeypatch):
    monkeypatch.setattr(gcs.storage, "Client", FakeClient)

    source_objects = list(
        gcs.list_source_objects(bucket_name="tiles", prefix="Terrain/", project="proj")
    )

    assert [source_object.name for source_object in source_objects] == [
        "Terrain/1/0/0",
        "Terrain/1/0/1",
    ]
    assert [source_object.date_created for source_object in source_objects] == [
        "created-0",
        "created-1",
    ]
    assert [source_object.date_last_modified for source_object in source_objects] == [
        "updated-0",
        "updated-1",
    ]
    assert FakeClient.created_with_project == "proj"
    assert FakeClient.bucket_instance.listed_prefix == "Terrain/"
