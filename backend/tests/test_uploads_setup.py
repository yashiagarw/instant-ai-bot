"""`python -m app.uploads.storage setup` against a fake S3 client: bucket, lifecycle, public access block and the
bucket CORS for the web app (production buckets are reached from the browser at S3_PUBLIC_ENDPOINT_URL)."""

from botocore.exceptions import ClientError

from app.config import Settings
from app.uploads.storage import S3Storage, cors_rules


def _error(op: str) -> ClientError:
    return ClientError({"Error": {"Code": "NotImplemented", "Message": "no"}}, op)


class FakeS3:
    def __init__(self, exists: bool = True, unsupported: tuple[str, ...] = ()):
        self.exists = exists
        self.unsupported = unsupported
        self.calls: dict[str, dict] = {}

    def _record(self, name: str, kwargs: dict):
        if name in self.unsupported:
            raise _error(name)
        self.calls[name] = kwargs

    def head_bucket(self, **kw):
        if not self.exists:
            raise _error("HeadBucket")

    def create_bucket(self, **kw):
        self._record("create_bucket", kw)

    def put_bucket_lifecycle_configuration(self, **kw):
        self._record("put_bucket_lifecycle_configuration", kw)

    def put_public_access_block(self, **kw):
        self._record("put_public_access_block", kw)

    def put_bucket_cors(self, **kw):
        self._record("put_bucket_cors", kw)

    def get_bucket_cors(self, **kw):
        # A server that accepts the rules but keeps nothing answers NoSuchCORSConfiguration (SeaweedFS 3.80).
        if "get_bucket_cors" in self.unsupported or "put_bucket_cors" not in self.calls:
            raise _error("GetBucketCors")
        return {"CORSRules": self.calls["put_bucket_cors"]["CORSConfiguration"]["CORSRules"]}


def make(fake: FakeS3, web_origin: str = "https://instantmechanic.online/") -> S3Storage:
    settings = Settings(_env_file=None, s3_access_key="k", s3_secret_key="s", s3_bucket="b", web_origin=web_origin)
    storage = S3Storage(settings)
    storage.client = fake
    return storage


def test_cors_allows_only_the_web_origin_to_post_and_get():
    rules = cors_rules("https://instantmechanic.online/")["CORSRules"]
    assert len(rules) == 1
    assert rules[0]["AllowedOrigins"] == ["https://instantmechanic.online"]
    assert set(rules[0]["AllowedMethods"]) == {"POST", "GET", "HEAD"}
    assert "PUT" not in rules[0]["AllowedMethods"] and "DELETE" not in rules[0]["AllowedMethods"]


def test_setup_creates_the_bucket_and_sets_its_cors():
    fake = FakeS3(exists=False)
    notes = make(fake).setup()
    assert notes == []
    assert fake.calls["create_bucket"] == {"Bucket": "b"}
    assert fake.calls["put_bucket_cors"]["Bucket"] == "b"
    assert fake.calls["put_bucket_cors"]["CORSConfiguration"] == cors_rules("https://instantmechanic.online")
    assert "put_bucket_lifecycle_configuration" in fake.calls


def test_setup_notes_a_storage_without_bucket_cors():
    fake = FakeS3(unsupported=("put_bucket_cors",))
    notes = make(fake, "https://localhost").setup()
    assert any("bucket CORS not supported" in n and "https://localhost" in n for n in notes)
    assert "create_bucket" not in fake.calls  # it existed


def test_setup_notes_a_storage_that_accepts_cors_but_keeps_nothing():
    fake = FakeS3(unsupported=("get_bucket_cors",))
    notes = make(fake, "https://localhost").setup()
    assert "put_bucket_cors" in fake.calls
    assert any("bucket CORS not supported" in n and "-s3.allowedOrigins" in n for n in notes)
