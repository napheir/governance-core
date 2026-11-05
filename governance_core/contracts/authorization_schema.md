# Contract: Authorization Code, Storage & Revocation Feed

**Version**: 1.0.0
**Status**: active
**Owner**: core
**Consumers**: `governance_core/installer.py` (install gate, doctor),
`governance_core/hooks/auth-guard.py` (runtime gate, via the vendored
`.claude/hooks/_gc_auth/`), `governance_core/tools/candidate.py` (uplink origin
binding), `maintainer/issue_auth_code.py`, `maintainer/revoke_consumer.py`.

Defines the maintainer-issued authorization code, where a project stores it,
and the signed revocation feed that can withdraw it (P-0065, P-0071, P-0132).
Implementations: `governance_core/auth/codec.py`, `auth/store.py`,
`auth/revocation.py`.

## 1. Code format

One copy-pasteable line:

    GC1.<b64url(payload_json)>.<b64url(signature)>

`payload_json` is canonical JSON (`sort_keys=True`, separators `,` `:`, UTF-8);
`signature` is the Ed25519 signature over those exact bytes, verified with the
public key bundled in the package (`governance_core/auth/pubkey.json`).

### 1.1 Payload (schema 2 -- the only accepted schema)

| field | type | meaning |
|-------|------|---------|
| `schema` | int | `2` |
| `consumer_id` | str | stable identity of the consuming project/org (not secret) |
| `issued` | `YYYY-MM-DD` | issue date |
| `expiry` | `YYYY-MM-DD` | the code stops verifying after this date |
| `revocation_feed_url` | str | the signed feed `auth-guard` polls (§3) |
| `max_offline_days` | int > 0 | freeze after this many days without a successful feed fetch |

**Schema 1 is retired (0.49.0, P-0132).** It had no `expiry` and no feed, so a
schema-1 code never expired and skipped the revocation gate. Clients from
0.49.0 reject it at install and at runtime.

### 1.2 Fingerprint

`code_fingerprint(code) = sha256(code.strip().encode("utf-8")).hexdigest()` --
64 lowercase hex characters. It identifies one code in the revocation feed;
publishing it does not reveal the code.

## 2. Storage

| location | content | git |
|----------|---------|-----|
| `.governance/auth_code` | the code, one line, LF-terminated | **ignored** (installer-managed `.gitignore` block) |
| `.governance/config.json` `authorization.consumer_id` | the code's consumer_id | tracked |
| `.governance/config.json` `authorization.verified_at` | ISO-8601 Z time of the last successful verification | tracked |

- The installer writes `.governance/auth_code` atomically (temp file +
  `os.replace`). `auth-guard`, `doctor` and `candidate.py` read only this file.
- **Opting into git (private repositories only):** a project that wants every
  clone to receive the code through git adds `!/.governance/auth_code` *after*
  the managed block; the installer never edits lines outside the block. doctor
  notes the file is tracked.
- **Retired location:** `config.json` `authorization.auth_code` (before 0.49.0).

### 2.1 Migration from config.json

1. `governance-core upgrade` resolves the code from `--auth-code`, else
   `.governance/auth_code`, else the retired `authorization.auth_code` -- the
   last only as a migration source -- and writes `.governance/auth_code`.
2. The config.json copy is **kept** until the owner runs
   `governance-core upgrade --remove-config-auth-code`. In a multi-clone project
   config.json is tracked and merged into every clone, and a clone still on a
   version before 0.49.0 reads its code from there: remove the copy only after
   every clone runs 0.49.0 or later. doctor warns while the copy exists.
3. Newer versions never write `authorization.auth_code`.

## 3. Revocation feed

Two files at the URL in the code: `revocation.json` and `revocation.json.sig`
(b64url Ed25519 signature over the exact bytes of `revocation.json`, same key
as the codes).

    {"schema": 1, "updated": "<ISO-8601 Z>",
     "revoked": [{"consumer_id": str, "revoked_on": "YYYY-MM-DD",
                  "reason": str, "code_sha256"?: "<64 hex>"}, ...]}

| entry | revokes (0.49.0+) | revokes (before 0.49.0) |
|-------|-------------------|-------------------------|
| without `code_sha256` | every code of `consumer_id` | every code of `consumer_id` |
| with `code_sha256` | only the code with that fingerprint | every code of `consumer_id` |

- Every entry carries a non-empty `consumer_id`: clients before 0.49.0 reject
  a feed containing an entry without one (and would then treat the feed as
  unreachable and freeze after `max_offline_days`).
- Because old clients read a per-code entry as consumer-wide, re-issue the
  consumer's replacement code and upgrade the consumer **before** publishing a
  per-code entry for one of its codes.
- `code_sha256`, when present, is 64 lowercase hex characters; any other value
  makes the feed invalid.
- Un-revoking a consumer (`--unrevoke`) removes only its consumer-wide entry;
  per-code entries stay until `--unrevoke-code`.

### 3.1 Enforcement points

- **install / upgrade:** verifies the code offline, then fetches the feed once
  (short timeout). A code that is revoked exits 7. A feed that cannot be fetched
  or verified does not block install.
- **auth-guard (every tool call):** verifies the code (daily cache), then
  evaluates the feed (fetch at most every 6 hours), blocking on a consumer-wide
  or per-code match, or once no fetch succeeded for `max_offline_days`.

## 4. Versioning

| version | change |
|---------|--------|
| 1.0.0 | First version of this contract (0.49.0, P-0132): schema 1 retired, storage moved to `.governance/auth_code`, per-code `code_sha256` feed entries. Code schema 2 and feed schema 1 unchanged on the wire. |
