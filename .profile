# ~/.profile: executed by the command interpreter for login shells.
# This file is not read by bash(1), if ~/.bash_profile or ~/.bash_login
# exists.
# see /usr/share/doc/bash/examples/startup-files for examples.
# the files are located in the bash-doc package.

# the default umask is set in /etc/profile; for setting the umask
# for ssh logins, install and configure the libpam-umask package.
#umask 022

# if running bash
if [ -n "$BASH_VERSION" ]; then
    # include .bashrc if it exists
    if [ -f "$HOME/.bashrc" ]; then
	. "$HOME/.bashrc"
    fi
fi

# set PATH so it includes user's private bin if it exists
if [ -d "$HOME/bin" ] ; then
    PATH="$HOME/bin:$PATH"
fi

# set PATH so it includes user's private bin if it exists
if [ -d "$HOME/.local/bin" ] ; then
    PATH="$HOME/.local/bin:$PATH"
fi


# Added by Toolbox App
export PATH="$PATH:/home/fenrir/.local/share/JetBrains/Toolbox/scripts"

. "$HOME/.cargo/env"

# nvm — sourced here so non-interactive login shells (bash -lc, cron) get
# node on PATH. Interactive shells additionally source it via .bashrc.
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Machine-local environment / secrets — UNTRACKED. Keep secrets OUT of this
# tracked file; put them in ~/.profile.local instead. Currently holds
# GEMINI_API_KEY for aider / aidermacs (see ~/.emacs.d/lisp/init-aidermacs.el).
# Keep this line last so local overrides win.
[ -f "$HOME/.profile.local" ] && . "$HOME/.profile.local"
