# M3 25-pair pilot

Date: 2026-08-13

## Scope

The deterministic pilot covered 25 generated schema-instance pairs across three
engines, four tokenizers, and all three conformance properties.

| Parameter | Value |
|---|---:|
| Pair seed | 20260813 |
| Maximum schema depth | 3 |
| Alternate tokenizations | 4 |
| Tokenization search states | 512 |
| Soundness walks per schema | 20 |
| Soundness maximum tokens | 32 |
| Viability lookahead depth | 4 |
| Viability candidates | 16 |
| Viability branch limit | 64 |

## Classification

Occurrence records were deduplicated by conceptual cause. The pilot identified five
distinct classes. Repeated records across schemas and tokenizers do not increase this
count.

| Property | Engine scope | Distinct cause | Status |
|---|---|---|---|
| Completeness | XGrammar and llguidance | Numeric bounds constrain decimal spelling instead of represented value | Existing class, finding 006 |
| Completeness | Pilot samples | Equivalent escaped spellings of schema-fixed strings are excluded | Existing class, finding 005 |
| Completeness | Pilot samples | Object member reachability follows schema declaration order | Existing class, finding 004 |
| Soundness | Outlines | Standard numeric value constraints compile but are not enforced | Known M3 class |
| Soundness | XGrammar | Constrained string compilation loses JSON lexical exclusions | New class, finding 007 |

The retained aggregate does not preserve a witness-to-engine mapping for every
completeness occurrence. The report therefore records the confirmed conceptual
classes without inventing per-engine attribution. Future persisted runs should keep
that mapping.

No viability cause was found. This is a bounded pilot result, not proof of absence.

## Tokenizer context warnings

Mistral canonical records at token index 0 are kept separate from findings. The same
initial-token behavior appeared with all three engines, which identifies a standalone
tokenizer-context mismatch rather than three engine causes.

The three Mistral completeness searches that exhausted the configured enumeration
budget are inconclusive coverage records. They are not findings.

## Conclusion

The pilot added two M3 soundness classes and revisited three known completeness
classes. Counts in the original execution matrix measure occurrences and coverage;
the classified result is five distinct causes, with Mistral index-0 records reported
only as tokenizer-context warnings.
