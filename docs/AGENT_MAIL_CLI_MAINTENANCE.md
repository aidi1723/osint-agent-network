# Agent Mail CLI Maintenance

This note records the local Agent Mail CLI setup for future maintenance. It intentionally does not include OAuth tokens, device codes, keychain records, or other secrets.

## Current Authorization

- Service: Agent Mail / Agently CLI
- Authorized email: `yizijue@agent.qq.com`
- Primary alias name: `yizijue`
- Primary alias id: `alias_2w6WVE-3U1vXSVtGJPGYVp15fUGZ3FOS`
- Verified on: `2026-06-26`
- Token storage: system keychain, managed by `agently-cli`
- Installed CLI: `@tencent-qqmail/agently-cli@1.0.6`
- CLI binary: `/opt/homebrew/bin/agently-cli`
- Global npm modules: `/opt/homebrew/lib/node_modules`
- Installed skill: `~/.agents/skills/agently-mail`

## Granted Scopes

The current OAuth grant returned these scopes:

- `alias:read`
- `mail:read`
- `mail:send`
- `mail:delete`

## Service Limits

Current limits returned by `agently-cli +me`:

- Daily send quota: `50`
- Requests per hour: `200`
- Requests per minute: `10`
- Max attachment count: `50`
- Max single attachment size: `20 MiB`
- Max total attachment size: `20 MiB`

## Verify Authorization

Run:

```bash
agently-cli +me
```

Expected result:

- JSON has `"ok": true`
- `data.aliases[0].email` is `yizijue@agent.qq.com`

If Codex sandboxing reports `keychain not initialized`, rerun the command with elevated host access so the CLI can read the system keychain.

## Install Or Update

Official setup document:

```text
https://agent.qq.com/doc/cli-setup.md
```

Update the CLI:

```bash
npm install -g @tencent-qqmail/agently-cli
```

Install or update the common Agent skill:

```bash
npx skills add https://agent.qq.com --skill -g -y
```

The skill installer may print `PromptScript does not support global skill installation`. That warning is acceptable as long as it also reports `agently-mail` installed under `~/.agents/skills/agently-mail` for Codex-compatible agents.

## Reauthorize

Run:

```bash
agently-cli auth login
```

The command prints an OAuth URL. Open that exact URL in a browser and complete authorization. After authorization, the command should exit with:

```text
OK: 认证成功
```

Then verify:

```bash
agently-cli +me
```

Do not paste or store OAuth URLs, device codes, tokens, or keychain exports in project files.

## Common Operations

List recent messages:

```bash
agently-cli message +list
```

Show the authorized account:

```bash
agently-cli +me
```

Use the installed `agently-mail` skill for natural-language mail workflows such as sending, reading, replying, forwarding, searching, downloading attachments, and inbox management.

## Troubleshooting

- `failed to reach auth server` or DNS errors: check network access to `auth.agent.qq.com`, then rerun the OAuth flow once.
- `keychain not initialized`: the CLI cannot access the system keychain from the current execution context; run from the normal user shell or allow host-level keychain access.
- `Authorization required`: run `agently-cli auth login` and complete browser authorization.
- npm registry errors while installing `skills`: rerun with normal network access and confirm npm can reach the configured registry.

