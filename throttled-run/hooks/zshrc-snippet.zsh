# --- throttled: brána před těžkými yarn skripty (skill throttled-run) ---------
# Přidej do ~/.zshrc. Platí i pro Claude Code: jeho Bash tool běží v zsh
# a načítá snapshot funkcí z ~/.zshrc, takže agenti dostanou bránu taky —
# bez jediné změny v promptech nebo v permissions.
yarn() {
    local sub=${1-}
    case $sub in
        build|ci|typecheck|lint|lint:check|knip|knip:ci|test|test:e2e|db:migrate|db:generate|cli:seed|cli:seed-demo-actions) ;;
        test:run)
            # jediný soubor je levný — bránu nepotřebuje
            if [[ -n ${2-} && ${2-} != -* ]]; then
                command yarn "$@"
                return
            fi
            ;;
        *)
            command yarn "$@"
            return
            ;;
    esac

    if [[ -n ${THROTTLED_DISABLE-} ]] || (( ! $+commands[throttled] )); then
        command yarn "$@"
        return
    fi

    # --then run: po 5 min jde stejně — tichý exit 75 v logu nikdo nečte
    throttled -w 5m --then run ${commands[yarn]} "$@"
}
# --- konec throttled ---------------------------------------------------------
