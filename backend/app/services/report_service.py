"""Intelligence report generation.

Every section is labelled by evidence class:
  OBSERVED      — computed directly from the dataset
  MODEL OUTPUT  — produced by a trained model
  INFERENCE     — statistical interpretation of the above
  HUMAN         — requires human interpretation/verification
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.analysis import bot as bot_analysis
from app.analysis import misinformation as misinfo_analysis
from app.analysis import network as network_analysis
from app.analysis import sentiment as sentiment_analysis
from app.analysis import topics as topics_analysis
from app.ml import registry
from app.models.model_registry import ReportRecord
from app.security.audit import record_event
from app.services import dataset_service, evidence_service

logger = logging.getLogger(__name__)


def _section(title: str, evidence_class: str, body: dict | list | str) -> dict:
    return {"title": title, "evidence_class": evidence_class, "body": body}


def build_report(db: Session, dataset_id: str | None, title: str | None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    datasets = dataset_service.list_datasets(db)
    dataset = dataset_service.get_dataset(db, dataset_id) if dataset_id else (
        next((d for d in datasets if d.status == "PREPROCESSED"), datasets[0] if datasets else None)
    )

    sections: dict[str, dict] = {}
    warnings: list[str] = []

    # ---------------- Executive summary (assembled last) ----------------
    dataset = dataset  # may be None

    # ---------------- Dataset information ----------------
    if dataset:
        df = dataset_service.dataset_frame(dataset)
        mapping = dataset.column_map or {}
        sections["dataset_information"] = _section(
            "Dataset Information",
            "OBSERVED",
            {
                "dataset_id": dataset.id,
                "name": dataset.name,
                "filename": dataset.filename,
                "format": dataset.format,
                "records": dataset.records,
                "columns": len(dataset.columns or []),
                "version": dataset.version,
                "status": dataset.status,
                "detected_columns": mapping,
            },
        )

        # ---------------- Evidence integrity ----------------
        if dataset.evidence_id:
            evidence = evidence_service.get_evidence(db, dataset.evidence_id)
            integrity = evidence_service.verify_integrity(evidence)
            events = evidence_service.audit_log(db, evidence)
            sections["evidence_integrity"] = _section(
                "Evidence Integrity",
                "OBSERVED",
                {
                    "evidence_id": evidence.evidence_id,
                    "filename": evidence.filename,
                    "sha256": evidence.sha256,
                    "size_bytes": evidence.size_bytes,
                    "uploaded_at": evidence.uploaded_at.isoformat()
                    if evidence.uploaded_at else None,
                    "integrity_check": integrity,
                    "audit_event_count": len(events),
                },
            )
            sections["audit_trail"] = _section(
                "Audit Trail",
                "OBSERVED",
                {
                    "events": [
                        {
                            "event": e.event,
                            "at": e.created_at.isoformat() if e.created_at else None,
                            "details": e.details,
                        }
                        for e in events
                    ]
                },
            )

        # ---------------- Data statistics ----------------
        profile = dataset.profile or dataset_service.get_profile(db, dataset.id)
        sections["data_statistics"] = _section(
            "Data Statistics",
            "OBSERVED",
            {
                "records": profile.get("records"),
                "columns": profile.get("columns_count"),
                "duplicate_records": profile.get("duplicate_records"),
                "unique_users": profile.get("unique_users"),
                "platform_distribution": profile.get("platform_distribution"),
                "date_range": profile.get("date_range"),
                "language_distribution": profile.get("language_distribution"),
                "avg_text_length": profile.get("avg_text_length"),
                "class_distributions": profile.get("class_distributions"),
            },
        )

        # ---------------- Sentiment ----------------
        try:
            sentiment = sentiment_analysis.analyze_dataset(df, mapping)
            sections["sentiment_analysis"] = _section(
                "Sentiment Analysis",
                "OBSERVED",
                {
                    "disclaimer": sentiment["disclaimer"],
                    "overall": sentiment["overall"],
                    "most_positive": sentiment["most_positive"][:3],
                    "most_negative": sentiment["most_negative"][:3],
                },
            )
        except Exception as exc:
            warnings.append(f"Sentiment: {exc}")
            sections["sentiment_analysis"] = _section(
                "Sentiment Analysis", "OBSERVED", {"error": str(exc)}
            )

        # ---------------- Topics ----------------
        try:
            topics = topics_analysis.analyze_dataset(df, mapping, n_topics=6)
            sections["topic_analysis"] = _section(
                "Topic Analysis",
                "OBSERVED",
                {
                    "n_topics": topics["n_topics"],
                    "quality": topics["quality"],
                    "topics": [
                        {
                            "id": t["id"],
                            "keywords": [k["term"] for k in t["keywords"][:6]],
                            "frequency": t["frequency"],
                        }
                        for t in topics["topics"]
                    ],
                },
            )
        except Exception as exc:
            warnings.append(f"Topics: {exc}")
            sections["topic_analysis"] = _section(
                "Topic Analysis", "OBSERVED", {"error": str(exc)}
            )

        # ---------------- Automated accounts ----------------
        artifact = registry.active_artifact(db, "bot_detection")
        if artifact:
            try:
                features = bot_analysis.build_account_features(df, mapping)
                result = bot_analysis.predict_accounts(features, artifact)
                high = [a for a in result["accounts"] if a["score"] >= 0.6]
                sections["automated_account_analysis"] = _section(
                    "Automated Account Analysis",
                    "MODEL OUTPUT",
                    {
                        "disclaimer": result["disclaimer"],
                        "model": result["model"],
                        "accounts_evaluated": len(result["accounts"]),
                        "high_likelihood_count": len(high),
                        "top_examples": [
                            {
                                "username": a["username"],
                                "score": a["score"],
                                "top_factors": a["feature_contributions"][:3],
                            }
                            for a in high[:5]
                        ],
                        "interpretation": (
                            "Accounts listed above scored high on posting-pattern "
                            "features. This is a statistical estimate only; human "
                            "review is required before any conclusion."
                        ),
                    },
                )
            except Exception as exc:
                warnings.append(f"Bot analysis: {exc}")
                sections["automated_account_analysis"] = _section(
                    "Automated Account Analysis", "MODEL OUTPUT", {"error": str(exc)}
                )
        else:
            sections["automated_account_analysis"] = _section(
                "Automated Account Analysis",
                "MODEL OUTPUT",
                {"status": "Model not trained"},
            )
            warnings.append("Bot model not trained.")

        # ---------------- Misinformation ----------------
        artifact = registry.active_artifact(db, "misinformation")
        if artifact:
            try:
                result = misinfo_analysis.predict_content(df, mapping, artifact, limit=300)
                sections["misinformation_model_results"] = _section(
                    "Misinformation Model Results",
                    "MODEL OUTPUT",
                    {
                        "disclaimer": result["disclaimer"],
                        "model": result["model"],
                        "summary": result["summary"],
                        "interpretation": (
                            "Classifications are model outputs with confidence "
                            "estimates — not factual determinations. Human "
                            "verification against reliable sources is required."
                        ),
                    },
                )
            except Exception as exc:
                warnings.append(f"Misinformation: {exc}")
                sections["misinformation_model_results"] = _section(
                    "Misinformation Model Results", "MODEL OUTPUT", {"error": str(exc)}
                )
        else:
            sections["misinformation_model_results"] = _section(
                "Misinformation Model Results",
                "MODEL OUTPUT",
                {"status": "Model not trained"},
            )
            warnings.append("Misinformation model not trained.")

        # ---------------- Network ----------------
        try:
            G, stats = network_analysis.build_graph(df, mapping, max_nodes=200)
            communities = network_analysis.detect_communities(G)
            centrality = network_analysis.compute_centrality(G)
            sections["network_analysis"] = _section(
                "Network Analysis",
                "OBSERVED",
                {
                    "disclaimer": network_analysis.DISCLAIMER,
                    "stats": stats,
                    "community_method": communities.get("method"),
                    "community_count": communities.get("count"),
                    "largest_communities": communities.get("communities", [])[:5],
                    "central_accounts": {
                        "degree": centrality.get("degree", [])[:5],
                        "pagerank": centrality.get("pagerank", [])[:5],
                    },
                },
            )
        except Exception as exc:
            warnings.append(f"Network: {exc}")
            sections["network_analysis"] = _section(
                "Network Analysis", "OBSERVED", {"error": str(exc)}
            )
    else:
        sections["dataset_information"] = _section(
            "Dataset Information", "OBSERVED", {"error": "No dataset available."}
        )

    # ---------------- Model performance ----------------
    model_perf = {}
    for task in ("sentiment", "bot_detection", "misinformation", "topic_model"):
        record = registry.get_active(db, task)
        model_perf[task] = (
            {
                "model_id": record.model_id,
                "name": record.name,
                "version": record.version,
                "status": record.status,
                "metrics": record.metrics,
            }
            if record
            else "Model not trained"
        )
    sections["model_performance"] = _section(
        "Model Performance", "MODEL OUTPUT", model_perf
    )

    # ---------------- Important patterns (INFERENCE) ----------------
    patterns = []
    profile = None
    if dataset and dataset.profile:
        profile = dataset.profile
    if profile:
        sent = profile.get("sentiment_distribution") or {}
        if sent.get("labels"):
            dominant = max(sent["labels"], key=sent["labels"].get)
            patterns.append(
                f"Sentiment skews {dominant} "
                f"({sent['labels'][dominant]*100:.1f}% of scored posts)."
            )
        plats = profile.get("platform_distribution") or {}
        if plats:
            top = max(plats, key=plats.get)
            patterns.append(
                f"'{top}' is the dominant platform "
                f"({plats[top]} of {profile.get('records', 0)} records)."
            )
        dups = profile.get("duplicate_records") or 0
        if dups:
            patterns.append(
                f"{dups} duplicate records detected — removed during preprocessing."
            )
    if not patterns:
        patterns.append("No dataset loaded — patterns require data.")
    sections["important_patterns"] = _section(
        "Important Patterns", "INFERENCE", patterns
    )

    # ---------------- Limitations (HUMAN) ----------------
    limitations = [
        "Model classifications are probabilistic estimates, not factual determinations.",
        "Sentiment reflects text tone only and does not indicate intent.",
        "Graph co-occurrence patterns do not prove real-world coordination.",
        "Results apply only to the loaded dataset and its time range.",
        "Public/synthetic data only — no private or authenticated data is used.",
    ] + [f"Warning: {w}" for w in warnings]
    sections["limitations"] = _section("Limitations", "HUMAN", limitations)

    # ---------------- Executive summary ----------------
    exec_body = {
        "generated_at": now,
        "dataset": dataset.name if dataset else None,
        "records": dataset.records if dataset else 0,
        "summary": [
            f"Analyzed {dataset.records if dataset else 0} records from "
            f"{profile.get('unique_users', 0)} accounts."
            if dataset
            else "No dataset loaded.",
            f"Models active: "
            + ", ".join(
                t for t in model_perf
                if isinstance(model_perf[t], dict)
            )
            or "None",
        ],
        "note": (
            "This report separates observed data, model output, statistical "
            "inference, and items requiring human interpretation. It does not "
            "make accusations about any real person or organization."
        ),
    }
    sections_ordered = {"executive_summary": _section(
        "Executive Summary", "INFERENCE", exec_body
    )}
    sections_ordered.update(sections)

    markdown = _render_markdown(title or "SMDPIS Intelligence Report", sections_ordered, now)
    return {"sections": sections_ordered, "markdown": markdown, "generated_at": now}


def _render_markdown(title: str, sections: dict, now: str) -> str:
    lines = [f"# {title}", f"_Generated: {now}_", ""]
    for key, section in sections.items():
        lines.append(f"## {section['title']}")
        lines.append(f"**Evidence class:** {section['evidence_class']}")
        body = section["body"]
        if isinstance(body, str):
            lines.append(body)
        elif isinstance(body, list):
            for item in body:
                lines.append(f"- {item}")
        elif isinstance(body, dict):
            if "error" in body:
                lines.append(f"- {body['error']}")
            else:
                for k, v in body.items():
                    if isinstance(v, (dict, list)):
                        import json as _json

                        v = _json.dumps(v, ensure_ascii=False, default=str)
                        if len(v) > 800:
                            v = v[:800] + "…"
                    lines.append(f"- **{k}**: {v}")
        lines.append("")
    return "\n".join(lines)


def create_report(db: Session, dataset_id: str | None, title: str | None) -> ReportRecord:
    payload = build_report(db, dataset_id, title)
    final_title = title or (
        "SMDPIS Report"
    )
    record = ReportRecord(
        title=final_title,
        dataset_id=dataset_id,
        content=payload["sections"],
        markdown=payload["markdown"],
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Audit against the dataset's evidence, if any
    if dataset_id:
        try:
            dataset = dataset_service.get_dataset(db, dataset_id)
            if dataset.evidence_id:
                record_event(
                    db,
                    dataset.evidence_id,
                    "REPORT",
                    {"report_id": record.id, "title": final_title},
                )
        except Exception:
            pass
    return record


def list_reports(db: Session) -> list[ReportRecord]:
    from sqlalchemy import select

    return list(db.scalars(select(ReportRecord).order_by(ReportRecord.created_at.desc())).all())


def get_report(db: Session, report_id: str) -> ReportRecord:
    from app.utils.errors import NotFoundError

    record = db.get(ReportRecord, report_id)
    if not record:
        raise NotFoundError("Report not found.")
    return record
