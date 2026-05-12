---
id: {{ id }}
experiment_id: {{ experiment_id }}
client_id: {{ client_id }}
winner: {{ winner | lower }}
confidence: {{ confidence | default(0.0) }}
status: {{ status | default("draft") }}
recorded_on: {{ recorded_on }}
---

# Result: {{ id }}

## Outcome

{{ outcome }}

## Data Summary

{{ data_summary | default("_No data summary provided._") }}

## Winner Determination

{% if winner %}
**Winner:** Yes — this experiment met the threshold and is recommended for promotion.
{% else %}
**Winner:** No — this experiment did not meet the winning threshold.
{% endif %}

**Confidence Score:** {{ (confidence * 100) | round(1) }}%

## Analyst Notes

{{ notes | default("_No additional notes._") }}

---

**Status:** `{{ status | default("draft") }}`
**Experiment:** [[experiments/{{ experiment_id }}]]
**Client:** [[clients/{{ client_id }}/_meta]]
