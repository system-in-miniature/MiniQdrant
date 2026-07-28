from __future__ import annotations

from miniqdrant import (
    Database,
    Distance,
    Filter,
    Match,
    OptimizerConfig,
    PayloadSchema,
    Point,
    ScalarQuantizationConfig,
    SearchRequest,
)


def test_full_semantic_closure(tmp_path) -> None:
    database = Database.open(tmp_path)
    collection = database.create_collection(
        "items",
        dimension=4,
        distance=Distance.COSINE,
        optimizer=OptimizerConfig(indexing_threshold_points=1),
        quantization=ScalarQuantizationConfig(oversampling=4),
    )
    collection.create_payload_index("category", PayloadSchema.KEYWORD)
    collection.upsert(
        [
            Point(1, (1.0, 0.0, 0.0, 0.0), {"category": "book"}),
            Point(2, (0.9, 0.1, 0.0, 0.0), {"category": "book"}),
            Point(3, (0.0, 1.0, 0.0, 0.0), {"category": "film"}),
            Point(4, (0.0, 0.0, 1.0, 0.0), {"category": "book"}),
        ]
    )
    request = SearchRequest(
        (1.0, 0.0, 0.0, 0.0),
        3,
        filter=Filter(must=(Match("category", "book"),)),
    )
    exact = collection.search(
        SearchRequest(
            request.vector,
            request.limit,
            filter=request.filter,
            exact=True,
        )
    )

    collection.optimize()
    approximate = collection.search(request)
    collection.delete([2])
    collection.flush()
    database.simulate_process_loss()

    reopened = Database.open(tmp_path).collection("items")
    restored = reopened.search(
        SearchRequest(
            request.vector,
            request.limit,
            filter=request.filter,
            exact=True,
        )
    )

    assert {hit.id for hit in approximate.hits} == {hit.id for hit in exact.hits}
    assert approximate.plan == ("quantized_hnsw_rescore",)
    assert [hit.id for hit in restored.hits] == [1, 4]
    assert reopened.retrieve([2]) == ()
