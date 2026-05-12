---
id: {{ id }}
hypothesis_id: {{ hypothesis_id }}
client_id: {{ client_id }}
title: "{{ title }}"
methodology: {{ methodology }}
status: {{ status | default("pending") }}
created: {{ created }}
---

# Experiment: {{ title }}

## Methodology

{{ methodology }}

## Variables

| Role | Variable |
|------|----------|
| **Independent** | {{ independent_variable | default("_Not defined_") }} |
| **Dependent** | {{ dependent_variable | default("_Not defined_") }} |
| **Control** | {{ control_variable | default("_Not defined_") }} |

## Expected Outcome

{{ expected_outcome | default("_No expected outcome specified._") }}

## Notes

_Add experiment notes here._

---

**Status:** `{{ status | default("pending") }}`
**Hypothesis:** [[hypotheses/{{ hypothesis_id }}]]
**Client:** [[clients/{{ client_id }}/_meta]]
