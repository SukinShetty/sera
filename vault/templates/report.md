---
client_id: {{ client_id }}
title: "{{ title }}"
generated_on: {{ generated_on }}
format: {{ format | default("markdown") }}
---

# Research Report: {{ title }}

**Client:** {{ client_id }}
**Generated:** {{ generated_on }}

---

## Executive Summary

{{ executive_summary | default("_Summary to be written._") }}

---

## Research Questions

{% if research_questions %}
{% for question in research_questions %}
{{ loop.index }}. {{ question }}
{% endfor %}
{% else %}
_No research questions recorded._
{% endif %}

---

## Hypotheses Tested

{% if hypotheses %}
{% for h in hypotheses %}
### {{ loop.index }}. {{ h.title }}

> {{ h.hypothesis }}

**Outcome:** {{ h.outcome | default("_Pending_") }}
**Status:** `{{ h.status }}`

{% endfor %}
{% else %}
_No hypotheses recorded._
{% endif %}

---

## Winning Experiments

{% if winners %}
{% for w in winners %}
### {{ loop.index }}. {{ w.title }}

**Confidence:** {{ (w.confidence * 100) | round(1) }}%

{{ w.outcome }}

{% endfor %}
{% else %}
_No winning experiments identified._
{% endif %}

---

## Recommendations

{% if recommendations %}
{% for rec in recommendations %}
{{ loop.index }}. {{ rec }}
{% endfor %}
{% else %}
_Recommendations to be added._
{% endif %}

---

## Appendix

_Raw experiment data and detailed result logs available in:_
- `[[clients/{{ client_id }}/experiments/]]`
- `[[clients/{{ client_id }}/results/]]`
