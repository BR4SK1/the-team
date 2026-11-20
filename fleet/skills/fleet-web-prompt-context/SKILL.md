---
name: fleet-web-prompt-context
description: Context for a user prompt delivered through the authenticated OpenCode web client.
metadata:
  opencode/autoinvoke: false
---

For this prompt, the user is interacting through the web client and has no terminal available to them. The user expects you to run commands and provide output. You should not assume that the user has access to a terminal or can run commands themselves. You continue with your normal agent behavior, and this skill does not change your behavior in any way. It is simply a context for how the user is interacting with you at this time.
