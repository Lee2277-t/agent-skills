# Safety And Release Notes

## Privacy

- Do not scan arbitrary home, `.ssh`, `.codex`, `.claude`, keychain, browser profile, or unrelated private folders.
- The bundled engine skips sensitive filenames and high-risk roots, but Codex should still keep user intent narrow and use explicit project paths.
- Never publish raw local optimization logs, cache JSON, real customer project files, phone numbers, order IDs, cloud file IDs, AppSecret, SecretKey, cookies, tokens, or private config.

## Security Scan Output

`miniapp_security_quick_scan` is a static quick scan. It is useful before release, but it is not a replacement for a manual security audit or WeChat/CloudBase permission review.

When reporting results:

- Include path, line, rule, severity, and fix direction.
- Avoid copying raw secret-like values.
- Prioritize cloud storage privacy, database rules, sensitive logs, internal route exposure, test leftovers, and environment boundary mistakes.

## CloudBase And WeChat Release

- Use official WeChat DevTools, miniprogram-ci, CloudBase CLI, or official CloudBase MCP for real deploy/upload operations.
- Keep `requireHumanConfirm:true` for production actions.
- Verify the exact version from WeChat DevTools or the public platform before release notes, upload, or any artifact sharing step.
- For customer private albums, confirm access control, revoke flow, privacy policy wording, and audit material before review.

## Public Sharing Boundaries

- Do not publish this package to GitHub, npm, or any public registry unless the maintainer explicitly requests that external action.
- If public sharing is later approved, first run `node --check scripts/miniapp_engineering_cli.mjs`, `npm run smoke:test`, `node scripts/miniapp_engineering_cli.mjs quick_validate`, and a sensitive-content review.
- Keep the original MCP engine under `assets/mcp-server/` for compatibility and traceability, but route normal users through `scripts/miniapp_engineering_cli.mjs`.
