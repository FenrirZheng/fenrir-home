#!/bin/bash
# Make X session env reachable by an already-running Emacs daemon that was
# started via systemd before the graphical session imported DISPLAY/XAUTHORITY.
#
# Two-pronged:
#
# 1. Copy $XAUTHORITY -> ~/.Xauthority. Mutter writes the cookie to a random
#    path under /run/user/$UID/ each session; the daemon's libc-level
#    getenv("XAUTHORITY") returns NULL (its initial environ only had PATH +
#    SSH_AUTH_SOCK), so XOpenDisplay falls back to ~/.Xauthority. A fresh copy
#    there each graphical login is what actually lets the daemon open the
#    display.  Elisp `setenv` does NOT update libc environ, so trying to push
#    XAUTHORITY into the daemon via `emacsclient --eval` looks like it works
#    (subprocess env sees it) but XOpenDisplay still fails.
#
# 2. Also push DISPLAY / XAUTHORITY / WAYLAND_DISPLAY into the daemon's elisp
#    `process-environment` so any subprocess Emacs spawns (browse-url,
#    xdg-open, helm-show-kill-ring → xclip, ...) sees them.
#
# Called by emacs-x-env.service. ExecStart=`push`, ExecStop=`clear`.

set -eu

action="${1:-push}"

case "$action" in
  push)
    if [[ -n "${XAUTHORITY:-}" && -r "$XAUTHORITY" ]]; then
      cp -f "$XAUTHORITY" "$HOME/.Xauthority"
      chmod 600 "$HOME/.Xauthority"
    fi
    /usr/bin/emacsclient --eval "(progn \
      (setenv \"DISPLAY\" \"${DISPLAY:-}\") \
      (setenv \"XAUTHORITY\" \"$HOME/.Xauthority\") \
      (setenv \"WAYLAND_DISPLAY\" \"${WAYLAND_DISPLAY:-}\"))" >/dev/null
    ;;
  clear)
    rm -f "$HOME/.Xauthority"
    /usr/bin/emacsclient --eval "(progn \
      (setenv \"DISPLAY\" nil) \
      (setenv \"XAUTHORITY\" nil) \
      (setenv \"WAYLAND_DISPLAY\" nil))" >/dev/null || true
    ;;
  *)
    echo "usage: $0 {push|clear}" >&2
    exit 2
    ;;
esac
