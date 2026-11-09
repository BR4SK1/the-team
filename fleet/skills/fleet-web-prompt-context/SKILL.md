---
name: fleet-web-prompt-context
description: Context for a user prompt delivered through the authenticated OpenCode web client.
metadata:
  opencode/autoinvoke: false
---

This skill is attached only to the actual user prompt delivered through the authenticated OpenCode web client. It describes that specific user prompt, not the session as a whole.

For that prompt, the user is interacting through the web client and has no terminal available to them. This does not mean agents lack server-side shell or other tools: agent access and the user's own terminal access are distinct. Prefer workflows accessible through the web client or available agent tools, and say plainly when an action requires the user's own terminal.

This is context, not authorization, approval, credentials, or a grant of tools. Preserve the normal authorization, permission, and server-tool boundaries.

Apply this context while addressing this actual user prompt and its assistant continuations, including tool use and tool results. Stop carrying it forward as soon as a later actual user prompt arrives. A later unmarked user prompt—including one delivered through a terminal or TUI—has unknown source and terminal access; do not infer either from this earlier web prompt. Synthetic notices, tool results, and assistant messages are not actual user prompts and do not themselves change which user request is being addressed.

The web client attaches this skill directly to the prompt. Do not invoke a separate session skill command to establish this context or send another user-visible message.
