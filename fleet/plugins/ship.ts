import { Plugin } from "@opencode/plugin"

const SHIP_PROMPT =
  "Load the ship skill by ID ship (frontmatter name Ship) via the skill tool and follow it. You are Cal. A normal /ship authorizes the routine staged-only workflow through non-prod deploy, full E2E, push and opening a PR, with no routine approval stops. Delegate the operational script steps to Worker in the background: Worker inspects the GitHub remote identity and current branch and derives the verified destination via ship-destination (explicit prior instructions, upstream, main tracking, or single remote; stop on ambiguous or conflicting destinations), surfaces staged scope and outgoing commits without reconfirming routine cases, and uses the repository's configured non-prod target and lease mechanism (busy or unverifiable required lease is a specific blocker). Stop only on a blocker, scope surprise, repo policy, authority limit, failed gate, or tool denial. Return the evidence SHAs. Do not run the scripts directly. Do not merge."

export default Plugin.define({
  id: "fleet.ship",
  async setup(ctx) {
    const existing = await ctx.command.list()
    const commands = Array.isArray(existing)
      ? existing
      : ((existing as { data?: Array<{ name: string }> }).data ?? [])
    if (commands.some((command) => command.name === "ship")) return

    await ctx.command.transform((editor) => {
      editor.add({
        name: "ship",
        description:
          "Ship a staged change through Husky gates, nested non-prod deploy and E2E, then an open PR for review",
        execute: async ({ sessionID, prompt, delivery }) => {
          const args = prompt.text.trim()
          if (args !== "") {
            await ctx.session.synthetic({
              sessionID,
              text: "Ship command takes no arguments. Run /ship with no trailing arguments, or load the ship skill explicitly (for example @ship with no arguments). No prompt was admitted and no repository operation was run.",
            })
            return
          }
          const session = await ctx.session.get({ sessionID })
          if (session.agent !== "cal") {
            await ctx.session.synthetic({
              sessionID,
              text: "The ship command must run in a Cal session. Select the Cal primary agent and run /ship again. The agent was not switched and no repository operation was run.",
            })
            return
          }
          await ctx.session.prompt({
            ...prompt,
            sessionID,
            text: SHIP_PROMPT,
            delivery,
          })
        },
      })
    })
  },
})
