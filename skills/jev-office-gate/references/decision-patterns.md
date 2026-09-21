# Narrow decision patterns

Use these patterns only after deterministic checks. Each question should control one decision.

## Requirement coverage

State: one requirement plus the relevant deliverable excerpt or cell range.

Choice:

- `met`: the excerpt fully satisfies the requirement
- `partial`: some material part is missing
- `not_met`: the requirement is not satisfied
- `manual_review`: the excerpt is insufficient to decide

Do not ask Jev to decide whether a file actually opens, a formula calculates, or a slide overlaps; inspect those directly.

## Evidence disposition

State: claim, exact source excerpt, source type, title, and date.

Choice:

- `formal_source`
- `side_evidence`
- `cannot_use`
- `manual_review`

Separate source authority from claim support. An official company post can support “the company announced X” while remaining self-disclosure for the underlying business metric.

## Triage priority

State: one flagged issue and its known impact.

Choice:

- `block_release`
- `review_before_release`
- `fix_when_convenient`
- `ignore`

Use deterministic policy to override Jev for mandatory requirements. Do not ask Jev to make legally binding, medical, financial, personnel, or compliance approvals.

## Avoid compound questions

Bad: “Is this source current, authoritative, accurate, and safe to publish?”

Better:

1. Check the date with code.
2. Classify source type from known metadata.
3. Ask whether the excerpt supports the claim.
4. Ask whether the wording overstates the excerpt.
5. Route low-confidence or consequential items to a human.
