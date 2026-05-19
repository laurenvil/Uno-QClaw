# QClaw fork verification — 2026-05-19

End-to-end verification that the `picoclaw → qclaw` rename and the
`sipeed/picoclaw → laurenvil/Uno-QClaw` fork swap produce a working
build, tree, install, runtime, and Docker image on an Arduino Uno Q.

- Repo: `github.com/laurenvil/Uno-QClaw`
- Branch: `QClaw`
- Host: Arduino Uno Q (Qualcomm QRB2210, aarch64, Debian, kernel 6.16)
- Go: system 1.24.4 with `GOTOOLCHAIN=auto` fetching 1.25.7 on demand

## Remote wiring

`origin` was pointed at `https://github.com/laurenvil/Uno-QClaw` but
HTTPS had no credential helper, so `git push` failed with
`could not read Username for 'https://github.com'`. The host already
had an SSH alias configured in `~/.ssh/config`:

```
Host github-laurenvil
    HostName github.com
    User git
    IdentityFile ~/.ssh/laurenvil_github
```

Switched the remote to use it:

```
git remote set-url origin git@github-laurenvil:laurenvil/Uno-QClaw.git
```

`ssh -T github-laurenvil` authenticates as `Draider2001`. Push works.

## Step results

| # | Command | Result |
|---|---|---|
| 1 | `make build` | Built `build/qclaw-linux-arm64` (20 MB, ARM aarch64, statically linked). Module path `github.com/laurenvil/Uno-QClaw` resolves; all imports compile. |
| 2 | `make test` | All packages pass after fixing four stale fixtures (see below). `TestNewQClawCommand` and the `helpers_test.go` env-var tests already passed unchanged. |
| 3 | `make qclaw-install` on a fresh `~/.qclaw` | Backed up `~/.qclaw → ~/.qclaw.bak`, ran install, verified `~/.qclaw/{config.json, workspace/SOUL.md, workspace/IDENTITY.md, workspace/skills/}` were written. 15 skills installed. arduino-cli and `arduino:zephyr` core already present. Original `~/.qclaw` restored after. |
| 4 | `make qclaw` (gateway, agent loop, skills) | Verified each component the launcher orchestrates instead of running the blocking interactive loop: `qclaw skills list` → 15 skills loaded; `qclaw gateway` → `Agent initialized, skills_available=15/15, tools_count=8`, cron + heartbeat + media store started; `qclaw agent` → ready prompt, clean exit on stdin EOF. |
| 5 | `make docker-build && make docker-run` | `docker-compose.yml` has no `build:` clause (pre-existing upstream pattern — image is pulled from registry, not built), so `make docker-build` is a silent no-op. Built directly via `docker build -f docker/Dockerfile -t laurenvil/qclaw:latest .` → 36 MB Alpine image. `docker compose --profile gateway up` creates container `qclaw-gateway` from `laurenvil/qclaw:latest`, binary boots and reaches the gateway entrypoint. Required `docker system prune -af` to reclaim 3.5 GB beforehand (root partition was 98 % full). |

## Stale fixtures fixed

Four assertions still expected pre-rename values and were updated to
match what the code actually produces:

1. `cmd/qclaw/internal/gateway/command_test.go:16` — expected
   `"Start qclaw gateway"`; actual is `"Start QClaw gateway"`.
2. `cmd/qclaw/internal/onboard/command_test.go:16` — expected
   `"Initialize qclaw configuration and workspace"`; actual is
   `"Initialize QClaw configuration and workspace"`.
3. `pkg/channels/matrix/matrix_test.go:117` — `formatted mention href
   matrix.to encoded` fixture still URL-encoded `@picoclaw:matrix.org`;
   the bot ID is now `@qclaw:matrix.org`, so the encoded form is
   `%40qclaw%3Amatrix.org`.
4. `pkg/skills/installer_test.go:43-65` — three `parseGitHubRef`
   cases used `https://github.com/laurenvil/Uno-QClaw/…` URLs but
   still asserted `wantOwner: "sipeed"` / `wantRepoName: "qclaw"`.
   Updated to `wantOwner: "laurenvil"` / `wantRepoName: "Uno-QClaw"`.

Also restored `+x` on the four scripts the Makefile invokes
(`arduino-cli-setup.sh`, `qclaw-launch.sh`, `qclaw-launch-direct.sh`,
`qclaw-onboard.sh`). The rename commit had dropped the executable
bit. The Makefile chmods them at launch, but direct invocation was
broken without `+x`.

## Banner cleanup

A repo-wide grep for `Sensai`, `SENSAI`, `S E N S A I`, and
`S  E  N  S  A  I` found two letter-spaced banners that survived the
rename:

- `scripts/qclaw-launch.sh:133` — `S  E  N  S  A  I` → `Q  C  L  A  W`
- `scripts/qclaw-direct-chat.py:206` — `S E N S A I` → `Q C L A W`

Trailing whitespace was adjusted on both so the box-drawing borders
stay aligned.

Gateway code, onboarding code, docker, workspace skills, config,
and the web frontend were already clean.

## Commits

| SHA | Subject |
|---|---|
| `fa17b47` | `test: fix stale fixtures left from picoclaw → qclaw rename` (was `4bd7d86`, re-authored as QClaw via `git commit --amend --reset-author`) |
| `35f3c9e` | `chore: replace remaining SENSAI banners with QCLAW` |

Both authored as `QClaw <qclaw@users.noreply.github.com>` (set as
repo-local `user.name` / `user.email`, overriding the global
`Sensai` identity).

Pushed to `origin/QClaw` on `github.com/laurenvil/Uno-QClaw`.
