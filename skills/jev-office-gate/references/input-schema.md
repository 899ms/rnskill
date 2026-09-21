# Citation review input

The helper accepts UTF-8 JSON with an `items` array and optional thresholds.

```json
{
  "items": [
    {
      "id": "claim_1",
      "claim": "The statement used in the report.",
      "evidence": "The exact excerpt copied from the source.",
      "source_type": "company_blog",
      "source_title": "Optional source title",
      "source_date": "2026-09-20",
      "source_url": "https://example.com/source"
    }
  ],
  "thresholds": {
    "support": 0.7,
    "risk": 0.6,
    "min_disposition_confidence": 0.5,
    "reject_probability": 0.8,
    "require_formal_source": true
  }
}
```

`claim` and `evidence` are required. Include `source_type` when the source's authority affects publication. The URL and metadata are context, not proof that the page exists or contains the excerpt.

## Commands

Build and inspect the request without calling Jev:

```bash
python3 scripts/jev_office_gate.py input.json --dry-run
```

Call Jev using `TYPESAFE_API_KEY`:

```bash
python3 scripts/jev_office_gate.py input.json --output review.json
```

Re-evaluate a saved API response without another paid call:

```bash
python3 scripts/jev_office_gate.py input.json --response-file response.json --output review.json
```

The output contains `decisions` and the raw response. `pass` means the configured automated rules did not fire; it does not certify truth. `manual_review` means at least one threshold, confidence, or disposition rule fired. `reject` is reserved for a high-probability contradiction or `cannot_use` result.
