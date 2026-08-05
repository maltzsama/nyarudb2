# NyaruDB2

@Metadata {
  @Title("NyaruDB2")
  @PageKind(sampleCode)
  @PageColor(blue)
}

Embedded document database for Swift. No server, no schema, no ceremony.

## Overview

Store, query, and stream any `Codable` type — directly on device, with indexed queries, optional AES-256-GCM encryption, crash recovery, and real backpressure streaming. No Core Data stack, no migrations, no SQL.

> Deep dive: the full conceptual guide, installation, quick start, and performance numbers live in the [README](https://github.com/maltzsama/nyarudb2#readme).

---

## Why NyaruDB2?

What's genuinely different: a **Codable-native, schemaless API** with **built-in per-record AES-256-GCM encryption**, **actor-based concurrency**, and **automatic CRC-32 + dirty-flag crash recovery** — in one dependency-light package, no SQL and no migrations.

Good fit when:

- Your data is document-shaped and changes schema between app versions — there is no schema to migrate.
- You want per-record encryption without a third-party dependency.
- You are already writing async/await Swift and want a storage layer built on actors, not main-thread contexts or SQL.
- You want to stream large datasets without materializing them in memory.

Probably **not** the right choice when:

- You need the maturity, tooling, and query planner of SQLite or Core Data.
- Minimal disk footprint or raw single-metric speed is the only priority — NyaruDB2 is competitive with Core Data and Realm on those, not categorically ahead.

---

## Installation

```swift
// Package.swift
dependencies: [
    .package(url: "https://github.com/maltzsama/NyaruDB2.git", from: "0.3.0")
],
targets: [
    .target(name: "YourApp", dependencies: ["NyaruDB2"])
]
```

**Requirements:** Swift 5.9+ · iOS 15+ · macOS 13+

---

## Quick Start

```swift
import NyaruDB2

struct Article: Codable, Sendable {
    let id: Int
    let title: String
    let author: String
    let publishedAt: Date
}

// Open the database (creates the directory if needed)
let db = try NyaruDB(
    path: "/path/to/db",
    options: DatabaseOptions(compression: .gzip, format: .msgpack)
)

// Open a typed collection with secondary indexes
let articles = try await db.collection(
    "articles",
    of: Article.self,
    options: CollectionOptions(
        idField: "id",
        indexedFields: ["author", "publishedAt"]
    )
)

// Insert
try await articles.insert(Article(id: 1, title: "Hello", author: "Ana", publishedAt: .now))

// Bulk insert — validates all documents before writing any
try await articles.insert(contentsOf: moreArticles)

// Query
let recent = try await articles.find()
    .where("publishedAt", isGreaterThan: Date().addingTimeInterval(-86400 * 7))
    .sort(by: "publishedAt", ascending: false)
    .limit(20)
    .execute()

// Partial update — only the changed fields
try await articles.patch(id: 1, changes: ["title": "Updated title"])

// Delete by predicate
let removed = try await articles.find().where("author", isEqualTo: "spam-bot").delete()

// Delete many by id in a single batched pass
try await articles.delete(ids: [3, 5, 8])

// Pull-based stream — memory stays bounded regardless of collection size
for try await article in articles.stream(batchSize: 64) {
    process(article)
}

// Reclaim space left by deletions
try await articles.compact()

try await db.close()
```

---

## Core Concepts

### Collections

A collection is a typed, actor-isolated handle to a set of documents stored under a shared directory. Opening the same collection twice returns a cached handle; there is no risk of concurrent writers corrupting it.

`CollectionOptions` configures the primary key field, secondary indexes, and the partition key. Compression, serialization format, and the encryption key are database-wide (`DatabaseOptions`) and are frozen into each collection's manifest when it is first created.

### Indexes

The `idField` is always indexed. Declare additional fields at open time:

```swift
CollectionOptions(idField: "id", indexedFields: ["email", "region", "score"])
```

The `idField`, `partitionKey`, and `compression` are frozen after the first open. Indexed operations run in O(log n); unindexed fields fall back to a full scan with the predicate applied in memory.

### Queries

```swift
// Equality, comparisons, ranges
users.find()
    .where("score", isGreaterThanOrEqualTo: 100)
    .where("score", isLessThan: 500)

// Set membership
users.find().where("tier", isIn: ["gold", "platinum"])

// Text predicates
users.find().where("email", endsWith: "@example.com")
users.find().where("username", like: "ana%")      // SQL-style wildcards
users.find().where("slug", glob: "2026-*-post")   // glob wildcards

// Logical composition — chained wheres are AND; use Predicate for OR/NOT
users.find()
    .where("age", isGreaterThanOrEqualTo: 18)
    .where(.or([.equal("country", "BR"), .equal("country", "PT")]))

// Existence
users.find().whereExists("phoneNumber")

// Sort, page
users.find().sort(by: "name").offset(40).limit(20).execute()

// Inspect the plan before running
let plan = await users.find().where("score", isGreaterThan: 50).explain()
```

### Atomic write batches

`writeBatch` accumulates mixed operations and applies them as one all-or-nothing unit:

```swift
try await users.writeBatch { batch in
    batch.insert(newUser)
    batch.update(changedUser)
    batch.delete(id: retiredUserID)
}
```

Every operation is validated **before** anything is written: a duplicate id, a missing update target, a thrown body, or two operations on the same id abort the batch with zero side effects, and a failed write is rolled back.

### Partitioning

When documents share a partition key (e.g. `region`, `category`), route them to dedicated shard files:

```swift
CollectionOptions(idField: "id", partitionKey: "region")
```

### Encryption

```swift
// Recommended: random key stored in the Keychain
let key = NyaruCrypto.generateRandomKey()
let db = try NyaruDB(path: path, options: DatabaseOptions(encryptionKey: key))
```

Encryption covers every record payload, every index snapshot, and the collection manifest. Opening with the wrong key fails immediately at the manifest with `NyaruError.decryptionFailed`.

### Crash Recovery & Fast Opens

Every record carries a CRC-32 checksum, and the shard header has a dirty flag set before the first write and cleared on clean close. On the next open, dirty shards are scanned, bad records tombstoned, torn writes truncated, and indexes rebuilt — automatically.

**Clean opens are O(1):** each shard persists scan-derived state (live count, free slots) to a `.state` sidecar that is adopted when the dirty flag is clear *and* the recorded file size matches.

### Compaction

```swift
// Compact only if fragmentation is worth it
if try await articles.needsCompaction() {
    try await articles.compact()
}
```

Compaction runs incrementally, one shard at a time — concurrent reads and writes interleave between cycles, keeping the worst-case stall to a single shard's rewrite.

### Durability

```swift
try await articles.sync()   // one collection
try await db.sync()         // every open collection
```

Or automatic, via `DatabaseOptions(autoSync: .afterWrites(500))` / `.interval(30)`. There are no background timers — an idle database never wakes up.

### Metrics and Logging

`collection.metrics()` returns cumulative counters (index lookups, covered queries, scan paths, shard I/O, compaction, recovery). NyaruDB2 logs structured events through [swift-log](https://github.com/apple/swift-log); control with `NyaruLogger.logLevel`.

---

## Serialization & Compression

| Option | Notes |
|---|---|
| `.gzip` | Portable, ~10× reduction on typical payloads |
| `.lzfse` | Apple platforms; faster decompression, moderate ratio |
| `.lz4` | Apple platforms; recommended only for large documents |
| `.none` | No compression |
| `format: .msgpack` | Binary serialization; use `.json` for human-readable storage |

Default recommendation: `gzip` + `msgpack` for production; `none` + `json` for debugging.

---

## Error Handling

All operations throw `NyaruError`:

```swift
do {
    try await users.insert(user)
} catch NyaruError.duplicateID(let id) {
    // Document with this id already exists
} catch NyaruError.decryptionFailed {
    // Wrong key or corrupted record
}
```

---

> Engine internals, storage format, and performance details are documented in [ARCHITECTURE.md](https://github.com/maltzsama/nyarudb2/blob/main/ARCHITECTURE.md) and [CHANGELOG.md](https://github.com/maltzsama/nyarudb2/blob/main/CHANGELOG.md).