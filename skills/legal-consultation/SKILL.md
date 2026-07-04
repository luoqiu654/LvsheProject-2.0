---
name: legal-consultation
description: Provide a structured legal consultation answer by combining intent analysis, legal knowledge search, contract risk review, calculation, and final summarization. Use this skill when the user asks a general legal consultation question.
license: MIT
compatibility: LvsheProject local Python backend, uses LangGraph LegalAgent.
metadata:
  author: Yifan Cai
  version: "0.1.0"
---

# Legal Consultation Skill

## Purpose

Use this skill to provide a structured legal consultation answer.

## When to Use

Use this skill when the user asks a general legal question and may need:

- legal knowledge search
- contract risk review
- simple calculation
- practical suggestions

## Workflow

1. Understand the user's question.
2. Decide whether to search the knowledge base, review contract risk, calculate an amount, or answer directly.
3. Use the appropriate tool.
4. Generate a concise and practical final answer.
5. Remind the user to consult a professional lawyer for complex disputes.

## Output Format

Return:

1. conclusion
2. reasoning
3. tool result or legal basis
4. practical next steps
5. disclaimer
