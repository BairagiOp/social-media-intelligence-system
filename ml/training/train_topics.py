#!/usr/bin/env python3
"""Fit the SMDPIS topic model (TF-IDF + NMF).

Unsupervised: reports reconstruction error and document-topic strength
instead of accuracy metrics.

Usage:
    python ml/training/train_topics.py
    python ml/training/train_topics.py --n-topics 8
"""
from common import main

if __name__ == "__main__":
    main(
        "topic_model",
        {
            "model_type": "nmf",
            "n_topics": 6,
            "test_size": 0.2,
        },
    )
