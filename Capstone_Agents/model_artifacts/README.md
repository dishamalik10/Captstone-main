# CNN artifacts

Place the trained deployment artifacts in this directory:

```text
fashion_cnn_final.keras
fashion_cnn.metadata.json
```

The `.keras` file is intentionally ignored by Git because model binaries should
be delivered through release artifacts or model storage. The metadata JSON must
retain the exact class order used during training.
