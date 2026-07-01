from tilewarden import gcs


class FakeBlob:
    def __init__(self, name, *, time_created=None, updated=None):
        self.name = name
        self.time_created = time_created
        self.updated = updated


class FakeBucket:
    def __init__(self):
        self.calls = []
        self.responses = {
            None: [
                FakeBlob("metadata.json"),
                FakeBlob("Terrain/1/0/0", time_created="created-0", updated="updated-0"),
                FakeBlob("Terrain/1/0/1", time_created="created-1", updated="updated-1"),
            ],
            "Terrain/": [
                FakeBlob("Terrain/1/0/0", time_created="created-0", updated="updated-0"),
                FakeBlob("Terrain/1/0/1", time_created="created-1", updated="updated-1"),
            ],
            "Terrain/1/": [
                FakeBlob("Terrain/1/0/0", time_created="created-0", updated="updated-0"),
            ],
            "Terrain/3/": [
                FakeBlob("Terrain/3/0/0", time_created="created-3", updated="updated-3"),
            ],
        }

    def list_blobs(self, prefix=None, max_results=None):
        self.calls.append((prefix, max_results))
        return list(self.responses.get(prefix, []))


class FakeClient:
    created_with_project = None
    bucket_instance = FakeBucket()

    def __init__(self, project=None):
        self.__class__.created_with_project = project

    def bucket(self, bucket_name):
        self.bucket_name = bucket_name
        return self.__class__.bucket_instance


def test_list_source_objects_uses_storage_client_bucket_and_prefix(monkeypatch):
    FakeClient.bucket_instance = FakeBucket()
    monkeypatch.setattr(gcs.storage, "Client", FakeClient)

    source_objects = list(
        gcs.list_source_objects(
            bucket_name="tiles",
            prefix="Terrain/",
            layout="prefix/z/x/y",
            level_filter=None,
            project="proj",
        )
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
    assert FakeClient.bucket_instance.calls == [("Terrain/", None)]


def test_discover_listing_parameters_uses_bounded_sample(monkeypatch):
    FakeClient.bucket_instance = FakeBucket()
    monkeypatch.setattr(gcs.storage, "Client", FakeClient)

    discovered = gcs.discover_listing_parameters(
        bucket_name="tiles",
        prefix="",
        layout="auto",
        project="proj",
        max_results=2,
    )

    assert discovered == gcs.ListingParameters(layout="prefix/z/x/y", prefix="Terrain/")
    assert FakeClient.bucket_instance.calls == [(None, 2)]


def test_list_source_objects_batches_by_level_for_resolved_layout(monkeypatch):
    FakeClient.bucket_instance = FakeBucket()
    monkeypatch.setattr(gcs.storage, "Client", FakeClient)

    source_objects = list(
        gcs.list_source_objects(
            bucket_name="tiles",
            prefix="Terrain/",
            layout="prefix/z/x/y",
            level_filter={3, 1},
            project=None,
        )
    )

    assert [source_object.name for source_object in source_objects] == [
        "Terrain/1/0/0",
        "Terrain/3/0/0",
    ]
    assert FakeClient.bucket_instance.calls == [("Terrain/1/", None), ("Terrain/3/", None)]


def test_list_source_objects_falls_back_to_broad_listing_without_resolved_prefix(monkeypatch):
    FakeClient.bucket_instance = FakeBucket()
    monkeypatch.setattr(gcs.storage, "Client", FakeClient)

    source_objects = list(
        gcs.list_source_objects(
            bucket_name="tiles",
            prefix="",
            layout="prefix/z/x/y",
            level_filter={1},
            project=None,
        )
    )

    assert [source_object.name for source_object in source_objects] == [
        "metadata.json",
        "Terrain/1/0/0",
        "Terrain/1/0/1",
    ]
    assert FakeClient.bucket_instance.calls == [(None, None)]
