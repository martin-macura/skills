#!/usr/bin/env bash
# PreToolUse(Bash) — odmítne těžký příkaz, dokud je stroj přetížený.
#
# Nic nepřepisuje a nic sám nepouští: dokud je load pod stropem, mlčí a příkaz
# jde normální cestou (včetně běžného ptaní na povolení). Teprve když je stroj
# busy, příkaz odmítne a vrátí přesné znění s `throttled`, které má agent použít.
#
# Zapojení (jednou, v ~/.claude/settings.json):
#   "hooks": { "PreToolUse": [ { "matcher": "Bash", "hooks": [
#     { "type": "command",
#       "command": "/Users/macik/projects/2bad2furious/skills/throttled-run/hooks/throttle-bash.sh",
#       "timeout": 15 } ] } ] }
set -uo pipefail

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
[ -n "$cmd" ] || exit 0

# už je pod bránou / brána vypnutá / nástroje chybí → nic neřeš
case "$cmd" in *throttled*) exit 0 ;; esac
[ -n "${THROTTLED_DISABLE:-}" ] && exit 0
command -v throttled >/dev/null 2>&1 || exit 0
command -v jq >/dev/null 2>&1 || exit 0

# Těžké příkazy. Máš-li v ~/.zshrc wrapper na `yarn`, smaž z regexu větev yarn.
HEAVY='(^|[;&|(]|[[:space:]])(yarn[[:space:]]+(build|ci|typecheck|lint|lint:check|knip|knip:ci|test|test:run|test:e2e|db:migrate|db:generate|cli:seed[^[:space:]]*)|npx[[:space:]]+(playwright|vitest|tsc|jest)|(vitest|playwright|tsc|vite)[[:space:]]+|docker([[:space:]]+compose)?[[:space:]]+build|docker[[:space:]]+compose[[:space:]]+up[^|;]*--build)'
printf '%s' "$cmd" | grep -Eq "$HEAVY" || exit 0

# Výjimky, které skill throttled-run výslovně negatuje: dev server, studio
# a běh jediného spec souboru (`yarn test:run cesta/k/souboru.spec.ts`).
case "$cmd" in
    *"yarn dev"*|*"yarn db:studio"*) exit 0 ;;
esac
if printf '%s' "$cmd" | grep -Eq 'yarn[[:space:]]+test:run[[:space:]]+[^-][^[:space:]]*\.(spec|test)\.[tj]sx?'; then
    exit 0
fi

verdict=$(throttled --check 2>&1) && exit 0   # stroj je volný → propusť beze změny

quoted=$(printf '%s' "$cmd" | sed "s/'/'\\\\''/g")
suggestion="throttled -w 8m --then fail zsh -c '$quoted'"

reason="Stroj je přetížený: ${verdict}

Nespouštěj těžký příkaz bez brány — rozbil bys běžící buildy a testy v ostatních worktree (a ony tobě: testy pak padají na 60s timeoutech, které vypadají jako regrese v diffu). Spusť místo toho:

    ${suggestion}

Exit 75 = stroj byl pořád busy a NIC se nespustilo (není to spadlý build ani červené testy) — ohlas to a zkus znovu v dalším kroku. Běh delší než ~10 min pusť odpojeně:
    nohup throttled -w 30m --then run <příkaz> > <log> 2>&1 & disown"

jq -n --arg r "$reason" --arg v "$verdict" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: $r
  },
  systemMessage: ("⏸︎ throttle: těžký příkaz odmítnut — " + $v)
}'
exit 0
