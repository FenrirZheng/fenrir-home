#!/usr/bin/env python3
"""Convert an Obsidian vault (.md + [[wikilinks]] + Markdown links) into an org-roam library.

  source : ~/code/obsidian   (Markdown notes, YAML frontmatter, Obsidian links)
  target : ~/code/org-roam    (one .org per note + a property drawer carrying :ID:)

Two passes -- link rewriting needs every note's UUID up front:

  Pass 1  build_maps()
    - assign a UUID to every .md note
    - key_to_uuid : {stem | title | alias  (lowercased) -> UUID}      basename lookups
    - path_to_uuid: {vault-relative posix path, lowercased -> UUID}    precise path links
    - asset maps  : basename and vault-relative path  ->  original asset path

  Pass 2  per note
    - strip YAML frontmatter, parse a small YAML subset
    - placeholder-out Obsidian-only syntax  [[wikilink]] / ![[embed]]  (pandoc can't read it),
      skipping fenced code blocks and inline `code` spans
    - markdown body -> org   (pandoc if on PATH, else a built-in fallback converter)
    - restore the placeholders as org-roam links:
        [[wikilink]]      ->  [[id:UUID][label]]              (or a fuzzy link if unresolved)
        ![[note]]         ->  [[id:UUID][label]]              (transclusion is lost -- see report)
        ![[image.png]]    ->  [[file:RELATIVE-TO-THIS-FILE]]
    - fixup pandoc's own [[file:...]] links (from ordinary Markdown links/images):
        [text](note.md)   ->  [[id:UUID][text]]
        [text](img/x.png) ->  [[file:RELATIVE-TO-THIS-FILE][text]]   (Obsidian writes vault-root
                                                                       relative paths; org wants
                                                                       file-relative -- so rewrite)
    - prepend  :PROPERTIES: (:ID:, :ROAM_ALIASES:, :ROAM_REFS:, :OBSIDIAN_*: provenance) :END:
               + #+title: + #+filetags:
    - write   <dst>/<same relative path>.org
  Assets: every non-.md file (images, pdfs, code snippets, *.base, ...) is copied verbatim,
          preserving its relative path.

Lossy on purpose -- a CONVERSION-REPORT.txt is written into the target dir listing every
unresolved link, every name collision, and every note that still contains an Obsidian-only
construct that wants a manual look:
  ![[note]] transclusion  ->  degraded to a plain link
  > [!callout]            ->  pandoc renders a blockquote; the [!type] marker stays as text
  ```dataview``` / *.base ->  left inert
  $$ math $$ / tables     ->  pandoc handles them; the built-in fallback does not
  %%comments%%            ->  flagged for review

Stdlib only.  Run with --dry-run first.  After conversion, in Emacs:  M-x org-roam-db-sync
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

# --------------------------------------------------------------------------- #

DEFAULT_SRC = Path("~/code/obsidian").expanduser()
DEFAULT_DST = Path("~/code/org-roam").expanduser()

SKIP_DIRS = {".git", ".obsidian", ".trash", ".claude", ".github"}
SKIP_FILE_NAMES = {".gitignore", ".gitmodules", ".gitattributes", ".gitkeep", ".DS_Store"}
INLINE_IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".pdf"}

WIKILINK_RE = re.compile(r"(!?)\[\[([^\]\n]+)\]\]")               # [[T]] [[T#h]] [[T|a]] ![[img]]
TAG_RE = re.compile(r"(?:^|(?<=\s))#([A-Za-z][\w/\-]*)")          # Obsidian inline #tag
FENCE_BLOCK_RE = re.compile(r"^```[^\n]*\n.*?\n```[ \t]*$", re.M | re.S)
INLINE_CODE_RE = re.compile(r"`{1,2}[^`\n]+`{1,2}")
MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
ORG_FILE_LINK_RE = re.compile(r"\[\[file:([^\]]+?)\](?:\[([^\]]*)\])?\]")
URL_RE = re.compile(r"^[A-Za-z][\w+.\-]*://|^mailto:|^tel:|^doi:", re.I)

PLACEHOLDER = "WLPLACEHOLDER{0}WLEND"                              # alphanumeric -> survives md->org
PLACEHOLDER_RE = re.compile(r"WLPLACEHOLDER(\d+)WLEND")

CONSUMED_FM_KEYS = {"title", "tags", "tag", "aliases", "alias", "url", "source", "website", "link"}

ORG_ROAM_CONFIG_SNIPPET = """\
;; ---------------------------------------------------------------------------
;; org-roam  (notes converted from the Obsidian vault into ~/code/org-roam)
;; ---------------------------------------------------------------------------
(use-package org-roam
  :custom
  (org-roam-directory (file-truename "~/code/org-roam"))
  (org-roam-dailies-directory "")          ; daily notes (e.g. 2026-05-08.org) sit at the root
  (org-roam-completion-everywhere t)
  :bind (("C-c r f" . org-roam-node-find)
         ("C-c r i" . org-roam-node-insert)
         ("C-c r b" . org-roam-buffer-toggle)
         ("C-c r c" . org-roam-capture)
         ("C-c r d" . org-roam-dailies-goto-today))
  :config
  (org-roam-db-autosync-mode 1))
