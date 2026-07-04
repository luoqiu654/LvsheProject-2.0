---
name: contract-risk-review
description: Review contract clauses and identify common legal risks, including missing breach liability, unclear delivery time, dispute resolution, termination, payment, and party information. Use this skill when the user asks to review or improve contract text.
license: MIT
compatibility: LvsheProject local Python backend, rule-based MVP with optional LLM summarization.
metadata:
  author: Yifan Cai
  version: "0.1.0"
---

# Contract Risk Review Skill

## Purpose

Use this skill to review contract text and identify common legal risks.

## When to Use

Use this skill when the user provides:

- a contract clause
- a draft agreement
- project cooperation terms
- service contract text
- lease contract text
- labor-related agreement text

Typical user intents:

- "帮我审查这个合同"
- "这个条款有什么风险"
- "这份协议哪里要改"
- "合同缺少什么内容"

## Review Checklist

Read `references/review_checklist.md` for detailed review items.

Core checks:

1. contract parties
2. subject matter
3. payment amount and payment time
4. delivery or performance deadline
5. acceptance criteria
6. breach liability
7. dispute resolution
8. termination clause
9. intellectual property, if relevant
10. confidentiality, if relevant

## Output Format

Return:

1. overall risk level
2. detected risks
3. missing clauses
4. suggested revisions
5. lawyer consultation reminder

## Safety Notes

Do not claim to replace a lawyer.
Do not fabricate exact legal article numbers.
If the contract text is incomplete, explicitly mention the limitation.
