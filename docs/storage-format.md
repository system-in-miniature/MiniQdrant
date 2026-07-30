> **Language**: English | [简体中文](zh/storage-format.md)

# Storage format

These formats are private to MiniQdrant and intentionally incompatible with
Qdrant.

## Collection root

```text
collection/
├── collection.json
├── CURRENT
├── manifest-000000000000000000NN.json
├── wal/00000000000000000001.wal
└── segments/seg-<uuid>/
    ├── meta.json
    ├── points.bin
    ├── payloads.bin
    ├── versions.bin
    ├── deleted.bin
    ├── hnsw.bin
    └── payload-indexes.bin
```

`collection.json` stores the immutable collection configuration and payload
index schemas. `CURRENT` contains one manifest filename. Manifests are canonical
JSON envelopes with a SHA-256 of their payload, generation, schema fingerprint,
ordered segment IDs, and WAL replay boundary.

## WAL frame

All integers are big-endian:

```text
magic "MQWL" (4)
format version (1)
body length (4)
sequence (8)
operation kind (1)
canonical JSON operation payload (N)
CRC32 of body (4)
```

Operation kind 1 is a batch upsert and kind 2 is a batch delete. Sequences must
start at one and remain contiguous. Recovery may truncate only an incomplete or
checksum-invalid final frame.

## Segment blobs

Each `.bin` file is independently framed:

```text
magic "MQSG" (4)
format version (1)
JSON payload length (4)
canonical JSON payload (N)
CRC32 of header plus payload (4)
```

`meta.json` records the schema, indexed flag, and SHA-256 for every blob. Point
IDs are explicitly tagged as integer or UUID. Versions and tombstones are
separate logical columns. The current implementation reconstructs in-memory
indexes from this semantic image when opening.

## Snapshot

```text
snapshot/
├── snapshot.json
└── collection/
```

`snapshot.json` maps every relative collection file to SHA-256. Creation copies
the current manifest, referenced segments, metadata, `CURRENT`, and WAL into a
temporary root, fsyncs it, then renames it. Restore checks the exact file set and
hashes, validates manifest/segments, copies to a staging collection, rewrites
only the collection name when requested, opens it successfully, and then
publishes it.
