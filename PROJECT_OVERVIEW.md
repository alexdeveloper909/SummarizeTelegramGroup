# Project Overview

This repository is an automation-friendly workspace for generating daily reports from Telegram groups or channels. The intended runtime is an AI coding agent or agent CLI that can execute local scripts, inspect stored message data, optionally perform web research for deeper context, and produce a concise morning report.

The current repository includes a first working version of the local pipeline: Telethon auth/bootstrap, SQLite-backed collection and staging, summary-input preparation, report persistence, retry-safe finalization, and supporting test coverage.

The near-term optimization direction is to keep summarization selective without hard-coding domain-specific heuristics into the preparation step.
The current reporting flow now includes a dedicated report-writing brief so the summarizer can start from a clear generic contract before reading the full message chronology.
The preferred operator path now uses one orchestration step to generate both the summary bundle and the report-writing brief together.

## Documentation Map

- [README.md](README.md): short project entry point
- [docs/specification.md](docs/specification.md): authoritative product and implementation specification
- [user_guide.md](user_guide.md): human setup, auth, execution, and troubleshooting guide
- [AGENTS.md](AGENTS.md): agent-facing operating instructions for this repository
- [docs/architecture.md](docs/architecture.md): component and storage design
- [docs/operations.md](docs/operations.md): retries, cleanup, and maintenance runbook
- [docs/prompts.md](docs/prompts.md): summarization prompt and report contract

## Implemented Deliverables

- Python scripts using Telethon to collect Telegram messages
- SQLite storage for per-run message staging and report metadata
- Agent-friendly scripts and prompts for summarization and report writing
- A report workflow that favors high-signal items over raw chronological replay
- Cleanup and read-state handling so each automation run finishes in a consistent state
- Documentation that supports both human operators and automation agents

## Working Principles

- Keep raw Telegram data local to the repository runtime and minimize retention
- Design for concurrent automation runs across multiple Telegram targets
- Separate data collection from summarization so collection can be tested independently
- Optimize the summarization stage for highlighting signal over exhaustive recap
- Prefer explicit run identifiers and target identifiers over implicit global state
- Keep Telegram secrets in environment variables or local ignored env files such as `.secrets/telegram.env`
- Allow auth bootstrap to source the Telegram phone number from local config to reduce interactive setup friction
- Allow auth bootstrap to source the Telegram 2FA password from local config when two-step verification is enabled

## Next Document to Read

Read [docs/specification.md](docs/specification.md) before changing code. It contains the architecture, data model, operational workflow, and phased checklist used as the source of truth for this repository.
