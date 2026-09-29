---
name: constrained-search
description: Build public-source queries from confirmed anchors and prevent broad same-name results from becoming facts.
---

# Constrained Search

Use this workflow before search, news, social, registry, directory, or profile lookup.

## Steps

1. Extract confirmed anchors: exact name, company field, country, city, platform, website, email, phone, purchase category, dates, and operator notes.
2. Search from strongest to weakest combinations:
   - exact company or person plus country
   - exact company or person plus platform
   - exact company or person plus business context
   - website, email, or phone plus company name
   - alternate names plus country and business context
3. Exclude obvious same-name noise such as unrelated sports, entertainment, crime, music, or public-figure results.
4. Record broad hits as review notes, not facts.
5. Promote only hits tied to the subject by a strong anchor or by multiple independent weaker anchors.

## Output Discipline

Every search-derived result must explain which anchor made it relevant. If that explanation is weak, keep the result as a candidate.
