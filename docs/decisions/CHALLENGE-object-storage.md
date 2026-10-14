# CHALLENGE: "MinIO locally" (SPEC §2 Stores)

- **Date:** 2026-10-14
- **Status:** proceeding with a reversible substitute (decision 0002: no approval stops); founder may overrule

## Evidence

`docker pull minio/minio:<any tag>` and `quay.io/minio/minio:<tag>` fail from this environment ("repository does not
exist or may require docker login"). MinIO stopped distributing community container images, so "MinIO locally"
can't be reproduced by a fresh clone.

## What changed

Local S3 is SeaweedFS (`chrislusf/seaweedfs:3.80`, Apache-2.0) exposing the S3 API on port 59000. The code only
speaks S3 (`lingard_storage.S3ObjectStore`, boto3), so the locked intent (S3-compatible object storage) is unchanged
and any S3 provider (AWS S3, Cloudflare R2, Backblaze B2, self-built MinIO) works by configuration.

## To revert

Point `OBJECT_STORE_URL` at a MinIO server; no code changes.
