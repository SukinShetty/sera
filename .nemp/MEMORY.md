# Nemp Memory Index

> Auto-generated. Last updated: 2026-07-14 14:55

## Stored Memories

| Key | Preview | Agent | Updated |
|-----|---------|-------|---------|
| stack | Python 3.14 + Click/Rich CLI + Streamlit UI + Anthropic Claude + matplotlib + Jinja2 + pytest; local-first (JSONL ledger + Obsidian vault), pip | nemp-init | 2026-07-14 |
| sera-project-definition | SERA = local-first Research-as-a-Service OS integrated with Obsidian | main | 2026-05-12 |
| sera-architecture | 5 sessions S0–S4 (foundation/cli/vault/engine/reports); git worktrees | main | 2026-05-12 |
| sera-session-rules | Each session owns its folder; read/update memory; import only from shared/ | main | 2026-05-12 |
| sera-folder-ownership | cli/=S1, vault/=S2, engine/=S3, reports/=S4; shared/ read-only | main | 2026-05-12 |
| sera-shared-api | shared/config (CONFIG, get_path, PROJECT_ROOT), file_io, validators | main | 2026-05-12 |
| sera-cli-contracts | Interfaces CLI expects from engine/reports; degrades gracefully | session-1 | 2026-05-12 |
| sera-vault-api | vault/scaffold.py: create_client_vault(id), list_vaults() | session-2 | 2026-05-12 |
| sera-session-0-complete | Shared foundation shipped; 21 smoke tests | main | 2026-05-12 |
| sera-session-1-complete | Click CLI: vault/hypothesis/experiment/report commands | session-1 | 2026-05-12 |
| sera-session-2-complete | Vault scaffold, 4 JSON schemas, 5 templates | session-2 | 2026-05-12 |
| sera-integration-complete | 79 tests pass; E2E create→hyp→exp→winner→report | main | 2026-05-12 |
| sera-worktrees | 4 session worktrees merged into master | main | 2026-05-12 |
| sera-next-steps | v0.1.0 shipped; install deps, set ANTHROPIC_API_KEY | main | 2026-05-12 |
| runner-integration-session-2026-07-03 | 7c241b8: real subprocess experiment execution + SERA_METRICS | main | 2026-07-03 |
| memory-sessions-p3-p4-2026-07-07 | P3/P4/P6 log; ablation run 2 clean, run-2 harness fixes committed | main | 2026-07-14 |
| instinct-preflight-external-deps | Preflight paid/external deps AND budget the whole run (conf 0.85) | main | 2026-07-13 |
| instinct-structural-failure-forensics | Classify swallowed failures by artifact-presence fingerprints (conf 0.6) | main | 2026-07-13 |
| instinct-verify-claimed-files | Verify "pre-written" artifacts actually exist before acting (conf 0.6) | main | 2026-07-03 |

## Files

| File | Purpose |
|------|---------|
| `memories.json` | All stored memories (rich schema: value, confidence, vitality, links) |
| `access.log` | Read/write/init audit trail |
| `MEMORY.md` | This index file |
