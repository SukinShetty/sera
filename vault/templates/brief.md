---
title: "{{ title }}"
client_id: {{ client_id }}
status: {{ status | default("draft") }}
created: {{ created }}
---

# Research Brief: {{ title }}

## Objective

{{ objective }}

## Background

{{ background | default("_No background provided._") }}

## Target Audience

{{ target_audience | default("_Not specified._") }}

## Research Questions

{% if research_questions %}
{% for question in research_questions %}
{{ loop.index }}. {{ question }}
{% endfor %}
{% else %}
_No research questions defined yet._
{% endif %}

## Timeline

{{ timeline | default("_Not specified._") }}

---

**Status:** `{{ status | default("draft") }}`
**Client:** [[clients/{{ client_id }}/_meta]]
