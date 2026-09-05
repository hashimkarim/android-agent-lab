# Discovery and remote execution

Link one canonical skill into `~/.codex/skills/adb-coordination`,
`~/.claude/skills/adb-coordination`, and, where used by the provider,
`~/.agents/skills/adb-coordination`. Keep existing installations until their
contents are reviewed. All copies can share the same claim registry, but one
canonical copy makes updates easier.

- Codex: request `$adb-coordination` or coordinated Android testing.
- Claude Code: request `/adb-coordination` or coordinated Android testing.
- T3 Code: use the selected provider's skill support. If unavailable, ask the
  thread to read this skill's `SKILL.md` by absolute path. Do not invent a
  T3-specific slash command or session-ID API.

Refresh the provider session when a newly installed skill is missing. Give
the agent the lab checkout path for Docker operations.

For a remote agent, install and run the helper on the ADB host under the same
user as other cooperating agents. Run commands there over an existing SSH
connection. Copying claim files between machines does not provide distributed
locking, and NFS is not a supported coordination backend.

For a browser on another computer, forward the web port:

```bash
ssh -N -L 8765:127.0.0.1:8765 user@emulator-host
```

Open `http://127.0.0.1:8765/vnc.html?autoconnect=true&resize=scale` locally. Run
agent ADB commands on the remote host to keep claims and device access together.
If T3's preview backend runs remotely, the URL must be reachable by that backend,
not just by the user's desktop browser. Native preview tooling may forward
environment ports; inspect the tools available in the current client.

Sources checked 2026-09-05:
- [Codex skills](https://developers.openai.com/codex/skills/)
- [Claude Code skills](https://code.claude.com/docs/en/skills)
- T3 Code's runtime-provided `preview_open`, `preview_navigate`, and
  `preview_snapshot` tool descriptions.
