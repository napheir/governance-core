# maintainer/

Maintainer-only tooling for governance-core authorization (P-0065 Phase 1).

This directory is **committed** to the repo (for auditability) but is
**excluded from the pip package** — `packages.find` matches only
`governance_core*`, and there is no `MANIFEST.in` adding top-level
directories, so `maintainer/` never reaches a wheel or sdist.

## Files

| File | Purpose |
|------|---------|
| `gen_signing_key.py` | One-time: generate the Ed25519 signing keypair. |
| `issue_auth_code.py` | Issue a signed authorization code for one consumer. |

## The signing key

`gen_signing_key.py` writes the **private** signing key to
`~/.governance-core/signing_key.json` — deliberately **outside the repo
tree** so it can never be committed by accident. The matching **public** key
is written to `governance_core/auth/pubkey.json`, which *is* committed and
ships inside the package so consumers verify codes offline.

Back up the private key offline. It cannot be recovered, and it signs every
authorization code. If it leaks, rotate: regenerate the keypair and publish
a new package version carrying the new public key.

## Usage

```sh
# once
python maintainer/gen_signing_key.py

# per consumer
python maintainer/issue_auth_code.py --consumer-id acme-project
```

The printed `GC1.<...>.<...>` string is the authorization code. Deliver it
to the project owner out-of-band; they run
`governance-core install --auth-code <CODE>`.
