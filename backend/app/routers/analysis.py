"""Analysis endpoints: sentiment, topics, bot likelihood, misinformation."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analysis import bot as bot_analysis
from app.analysis import misinformation as misinfo_analysis
from app.analysis import sentiment as sentiment_analysis
from app.analysis import topics as topics_analysis
from app.app_state import analysis_cache
from app.database import get_db
from app.ml import registry
from app.schemas import (
    BotResponse,
    DatasetScopedRequest,
    InferRequest,
    MisinformationRequest,
    MisinformationResponse,
    SentimentResponse,
    TopicsRequest,
    TopicsResponse,
)
from app.services import dataset_service
from app.security.audit import record_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _frame(db: Session, dataset_id: str):
    dataset = dataset_service.get_dataset(db, dataset_id)
    df = dataset_service.dataset_frame(dataset)
    return dataset, df


def _audit(db: Session, dataset, event: str, details: dict) -> None:
    if dataset.evidence_id:
        record_event(db, dataset.evidence_id, event, details)


@router.post("/sentiment", response_model=SentimentResponse)
def sentiment(body: DatasetScopedRequest, db: Session = Depends(get_db)):
    dataset, df = _frame(db, body.dataset_id)
    result = sentiment_analysis.analyze_dataset(df, dataset.column_map or {})
    analysis_cache.store(body.dataset_id, "sentiment", result)
    _audit(db, dataset, "ANALYZE", {"type": "sentiment", "records": result["total"]})
    return SentimentResponse(dataset_id=body.dataset_id, **result)


@router.post("/topics", response_model=TopicsResponse)
def topics(body: TopicsRequest, db: Session = Depends(get_db)):
    dataset, df = _frame(db, body.dataset_id)
    result = topics_analysis.analyze_dataset(
        df, dataset.column_map or {}, n_topics=body.n_topics, top_terms=body.top_terms
    )
    analysis_cache.store(body.dataset_id, "topics", result)
    _audit(db, dataset, "ANALYZE", {"type": "topics", "n_topics": result["n_topics"]})
    return TopicsResponse(dataset_id=body.dataset_id, **result)


@router.post("/bot", response_model=BotResponse)
def bot(body: DatasetScopedRequest, db: Session = Depends(get_db)):
    dataset, df = _frame(db, body.dataset_id)
    artifact = registry.active_artifact(db, "bot_detection")
    bot_analysis.require_model(artifact)   # → 409 "Model not trained" if missing
    features = bot_analysis.build_account_features(df, dataset.column_map or {})
    result = bot_analysis.predict_accounts(features, artifact)
    analysis_cache.store(body.dataset_id, "bot", result)
    _audit(db, dataset, "ANALYZE", {"type": "bot_detection", "accounts": len(result["accounts"])})
    return BotResponse(dataset_id=body.dataset_id, **result)


@router.post("/misinformation", response_model=MisinformationResponse)
def misinformation(body: MisinformationRequest, db: Session = Depends(get_db)):
    dataset, df = _frame(db, body.dataset_id)
    artifact = registry.active_artifact(db, "misinformation")
    bot_analysis.require_model(artifact)   # same 409 semantics
    result = misinfo_analysis.predict_content(
        df, dataset.column_map or {}, artifact, limit=body.limit
    )
    analysis_cache.store(body.dataset_id, "misinformation", result)
    _audit(
        db, dataset, "ANALYZE",
        {"type": "misinformation", "evaluated": result["summary"]["evaluated"]},
    )
    return MisinformationResponse(dataset_id=body.dataset_id, **result)


@router.post("/inference")
def inference(body: InferRequest, db: Session = Depends(get_db)):
    """Ad-hoc inference on arbitrary texts or a dataset using the active model."""
    import pandas as pd

    from app.utils.column_detect import resolve
    from app.utils.errors import ModelNotTrained, ValidationFailed

    task = body.task
    artifact = registry.active_artifact(db, task) if task != "sentiment" else {"active": True}
    if task != "sentiment" and not artifact:
        raise ModelNotTrained(task)

    if body.texts:
        df = pd.DataFrame({"text": [str(t) for t in body.texts[: body.limit]]})
        mapping = {"text": "text"}
    else:
        if not body.dataset_id:
            raise ValidationFailed("Provide either 'texts' or 'dataset_id'.")
        dataset, df = _frame(db, body.dataset_id)
        mapping = dataset.column_map or {}
        df = df.head(body.limit)

    if task == "sentiment":
        text_col = resolve(mapping, "text") or resolve(mapping, "text_clean")
        if not text_col or text_col not in df.columns:
            raise ValidationFailed("No text column available for sentiment inference.")
        texts = df[text_col].fillna("").astype(str).tolist()
        scores = sentiment_analysis.score_texts(texts)
        return {
            "task": task,
            "mode": "adhoc" if body.texts else "dataset",
            "items": [
                {
                    "text": t[:300],
                    "model_classification": sentiment_analysis.label_for_compound(
                        s["compound"]
                    ),
                    "confidence": round(abs(s["compound"]), 4),
                    "scores": s,
                }
                for t, s in zip(texts, scores)
            ],
            "note": "VADER lexicon scoring (no trained model required).",
        }

    if task == "misinformation":
        result = misinfo_analysis.predict_content(df, mapping, artifact, limit=body.limit)
        return {"task": task, "mode": "adhoc" if body.texts else "dataset", **result}

    # bot_detection on arbitrary text is meaningless — always dataset-scoped
    if body.texts:
        raise ValidationFailed(
            "Automated-account analysis requires dataset-level account features."
        )
    features = bot_analysis.build_account_features(df, mapping)
    result = bot_analysis.predict_accounts(features, artifact)
    return {"task": task, "mode": "dataset", **result}
