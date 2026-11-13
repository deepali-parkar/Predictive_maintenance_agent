# SENTINEL Evaluation Report

## Detection - held-out (final)
```json
{
  "assets": [
    "PMP-108",
    "PMP-107",
    "MTR-207",
    "CMP-302"
  ],
  "point_level": {
    "tp": 1416,
    "fp": 63,
    "fn": 140,
    "tn": 9889,
    "precision": 0.9574,
    "recall": 0.91,
    "f1": 0.9331,
    "false_positive_rate": 0.0063,
    "false_negative_rate": 0.09
  },
  "by_sensor": {
    "current": {
      "tp": 264,
      "fp": 0,
      "fn": 72,
      "tn": 2541,
      "precision": 1.0,
      "recall": 0.7857,
      "f1": 0.88,
      "false_positive_rate": 0.0,
      "false_negative_rate": 0.2143
    },
    "pressure": {
      "tp": 237,
      "fp": 0,
      "fn": 46,
      "tn": 2594,
      "precision": 1.0,
      "recall": 0.8375,
      "f1": 0.9115,
      "false_positive_rate": 0.0,
      "false_negative_rate": 0.1625
    },
    "temperature": {
      "tp": 579,
      "fp": 16,
      "fn": 22,
      "tn": 2260,
      "precision": 0.9731,
      "recall": 0.9634,
      "f1": 0.9682,
      "false_positive_rate": 0.007,
      "false_negative_rate": 0.0366
    },
    "vibration": {
      "tp": 336,
      "fp": 47,
      "fn": 0,
      "tn": 2494,
      "precision": 0.8773,
      "recall": 1.0,
      "f1": 0.9346,
      "false_positive_rate": 0.0185,
      "false_negative_rate": 0.0
    }
  },
  "event_level": {
    "degrading_assets": 3,
    "detected": 3,
    "event_recall": 1.0,
    "healthy_assets": 1,
    "healthy_false_alarms": 0,
    "mean_lead_time_h": 534.0,
    "mean_delay_vs_label_onset_h": 0.3
  }
}
```

## Detection - dev (development only)
```json
{
  "point_level": {
    "tp": 2851,
    "fp": 120,
    "fn": 265,
    "tn": 42748,
    "precision": 0.9596,
    "recall": 0.915,
    "f1": 0.9368,
    "false_positive_rate": 0.0028,
    "false_negative_rate": 0.085
  },
  "event_level": {
    "degrading_assets": 8,
    "detected": 8,
    "event_recall": 1.0,
    "healthy_assets": 8,
    "healthy_false_alarms": 0,
    "mean_lead_time_h": 486.1,
    "mean_delay_vs_label_onset_h": 7.1
  }
}
```

## RAG retrieval
_not run yet (`rag_eval.json` missing)_

## Agent / citations / governance / routing cost
_not run yet (`agent_eval.json` missing)_
