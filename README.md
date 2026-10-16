# Ask: Claude in the Parsec launcher

A [Parsec](https://github.com/abidibo/parsec) plugin. Ask Claude a quick
question, or fix the text you just copied, without leaving what you're doing.

| Type | What happens |
|---|---|
| `ask how do I undo a pushed commit` | Enter asks Claude; the answer appears as it's written. Enter copies it, Tab pastes it. |
| `fix` | Fixes spelling, grammar and punctuation of the copied text. Enter pastes the result over your selection, Tab copies it. |
| `fix more formal` | Applies your instruction to the copied text instead. |
| `fix in English` | ...including translating it. |

The usual flow for `fix`: select the text you're writing, Ctrl+C, open Parsec,
type `fix`, Enter to see the result, Enter again to paste it back.

It runs [Claude Code](https://claude.com/claude-code) in headless mode
(`claude -p`), so it uses your Claude plan, not API credits. Nothing is
called while you type: Claude only runs when you press Enter, and pressing
Esc or closing the launcher stops it.

## Requirements

- Parsec 1.4.0 or later (slow answers and clipboard access for plugins)
- Claude Code, logged in: run `claude` once in a terminal
- Python 3.8+

## Install

```sh
parsec plugin install https://github.com/abidibo/parsec-ask
```

## Configuration

`~/.local/share/parsec/plugins/ask/plugin.toml`:

```toml
[config]
model = "sonnet"    # Claude Code model: sonnet, haiku, opus, or a full model name
command = []        # another CLI instead of Claude Code
```

`haiku` answers a second or two sooner and uses less of your plan.

`command` runs any other CLI that reads the prompt on stdin and prints the
answer on stdout, for example `["codex", "exec", "--skip-git-repo-check"]`.
Its output is shown as it arrives, line by line.

## How it works

Claude Code runs with no tools, no saved session, a short system prompt of
its own, and in an empty folder, so no project files or `CLAUDE.md` are
loaded. Your global `~/.claude` settings still apply. The first words take
about three seconds, a second or two of which is Claude Code starting.

For `fix`, the copied text is sent wrapped in `<text>` tags, and Claude is
told to treat it as text to rewrite, never as instructions. Parsec never
hands the plugin a password it has just copied from KeePass.

## Development

```sh
python3 -m unittest      # offline: a fake `claude` stands in for the real one
```

## License

MIT