;; First run: M-x my/package-refresh, restart Emacs, then M-x org-roam-db-sync.
"""


# --------------------------------------------------------------------------- #
# frontmatter
# --------------------------------------------------------------------------- #

def normalise(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_frontmatter(text: str) -> tuple[str, str]:
    m = re.match(r"---\n(.*?)\n---\n?", text, re.S)
    return (m.group(1), text[m.end():]) if m else ("", text)


def _unquote_yaml(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def parse_frontmatter(fm: str) -> dict:
    """Tiny YAML subset: scalars, inline `[a, b]` flow lists, and `k:`+`- a` block lists."""
    data: dict = {}
    key: str | None = None
    for raw in fm.splitlines():
        if not raw.strip():
            continue
        m_item = re.match(r"\s*-\s+(.*)$", raw)
        if m_item and key is not None and isinstance(data.get(key), list):
            data[key].append(_unquote_yaml(m_item.group(1)))
            continue
        m_kv = re.match(r"([^:#\n][^:\n]*?)\s*:\s*(.*)$", raw)
        if m_kv:
            key = m_kv.group(1).strip().lower()
            val = m_kv.group(2).strip()
            if val == "":
                data[key] = []
            elif val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                data[key] = [_unquote_yaml(x) for x in inner.split(",") if x.strip()] if inner else []
            else:
                data[key] = _unquote_yaml(val)
            continue
    return data


def as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [x for x in re.split(r"[,\s]+", v.strip()) if x]
    return [str(v)]


def org_tag(t: str) -> str:
    t = re.sub(r"[^A-Za-z0-9_@#%]", "_", t.lstrip("#"))
    return re.sub(r"_+", "_", t).strip("_")


# --------------------------------------------------------------------------- #
# code-region masking (fenced blocks + inline code spans are "protected")
# --------------------------------------------------------------------------- #

def split_protected(text: str):
    """Yield (is_protected, chunk) covering `text`. Protected = fenced ``` block or `inline code`."""
    pos = 0
    for m in FENCE_BLOCK_RE.finditer(text):
        if m.start() > pos:
            yield from _split_inline_code(text[pos:m.start()])
        yield (True, m.group(0))
        pos = m.end()
    if pos < len(text):
        yield from _split_inline_code(text[pos:])


def _split_inline_code(text: str):
    pos = 0
    for m in INLINE_CODE_RE.finditer(text):
        if m.start() > pos:
            yield (False, text[pos:m.start()])
        yield (True, m.group(0))
        pos = m.end()
    if pos < len(text):
        yield (False, text[pos:])


# --------------------------------------------------------------------------- #
# pass 1
# --------------------------------------------------------------------------- #

def iter_md_files(root: Path):
    for p in sorted(root.rglob("*.md")):
        if not any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            yield p


def iter_asset_files(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.suffix.lower() == ".md" or p.name in SKIP_FILE_NAMES:
            continue
        yield p


class Maps:
    def __init__(self):
        self.note_uuid: dict[Path, str] = {}
        self.key_to_uuid: dict[str, str] = {}                 # first holder wins
        self.path_to_uuid: dict[str, str] = {}                # vault-rel posix, lowercased
        self.asset_by_name: dict[str, str] = {}               # basename.lower -> vault-rel posix (orig)
        self.asset_by_path: dict[str, str] = {}               # vault-rel posix lower -> vault-rel posix orig
        self.collisions: list[tuple[str, Path, Path]] = []


def build_maps(md_files: list[Path], asset_files: list[Path], root: Path) -> Maps:
    m = Maps()
    key_owner: dict[str, Path] = {}
    for p in md_files:
        u = str(uuid.uuid4())
        m.note_uuid[p] = u
        rel = p.relative_to(root).as_posix()
        m.path_to_uuid[rel.lower()] = u
        fm = parse_frontmatter(split_frontmatter(normalise(p.read_text("utf-8", errors="replace")))[0])
        keys = {p.stem.lower()}
        title = fm.get("title")
        if isinstance(title, str) and title.strip():
            keys.add(title.strip().lower())
        for a in as_list(fm.get("aliases")) + as_list(fm.get("alias")):
            keys.add(a.lower())
        for k in keys:
            if k in m.key_to_uuid:
                if m.key_to_uuid[k] != u:
                    m.collisions.append((k, key_owner[k], p))
            else:
                m.key_to_uuid[k] = u
                key_owner[k] = p
    for p in asset_files:
        rel = p.relative_to(root).as_posix()
        m.asset_by_name.setdefault(p.name.lower(), rel)
        m.asset_by_path[rel.lower()] = rel
    return m


# --------------------------------------------------------------------------- #
# link resolution
# --------------------------------------------------------------------------- #

def _split_anchor(t: str) -> tuple[str, str | None]:
    for sep in ("::", "#"):
        if sep in t:
            base, _, frag = t.partition(sep)
            return base.strip(), frag.strip().lstrip("*^")
    return t.strip(), None


def _rel_to_note(vault_rel_posix: str, note_dir: PurePosixPath) -> str:
    rp = os.path.relpath(vault_rel_posix, str(note_dir) if str(note_dir) != "." else ".")
    return PurePosixPath(*Path(rp).parts).as_posix() if os.sep != "/" else rp


def resolve_target(raw: str, note_dir: PurePosixPath, m: Maps):
    """Resolve an Obsidian/Markdown link target to one of:
       ('id', uuid, anchor)  |  ('file', path-relative-to-note)  |
       ('ext', raw)  external/in-page  |  ('none', raw)  unresolved."""
    raw = raw.strip()
    if not raw or URL_RE.match(raw) or raw.startswith("#"):
        return ("ext", raw)
    target, anchor = _split_anchor(unquote(raw))
    if not target:
        return ("ext", raw)
    low = target.lower()
    has_slash = "/" in target

    # 1. note by vault-root-relative path
    cand = low if low.endswith(".md") else low + ".md"
    if cand in m.path_to_uuid:
        return ("id", m.path_to_uuid[cand], anchor)
    # 2. note by path relative to the linking note
    if has_slash:
        rel = os.path.normpath((note_dir / target).as_posix()).replace(os.sep, "/").lower()
        cand2 = rel if rel.endswith(".md") else rel + ".md"
        if cand2 in m.path_to_uuid:
            return ("id", m.path_to_uuid[cand2], anchor)
    # 3. asset by vault-root-relative path (or relative to the note)
    if low in m.asset_by_path:
        return ("file", _rel_to_note(m.asset_by_path[low], note_dir))
    if has_slash:
        relp = os.path.normpath((note_dir / target).as_posix()).replace(os.sep, "/").lower()
        if relp in m.asset_by_path:
            return ("file", _rel_to_note(m.asset_by_path[relp], note_dir))
    # 4. basename note lookup
    base = target.split("/")[-1]
    base_key = base[:-3].lower() if base.lower().endswith(".md") else base.lower()
    if base_key in m.key_to_uuid:
        return ("id", m.key_to_uuid[base_key], anchor)
    # 5. basename asset lookup
    if base.lower() in m.asset_by_name:
        return ("file", _rel_to_note(m.asset_by_name[base.lower()], note_dir))
    return ("none", raw)


def _org_link(kind_tuple, default_label: str, *, embed: bool) -> str:
    kind = kind_tuple[0]
    if kind == "id":
        _, u, anchor = kind_tuple
        label = default_label or "link"
        if anchor and not default_label:
            label = f"{label} › {anchor}"
        return f"[[id:{u}][{label}]]"
    if kind == "file":
        path = kind_tuple[1]
        if embed:
            return f"[[file:{path}]]"
        return f"[[file:{path}][{default_label or os.path.basename(path)}]]"
    return ""  # caller handles ext/none


# ---- placeholder pass (Obsidian [[...]] / ![[...]]) ------------------------ #

def stash_wikilinks(body: str):
    holders: list[tuple[str, str]] = []

    def stash(mo: re.Match) -> str:
        holders.append((mo.group(1), mo.group(2)))
        return PLACEHOLDER.format(len(holders) - 1)

    out = [chunk if prot else WIKILINK_RE.sub(stash, chunk) for prot, chunk in split_protected(body)]
    return "".join(out), holders


def restore_wikilinks(org: str, holders: list, note_dir: PurePosixPath, m: Maps, stats: dict, fname: str) -> str:
    def sub(mo: re.Match) -> str:
        bang, inner = holders[int(mo.group(1))]
        embed = bang == "!"
        link, _, disp = inner.partition("|") if "|" in inner else (inner, "", "")
        disp = disp.strip() or None
        res = resolve_target(link.strip(), note_dir, m)
        if res[0] in ("id", "file"):
            if res[0] == "file" and embed:
                stats["embed_assets"] += 1
            if res[0] == "id" and embed:
                stats["embed_notes"] += 1
            base = link.strip().split("/")[-1]
            if base.lower().endswith(".md"):
                base = base[:-3]
            return _org_link(res, disp or base, embed=embed)
        # unresolved -> keep something readable; org treats [[x]] as a fuzzy link
        stats["unresolved"].append((fname, inner))
        keep = link.strip()
        return f"[[{keep}]]" if not disp else f"[[{keep}][{disp}]]"

    return PLACEHOLDER_RE.sub(sub, org)


# ---- fixup pass (pandoc's own [[file:...]] links from Markdown links/images) ---- #

def fixup_file_links(org: str, note_dir: PurePosixPath, m: Maps, stats: dict, fname: str) -> str:
    def sub(mo: re.Match) -> str:
        target, label = mo.group(1).strip(), (mo.group(2) or "").strip()
        # pandoc may render an anchor as  path::frag ; resolve_target handles ::
        res = resolve_target(target, note_dir, m)
        if res[0] == "id":
            return _org_link(res, label, embed=False)
        if res[0] == "file":
            new = res[1]
            return f"[[file:{new}][{label}]]" if label else f"[[file:{new}]]"
        if res[0] == "ext":
            return mo.group(0)
        # target ended in .md but no note matched -> a dangling internal link
        if re.search(r"\.md(::|#|$)", target, re.I):
            stats["unresolved"].append((fname, target))
        return mo.group(0)

    return ORG_FILE_LINK_RE.sub(sub, org)


# ---- tag harvesting -------------------------------------------------------- #

def harvest_tags(body: str) -> set[str]:
    tags: set[str] = set()
    for prot, chunk in split_protected(body):
        if prot:
            continue
        for line in chunk.splitlines():
            if MD_HEADING_RE.match(line):
                continue
            tags.update(TAG_RE.findall(line))
    return tags


# --------------------------------------------------------------------------- #
# markdown -> org
# --------------------------------------------------------------------------- #

def md_to_org_pandoc(body: str) -> str | None:
    try:
        r = subprocess.run(["pandoc", "--from=gfm", "--to=org", "--wrap=preserve"],
                           input=body, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def _inline_md_to_org(s: str) -> str:
    code: list[str] = []
    s = re.sub(r"`([^`\n]+)`", lambda mo: (code.append(mo.group(1)), f"\x00C{len(code)-1}\x00")[1], s)
    bold: list[str] = []
    s = re.sub(r"\*\*([^*]+)\*\*", lambda mo: (bold.append(mo.group(1)), f"\x00B{len(bold)-1}\x00")[1], s)
    s = re.sub(r"__([^_]+)__", lambda mo: (bold.append(mo.group(1)), f"\x00B{len(bold)-1}\x00")[1], s)
    s = re.sub(r"!\[([^\]]*)\]\(<?([^)>\s]+)>?[^)]*\)", lambda mo: f"[[file:{mo.group(2)}]]", s)
    s = re.sub(r"\[([^\]]+)\]\(<?([^)>\s]+)>?[^)]*\)", lambda mo: f"[[{mo.group(2)}][{mo.group(1)}]]", s)
    s = re.sub(r"~~([^~]+)~~", r"+\1+", s)
    s = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"/\1/", s)
    s = re.sub(r"(?<![\w_])_([^_\s][^_]*?)_(?![\w_])", r"/\1/", s)
    s = re.sub(r"\x00B(\d+)\x00", lambda mo: f"*{bold[int(mo.group(1))]}*", s)
    s = re.sub(r"\x00C(\d+)\x00", lambda mo: f"~{code[int(mo.group(1))]}~", s)
    return s


def md_to_org_fallback(md: str) -> str:
    out: list[str] = []
    in_fence = False
    quote: list[str] = []

    def flush_quote():
        if quote:
            out.append("#+begin_quote")
            out.extend(_inline_md_to_org(x) for x in quote)
            out.append("#+end_quote")
            quote.clear()

    for line in md.splitlines():
        mf = re.match(r"^(\s*)```+\s*([\w.+\-]*)\s*$", line)
        if mf:
            flush_quote()
            if not in_fence:
                in_fence = True
                out.append(f"#+begin_src {mf.group(2)}".rstrip())
            else:
                in_fence = False
                out.append("#+end_src")
            continue
        if in_fence:
            out.append(line)
            continue
        mq = re.match(r"^>\s?(.*)$", line)
        if mq:
            quote.append(mq.group(1))
            continue
        flush_quote()
        mh = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if mh:
            out.append("*" * len(mh.group(1)) + " " + _inline_md_to_org(mh.group(2)))
            continue
        if re.match(r"^\s{0,3}([-*_])\s*(\1\s*){2,}$", line):
            out.append("-----")
            continue
        ml = re.match(r"^(\s*)[*+\-]\s+(.*)$", line)
        if ml:
            out.append(f"{ml.group(1)}- {_inline_md_to_org(ml.group(2))}")
            continue
        mo = re.match(r"^(\s*)(\d+)[.)]\s+(.*)$", line)
        if mo:
            out.append(f"{mo.group(1)}{mo.group(2)}. {_inline_md_to_org(mo.group(3))}")
            continue
        out.append(_inline_md_to_org(line))
    if in_fence:
        out.append("#+end_src")
    flush_quote()
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# header drawer
# --------------------------------------------------------------------------- #

GENERIC_STEM_RE = re.compile(r"_?index|readme", re.I)


def _fallback_title(stem: str, rel_path: str) -> str:
    """Obsidian uses the filename as the note title, but a vault has dozens of
    `index.md` -- a bare "index" node is useless in org-roam-node-find.  For
    those generic names, qualify with the containing directory: java/btrace/index
    -> "btrace/index"."""
    if GENERIC_STEM_RE.fullmatch(stem):
        parent = PurePosixPath(rel_path).parent.name
        if parent:
            return f"{parent}/{stem}"
    return stem


def build_header(node_uuid: str, fm: dict, body_tags: set[str], stem: str, rel_path: str) -> str:
    title = fm.get("title")
    title = title.strip() if isinstance(title, str) and title.strip() else _fallback_title(stem, rel_path)
    aliases: list[str] = []
    for a in as_list(fm.get("aliases")) + as_list(fm.get("alias")):
        if a and a != title and a not in aliases:
            aliases.append(a)
    refs: list[str] = []
    for k in ("url", "source", "website", "link"):
        for v in as_list(fm.get(k)):
            if (URL_RE.match(v) or v.startswith("@")) and v not in refs:
                refs.append(v)
    tags = sorted({org_tag(t) for t in (set(as_list(fm.get("tags"))) | set(as_list(fm.get("tag"))) | body_tags)} - {""})

    props = [":PROPERTIES:", f":ID:       {node_uuid}"]
    if aliases:
        props.append(":ROAM_ALIASES: " + " ".join(f'"{a}"' for a in aliases))
    if refs:
        props.append(":ROAM_REFS: " + " ".join(refs))
    props.append(f":OBSIDIAN_PATH: {rel_path}")
    for k, v in fm.items():
        if k in CONSUMED_FM_KEYS:
            continue
        flat = ", ".join(as_list(v)) if isinstance(v, list) else str(v)
        flat = flat.replace("\n", " ").strip()
        kk = org_tag(k).upper()
        if flat and kk:
            props.append(f":OBSIDIAN_{kk}: {flat}")
    props.append(":END:")
    head = "\n".join(props) + f"\n#+title: {title}\n"
    if tags:
        head += "#+filetags: :" + ":".join(tags) + ":\n"
    return head


# --------------------------------------------------------------------------- #
# feature scan (heads-up list only)
# --------------------------------------------------------------------------- #

def feature_scan(body: str) -> set[str]:
    feats = set()
    if "![[" in body:
        feats.add("![[embed]]")
    if re.search(r"^>\s*\[!", body, re.M):
        feats.add("> [!callout]")
    if re.search(r"^```+\s*dataview", body, re.M):
        feats.add("dataview block")
    if re.search(r"^\s*\|.+\|\s*$", body, re.M) and re.search(r"^\s*\|[\s:|\-]+\|\s*$", body, re.M):
        feats.add("markdown table")
    if "$$" in body or re.search(r"(?<![\\\w])\$[^$\n]+\$", body):
        feats.add("LaTeX math")
    if re.search(r"%%.+?%%", body, re.S):
        feats.add("%%comment%%")
    return feats


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #

def convert_note(p: Path, src: Path, dst: Path, m: Maps, use_pandoc: bool, stats: dict, write: bool):
    rel = p.relative_to(src)
    fname = rel.as_posix()
    note_dir = PurePosixPath(rel.parent.as_posix())
    text = normalise(p.read_text("utf-8", errors="replace"))
    fm_raw, body = split_frontmatter(text)
    fm = parse_frontmatter(fm_raw)

    feats = feature_scan(body)
    if feats:
        stats["features"][fname] = feats

    body_ph, holders = stash_wikilinks(body)
    body_tags = harvest_tags(body)

    org = md_to_org_pandoc(body_ph) if use_pandoc else None
    if org is None:
        if use_pandoc:
            stats["pandoc_failures"].append(fname)
        org = md_to_org_fallback(body_ph)

    org = restore_wikilinks(org, holders, note_dir, m, stats, fname)
    org = fixup_file_links(org, note_dir, m, stats, fname)
    header = build_header(m.note_uuid[p], fm, body_tags, p.stem, fname)

    if write:
        out_path = (dst / rel).with_suffix(".org")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(header + "\n" + org.rstrip() + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert an Obsidian vault to an org-roam library.")
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--dst", type=Path, default=DEFAULT_DST)
    ap.add_argument("--force", action="store_true", help="write into --dst even if it is non-empty")
    ap.add_argument("--dry-run", action="store_true", help="resolve and report only; write nothing")
    ap.add_argument("--no-pandoc", action="store_true", help="force the built-in markdown->org converter")
    ap.add_argument("--print-config", action="store_true", help="print the init.el org-roam block and exit")
    args = ap.parse_args()

    if args.print_config:
        print(ORG_ROAM_CONFIG_SNIPPET)
        return 0

    src: Path = args.src.expanduser().resolve()
    dst: Path = args.dst.expanduser().resolve()
    if not src.is_dir():
        print(f"error: source vault not found: {src}", file=sys.stderr)
        return 2
    if not args.dry_run and dst.exists() and any(dst.iterdir()) and not args.force:
        print(f"error: {dst} exists and is not empty -- pass --force to overwrite", file=sys.stderr)
        return 2

    use_pandoc = (not args.no_pandoc) and shutil.which("pandoc") is not None
    md_files = list(iter_md_files(src))
    asset_files = list(iter_asset_files(src))
    print(f"vault   : {src}")
    print(f"  notes : {len(md_files)} .md")
    print(f"  assets: {len(asset_files)} other files")
    print(f"  md->org: {'pandoc' if use_pandoc else 'built-in fallback converter'}")
    print(f"  mode  : {'DRY RUN' if args.dry_run else 'write -> ' + str(dst)}")

    m = build_maps(md_files, asset_files, src)
    stats = {"unresolved": [], "embed_notes": 0, "embed_assets": 0, "pandoc_failures": [], "features": {}}

    if not args.dry_run:
        dst.mkdir(parents=True, exist_ok=True)
        for p in asset_files:                                    # assets first; a note wins on a clash
            out_path = dst / p.relative_to(src)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out_path)

    for i, p in enumerate(md_files, 1):
        convert_note(p, src, dst, m, use_pandoc, stats, write=not args.dry_run)
        if i % 300 == 0:
            print(f"  ... {i}/{len(md_files)}")

    report_path = None if args.dry_run else dst / "CONVERSION-REPORT.txt"
    _write_report(report_path, src, dst, md_files, asset_files, use_pandoc, m, stats, dry_run=args.dry_run)
    if args.dry_run:
        print("dry run complete -- nothing written")
    else:
        print(f"done -> {dst}")
        print(f"  report: {report_path}")
        print("  next: M-x my/package-refresh, restart Emacs, M-x org-roam-db-sync")
    return 0


def _write_report(path, src, dst, md_files, asset_files, use_pandoc, m: Maps, stats, *, dry_run):
    L: list[str] = []
    a = L.append
    a("Obsidian -> org-roam conversion report")
    a("=" * 40)
    a(f"source vault : {src}")
    a(f"target dir   : {dst}")
    a(f"mode         : {'DRY RUN (nothing written)' if dry_run else 'written'}")
    a(f"md -> org    : {'pandoc' if use_pandoc else 'built-in fallback converter'}")
    a(f"notes        : {len(md_files)}")
    a(f"assets       : {len(asset_files)} ({'not copied (dry run)' if dry_run else 'copied verbatim'})")
    a(f"![[note]] transclusions degraded to links : {stats['embed_notes']}")
    a(f"![[asset]] embeds rewritten to [[file:..]] : {stats['embed_assets']}")
    if stats["pandoc_failures"]:
        a(f"pandoc failed (fell back) on {len(stats['pandoc_failures'])} file(s): " + ", ".join(stats["pandoc_failures"][:50]))
    a("")
    uniq_unres = sorted(set(stats["unresolved"]))
    a(f"unresolved links (left as fuzzy/file links, point at nothing): {len(uniq_unres)}")
    for fname, tgt in uniq_unres[:400]:
        a(f"  {fname}  ->  {tgt}")
    if len(uniq_unres) > 400:
        a(f"  ... and {len(uniq_unres) - 400} more")
    a("")
    a(f"name collisions (two+ notes share a stem/title/alias; first one wins for bare [[name]] links): {len(m.collisions)}")
    for key, first, dup in m.collisions[:250]:
        a(f"  '{key}': kept {first.relative_to(src).as_posix()}   (also: {dup.relative_to(src).as_posix()})")
    if len(m.collisions) > 250:
        a(f"  ... and {len(m.collisions) - 250} more")
    a("")
    a("notes containing Obsidian-only constructs worth a manual look:")
    if stats["features"]:
        for fname in sorted(stats["features"]):
            a(f"  {fname}: {', '.join(sorted(stats['features'][fname]))}")
    else:
        a("  (none detected)")
    a("")
    a("-" * 40)
    a("Add to ~/.emacs.d/init.el:")
    a("")
    a(ORG_ROAM_CONFIG_SNIPPET)
    text = "\n".join(L) + "\n"
    if path is None:
        print("\n" + text)
    else:
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
