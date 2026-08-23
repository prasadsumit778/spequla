"""Immutable raw landing to object storage.

Implements corpus/04 section 5 ("source file -> source_file: hash recorded,
bytes retained immutably") and corpus/04 section 6 ("Object storage: tenant id
as the first path segment on every raw file"). This module only lands bytes
and computes hashes -- it does not parse, stage or write canonical facts. That
is the rest of Sprint 1's ingestion pipeline.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import boto3
from botocore.client import Config

ENDPOINT_URL = os.environ.get("OBJECT_STORE_ENDPOINT", "http://localhost:9000")
ACCESS_KEY = os.environ.get("OBJECT_STORE_ACCESS_KEY", "spequla")
SECRET_KEY = os.environ.get("OBJECT_STORE_SECRET_KEY", "spequla_dev_only")
BUCKET = os.environ.get("OBJECT_STORE_BUCKET", "spequla-raw")


def _client():
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket():
    s3 = _client()
    existing = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
    if BUCKET not in existing:
        s3.create_bucket(Bucket=BUCKET)


def content_hash(data: bytes) -> bytes:
    """Content hash of the raw file, per corpus/09 section 2.3 (idempotency)."""
    return hashlib.sha256(data).digest()


def schema_hash(header_row: list[str]) -> bytes:
    """Hash of the column header row only, per corpus/09 section 2.6
    (a schema hash change on a source file blocks the load rather than
    adapting -- never auto-adopted)."""
    return hashlib.sha256("|".join(header_row).encode()).digest()


def land_file(tenant_id: str, load_run_id: int, file_name: str, data: bytes) -> str:
    """Upload raw bytes immutably. Returns the tenant-id-prefixed storage path,
    per corpus/04 section 6."""
    ensure_bucket()
    key = f"{tenant_id}/raw/{load_run_id}/{Path(file_name).name}"
    _client().put_object(Bucket=BUCKET, Key=key, Body=data)
    return f"s3://{BUCKET}/{key}"


def read_landed(storage_path: str) -> bytes:
    assert storage_path.startswith(f"s3://{BUCKET}/")
    key = storage_path[len(f"s3://{BUCKET}/"):]
    obj = _client().get_object(Bucket=BUCKET, Key=key)
    return obj["Body"].read()
