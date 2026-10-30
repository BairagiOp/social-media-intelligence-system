#!/usr/bin/env python3
"""Train the SMDPIS automated-account (bot) detection model.

Steps: load -> validate schema -> account-level feature engineering -> split
       -> train -> evaluate -> save metrics -> save model -> print results

Usage:
    python ml/training/train_bot_detection.py
    python ml/training/train_bot_detection.py --model-type gradient_boosting
"""
from common import main

if __name__ == "__main__":
    main(
        "bot_detection",
        {
            "target": "is_automated",
            "model_type": "random_forest",
            "test_size": 0.2,
        },
    )
