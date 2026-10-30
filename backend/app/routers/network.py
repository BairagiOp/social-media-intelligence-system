"""Network graph endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.analysis import bot as bot_analysis
from app.analysis import network as network_analysis
from app.database import get_db
from app.ml import registry
from app.schemas import GraphResponse
from app.services import dataset_service

router = APIRouter(prefix="/api/network", tags=["network"])


@router.get("/graph", response_model=GraphResponse)
def graph(
    dataset_id: str = Query(...),
    edge_types: str = Query("mention,reply,share"),
    min_weight: int = Query(1, ge=1),
    date_from: str | None = None,
    date_to: str | None = None,
    max_nodes: int = Query(300, ge=10, le=1000),
    db: Session = Depends(get_db),
):
    dataset = dataset_service.get_dataset(db, dataset_id)
    df = dataset_service.dataset_frame(dataset)
    mapping = dataset.column_map or {}

    types = tuple(
        t.strip() for t in edge_types.split(",") if t.strip() in network_analysis.EDGE_TYPES
    ) or network_analysis.EDGE_TYPES

    G, stats = network_analysis.build_graph(
        df,
        mapping,
        edge_types=types,
        min_weight=min_weight,
        date_from=date_from,
        date_to=date_to,
        max_nodes=max_nodes,
    )
    communities = network_analysis.detect_communities(G)
    centrality = network_analysis.compute_centrality(G)

    # Attach automated-account likelihood to nodes when a model is active.
    scores: dict[str, float] = {}
    artifact = registry.active_artifact(db, "bot_detection")
    if artifact:
        try:
            features = bot_analysis.build_account_features(df, mapping)
            prediction = bot_analysis.predict_accounts(features, artifact)
            scores = {
                a["username"]: a["score"] for a in prediction["accounts"]
            }
        except Exception:
            scores = {}

    payload = network_analysis.graph_payload(G, stats, communities, centrality, scores)
    return GraphResponse(dataset_id=dataset_id, **payload)
