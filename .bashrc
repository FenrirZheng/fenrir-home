# ~/.bashrc: executed by bash(1) for non-login shells.
# see /usr/share/doc/bash/examples/startup-files (in the package bash-doc)
# for examples

# 載入自訂函式 (放在 interactive guard 之前, 讓非互動式 shell 也能使用)
for f in ~/.bash.d/*.sh; do source "$f"; done
[ -f ~/.shell.d/aliases ] && source ~/.shell.d/aliases

# If not running interactively, don't do anything
case $- in
    *i*) ;;
      *) return;;
esac

# --- Auto-enter tmux for interactive shells -------------------------------
# Attach to the most-recently-used session if one exists, otherwise start a
# fresh one. Placed right after the interactive guard so it runs BEFORE the
# heavy sdkman/nvm/zoxide init below -- `exec` replaces this process, and the
# tmux inner shell re-sources ~/.bashrc in full, so loading them here first
# would just be wasted work in the throwaway outer shell.
# Guards:
#   $TMUX empty          : not already inside tmux (avoids nesting / recursion)
#   NO_TMUX unset        : escape hatch -> `NO_TMUX=1 bash` skips this
#   INSIDE_EMACS unset   : don't hijack Emacs term/eshell/vterm buffers
#   TERM not screen/tmux : belt-and-suspenders against re-entry
if command -v tmux >/dev/null 2>&1 \
   && [ -z "$TMUX" ] && [ -z "$NO_TMUX" ] && [ -z "$INSIDE_EMACS" ] \
   && [[ "$TERM" != screen* && "$TERM" != tmux* ]]; then
    if tmux has-session 2>/dev/null; then
        exec tmux attach-session
    else
        exec tmux new-session
    fi
fi

# don't put duplicate lines or lines starting with space in the history.
# See bash(1) for more options
HISTCONTROL=ignoreboth

# append to the history file, don't overwrite it
shopt -s histappend

# for setting history length see HISTSIZE and HISTFILESIZE in bash(1)
HISTSIZE=1000
HISTFILESIZE=2000

# check the window size after each command and, if necessary,
# update the values of LINES and COLUMNS.
shopt -s checkwinsize

# If set, the pattern "**" used in a pathname expansion context will
# match all files and zero or more directories and subdirectories.
#shopt -s globstar

# make less more friendly for non-text input files, see lesspipe(1)
#[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

# set variable identifying the chroot you work in (used in the prompt below)
if [ -z "${debian_chroot:-}" ] && [ -r /etc/debian_chroot ]; then
    debian_chroot=$(cat /etc/debian_chroot)
fi

# set a fancy prompt (non-color, unless we know we "want" color)
case "$TERM" in
    xterm-color|*-256color) color_prompt=yes;;
esac

# uncomment for a colored prompt, if the terminal has the capability; turned
# off by default to not distract the user: the focus in a terminal window
# should be on the output of commands, not on the prompt
#force_color_prompt=yes

if [ -n "$force_color_prompt" ]; then
    if [ -x /usr/bin/tput ] && tput setaf 1 >&/dev/null; then
	# We have color support; assume it's compliant with Ecma-48
	# (ISO/IEC-6429). (Lack of such support is extremely rare, and such
	# a case would tend to support setf rather than setaf.)
	color_prompt=yes
    else
	color_prompt=
    fi
fi

if [ "$color_prompt" = yes ]; then
    PS1='${debian_chroot:+($debian_chroot)}\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
else
    PS1='${debian_chroot:+($debian_chroot)}\u@\h:\w\$ '
fi
unset color_prompt force_color_prompt

# If this is an xterm set the title to user@host:dir
case "$TERM" in
xterm*|rxvt*)
    PS1="\[\e]0;${debian_chroot:+($debian_chroot)}\u@\h: \w\a\]$PS1"
    ;;
*)
    ;;
esac

# enable color support of ls and also add handy aliases
if [ -x /usrpath/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    #alias dir='dir --color=auto'
    #alias vdir='vdir --color=auto'

    #alias grep='grep --color=auto'
    #alias fgrep='fgrep --color=auto'
    #alias egrep='egrep --color=auto'
fi

# colored GCC warnings and errors
#export GCC_COLORS='error=01;31:warning=01;35:note=01;36:caret=01;32:locus=01:quote=01'

# some more ls aliases
#alias ll='ls -l'
#alias la='ls -A'
#alias l='ls -CF'

# Alias definitions.
# You may want to put all your additions into a separate file like
# ~/.bash_aliases, instead of adding them here directly.
# See /usr/share/doc/bash-doc/examples in the bash-doc package.

if [ -f ~/.bash_aliases ]; then
    . ~/.bash_aliases
fi

# EDITOR points at a wrapper script, NOT directly at `emacsclient -t -a ""'.
# Claude Code's Ctrl+G launches $EDITOR via naive `EDITOR.split(" ")' +
# shell-less `spawnSync', so a bare `-a ""' would reach emacsclient as the
# LITERAL two-char string `""' and break the daemon-autostart fallback whenever
# no daemon is running.  Routing through ~/.local/bin/claude-editor (a real
# bash script) restores correct `-a ""' parsing for every consumer (git,
# Claude, etc.) while keeping the daemon semantics described below.
export EDITOR="$HOME/.local/bin/claude-editor"
export VISUAL="$HOME/.local/bin/claude-editor"

# Always go through the daemon.  `-a ""' = if no daemon is running, spawn one
# (`emacs --daemon') and connect to it.  The previous `alias emacs='emacs -nw''
# bypassed the daemon entirely and opened a fresh standalone Emacs each time
# -- silently fragmenting buffer/history/state.
#
#   emacs-tui : `-t' attaches a frame INSIDE the current terminal (blocks).
#   emacs-gui : `-c' opens a new GUI frame (blocks too -- suffix with ` &'
#               from the terminal if you want the prompt back immediately,
#               or use `emacsclient -nc' for a fire-and-forget variant).
alias emacs='emacsclient -t -a ""'
alias emacs-tui='emacsclient -t -a ""'
alias emacs-gui='emacsclient -c -a ""'

# debain system fd naming as fdfind
# sudo apt install bfs
if [ -f /etc/debian_version ]; then
    alias fd='fdfind'
    alias find='bfs'
fi

# enable programmable completion features (you don't need to enable
# this, if it's already enabled in /etc/bash.bashrc and /etc/profile
# sources /etc/bash.bashrc).
if ! shopt -oq posix; then
  if [ -f /usr/share/bash-completion/bash_completion ]; then
    . /usr/share/bash-completion/bash_completion
  elif [ -f /etc/bash_completion ]; then
    . /etc/bash_completion
  fi
fi
export PATH="$HOME/.bash.d:$HOME/.shell.d/bin:$HOME/.local/bin:$HOME/go/bin:$PATH"
. "$HOME/.cargo/env"

#THIS MUST BE AT THE END OF THE FILE FOR SDKMAN TO WORK!!!
export SDKMAN_DIR="$HOME/.sdkman"
[[ -s "$HOME/.sdkman/bin/sdkman-init.sh" ]] && source "$HOME/.sdkman/bin/sdkman-init.sh"

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion

export PATH="$PATH:/home/fenrir/.foundry/bin"


# bash complete

if ! shopt -oq posix; then
  if [ -f /usr/share/bash-completion/bash_completion ]; then
    . /usr/share/bash-completion/bash_completion
  elif [ -f /etc/bash_completion ]; then
    . /etc/bash_completion
  fi
fi


# pnpm
export PNPM_HOME="/home/fenrir/.local/share/pnpm"
case ":$PATH:" in
  *":$PNPM_HOME:"*) ;;
  *) export PATH="$PNPM_HOME:$PATH" ;;
esac
# pnpm end

#  eval "$(zoxide init bash)" , folder dictionary
eval "$(zoxide init bash)"


# Added by Antigravity CLI installer
export PATH="/home/fenrir/.local/bin:$PATH"
