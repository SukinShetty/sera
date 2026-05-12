---
id: {{ id }}
brief_id: {{ brief_id }}
client_id: {{ client_id }}
title: "{{ title }}"
status: {{ status | default("draft") }}
created: {{ created }}
---

# Hypothesis: {{ title }}

> **{{ hypothesis }}**

## Rationale

{{ rationale | default("_No rationale provided._") }}

## Success Metrics

{% if metrics %}
{% for metric in metrics %}
- {{ metric }}
{% endfor %}
{% else %}
_No success metrics defined yet._
{% endif %}

---

**Status:** `{{ status | default("draft") }}`
**Brief:** [[briefs/{{ brief_id }}]]
**Client:** [[clients/{{ client_id }}/_meta]]
