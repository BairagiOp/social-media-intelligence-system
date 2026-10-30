#!/usr/bin/env python3
"""Train the SMDPIS misinformation classification baseline (TF-IDF + LogReg).

Outputs are model classifications with confidence estimates — NOT factual
determinations. Human verification is required for any real-world conclusion.

Usage:
    python ml/training/train_misinformation.py
    python ml/training/train_misinformation.py --target misinfo_label
"""
from common import main

if __name__ == "__main__":
    main(
        "misinformation",
        {
            "target": "misinfo_label",
            "model_type": "logistic_regression",
            "test_size": 0.2,
        },
    )
