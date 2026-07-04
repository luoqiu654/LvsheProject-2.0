---
name: law-search
description: Search the local legal knowledge base for contract, breach, deposit, lease, labor, compensation, and civil law questions. Use this skill when the user asks for legal basis, relevant rules, or knowledge-base-backed answers.
license: MIT
compatibility: LvsheProject local Python backend, requires ChromaDB indexed legal documents.
metadata:
  author: Yifan Cai
  version: "0.1.0"
---

# Law Search Skill

## Purpose

Use this skill to search the local legal knowledge base and retrieve relevant legal context.

## When to Use

Use this skill when the user asks about:

- contract formation
- contract validity
- breach of contract
- damages and compensation
- deposit and liquidated damages
- lease contracts
- labor contract risks
- legal basis or legal explanation

## Workflow

1. Rewrite the user question into a concise legal search query.
2. Search the local RAG knowledge base.
3. Return relevant context with source information.
4. Do not fabricate legal article numbers.
5. If the knowledge base is insufficient, clearly state that the current knowledge base is insufficient.

## Output Format

Return:

1. brief conclusion
2. retrieved basis
3. source references
4. practical reminder

## Safety Notes

This skill provides legal information, not formal legal representation.
For complex disputes, recommend consulting a licensed lawyer.
