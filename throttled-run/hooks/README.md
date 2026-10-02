# Aby se `throttled` používal sám — i během vývoje

Dvě vrstvy. Každá zvlášť dává smysl, dohromady se nepřekrývají.

## Vrstva 1 — zsh wrapper (`zshrc-snippet.zsh`) · průhledná, doporučená

Funkce `yarn()` v `~/.zshrc`, která těžké podpříkazy pustí přes `throttled -w 5m --then run`.

Proč zrovna funkce: Claude Code pouští Bash tool v **zsh** a načítá si snapshot funkcí z tvého
`~/.zshrc` (`type nvm` uvnitř agenta ukáže cestu do `~/.claude/shell-snapshots/`). Takže jedna
funkce pokryje **tebe v terminálu i každého agenta a subagenta** — bez zásahu do promptů, skillů
i permissions. Aliasy takhle nefungují, snapshot je na začátku odstřeluje (`unalias -a`); funkce
ano.

```bash
cat ~/projects/2bad2furious/skills/throttled-run/hooks/zshrc-snippet.zsh >> ~/.zshrc
```

Pak stačí nová session (snapshot se dělá při startu; běžící sessions mají ten starý).

- Negatuje se `yarn dev`, `yarn add`, `yarn test:run <jeden soubor>` a všechno ostatní neuvedené.
- `--then run`: po 5 minutách jde stejně. Tichý exit 75 v logu, který nikdo nečte, je horší než
  build na trochu vytíženém stroji.
- `THROTTLED_DISABLE=1 yarn build` bránu obejde.
- Když sáhneš po `npx playwright` / `vitest` / `docker build` mimo yarn, wrapper je nevidí — na to
  je vrstva 2.

## Vrstva 2 — PreToolUse hook (`throttle-bash.sh`) · záruka, ne nápověda

Hook nad Bash toolem, který **nepřepisuje příkazy a sám nic nepouští**. Dokud je load pod stropem,
mlčí a příkaz jde běžnou cestou včetně normálního ptaní na povolení. Teprve když je stroj busy,
těžký příkaz odmítne a vrátí přesné znění s `throttled`, které má agent použít.

```jsonc
// ~/.claude/settings.json
"hooks": {
  "PreToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "command",
          "command": "/Users/macik/projects/2bad2furious/skills/throttled-run/hooks/throttle-bash.sh",
          "timeout": 15
        }
      ]
    }
  ]
}
```

- **Proč deny a ne přepis příkazu.** PreToolUse umí `updatedInput`, ale jen spolu
  s `permissionDecision: "allow"` — tedy za cenu automatického schválení každého takového příkazu.
  Deny drží permission model nedotčený a stojí jeden krok navíc, a to jen na přetíženém stroji.
- Máš-li vrstvu 1, smaž z `HEAVY` v skriptu větev `yarn` — jinak hook odmítne i příkaz, který by
  wrapper stejně přes bránu pustil.
- Vyžaduje `jq` a `throttled` na PATH; když kterýkoli chybí, hook mlčí a nic neblokuje.

## Co se nedělá

- **`package.json` skripty (`"build": "throttled vite build"`)** — repo je sdílené, `throttled`
  nikdo jiný z týmu nemá a CI by muselo všude vypínat `THROTTLED_DISABLE=1`.
- **`AGENTS.md` pravidlo** — totéž: pravidlo pro nástroj, který má na stroji jeden člověk.
  Brána patří na tenhle stroj, ne do repa.
