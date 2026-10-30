#!/usr/bin/env python3
"""Train the SMDPIS sentiment classification model.

Steps: load -> validate schema -> preprocess -> split -> train -> evaluate
       -> save metrics -> save model -> print results

Usage:
    python ml/training/train_sentiment.py                 # sample dataset
    python ml/training/train_sentiment.py --dataset <ID>  # registered dataset
    python ml/training/train_sentiment.py --dataset data/sample/smdp_posts.csv
"""
from common import main

if __name__ == "__main__":
    main(
        "sentiment",
        {
            "target": "label",
            "model_type": "logistic_regression",
            "test_size": 0.2,
        },
    )
