#!/usr/bin/env python3
"""Render README.md from README.template.md, config.json and GitHub repo data.

Reads the JSON that `gh repo list --json ...` produces and writes the rendered
page to stdout. Pure with respect to the data: no network access, so the whole
renderer is testable against a fixture.
"""

import json
import re
import sys
from pathlib import Path

STAR = "⭐"


def topics_of(repo):
    """Topic names as a set. The API sends null rather than [] when there are none."""
    return {t["name"] for t in (repo.get("repositoryTopics") or [])}


def total_stars(repos):
    """Every public repo counts, forks included. Private repos never do."""
    return sum(r["stargazerCount"] for r in repos if not r["isPrivate"])


def assign(repos, sections, exclude):
    """Bucket repos: by topic first, then forks, then the catch-all.

    A section names a topic, or is the forks section (`forks: true`), or is the
    catch-all (neither). Topics win, so a fork that carries a section's topic
    stays there, and only a fork that matches no topic section reaches the forks
    section. Without a forks section such forks fall to the catch-all instead.

    Raises ValueError if a repo matches more than one topic section, rather than
    guessing a precedence. An ambiguous repo is a topic mistake worth surfacing.
    """
    catch_all = [s["id"] for s in sections if not s.get("topic") and not s.get("forks")]
    forks = [s["id"] for s in sections if s.get("forks")]
    if len(catch_all) != 1:
        raise ValueError("config must define exactly one catch-all section")
    if len(forks) > 1:
        raise ValueError("config must define at most one forks section")

    buckets = {s["id"]: [] for s in sections}
    for repo in repos:
        if repo["isPrivate"] or repo["name"] in exclude:
            continue
        names = topics_of(repo)
        matched = [s["id"] for s in sections if s.get("topic") and s["topic"] in names]
        if len(matched) > 1:
            raise ValueError(
                f"{repo['name']} matches sections {', '.join(matched)}; "
                "remove one of its topics"
            )
        if matched:
            target = matched[0]
        elif forks and repo["isFork"]:
            target = forks[0]
        else:
            target = catch_all[0]
        buckets[target].append(repo)
    return buckets


def sort_bucket(bucket, featured):
    """Featured repos first in listed order, then the rest by stars descending.

    Star order is the sensible default, so `featured` only has to record the
    deliberate exceptions to it. The trailing name key keeps the result stable
    when counts tie, which they do across the whole thesis section.
    """
    index = {name: i for i, name in enumerate(featured)}
    return sorted(
        bucket,
        key=lambda r: (
            index.get(r["name"], len(featured)),
            -r["stargazerCount"],
            r["name"],
        ),
    )


def repo_url(user, repo):
    return f"https://github.com/{user}/{repo['name']}"


def upstream_of(repo):
    """The `owner/name` a fork was taken from.

    GitHub reports the repo it currently records the fork as taken from, which
    is not always the repo a pull request was opened against: deleting an
    upstream promotes its oldest fork. A fork whose upstream is gone entirely
    has no parent, and the page refuses to guess a label for it.
    """
    parent = repo.get("parent")
    if not parent:
        raise ValueError(
            f"{repo['name']} is a fork with no upstream; exclude it or give it a topic"
        )
    return f"{parent['owner']['login']}/{parent['name']}"


def bullet(label, url, description, count=0):
    stars = f"{count}{STAR} " if count else ""
    suffix = f": {description}" if description else ""
    return f"- {stars}**[{label}]({url})**{suffix}"


def render_bullets(repos, user):
    return "\n".join(
        bullet(r["name"], repo_url(user, r), r["description"], r["stargazerCount"])
        for r in repos
    )


def render_upstream(repos, user):
    """One bullet per fork: the upstream's name, linked to the fork.

    The name credits the project; the link lands on the fork, where the work
    is. No star count: a count in front of someone else's repo name reads as
    that repo's count. The fork's own stars still reach the intro total.
    """
    lines = []
    for r in repos:
        lines.append(bullet(upstream_of(r), repo_url(user, r), r["description"]))
    return "\n".join(lines)


def render_inline(repos, user):
    return " ·\n".join(f"[{r['name']}]({repo_url(user, r)})" for r in repos)


RENDERERS = {
    "bullets": render_bullets,
    "inline": render_inline,
    "upstream": render_upstream,
}


def render(template, config, repos):
    """Substitute every section's placeholder.

    A section that carries its own `heading` in the config is one that may be
    empty: it renders heading and list together, and vanishes with its
    placeholder line when nothing is in it. Every other heading stays in the
    template, where the hand-written text belongs, so an empty bucket there
    is an error rather than a dangling heading.
    """
    user = config["user"]
    buckets = assign(repos, config["sections"], config["exclude"])
    output = template.replace("{{total_stars}}", str(total_stars(repos)))
    for section in config["sections"]:
        sid = section["id"]
        placeholder = "{{" + sid + "}}"
        if placeholder not in template:
            raise ValueError(f"template has no {placeholder}")
        ordered = sort_bucket(buckets[sid], config["featured"].get(sid, []))
        if ordered:
            block = RENDERERS[section["style"]](ordered, user)
            if "heading" in section:
                block = f"### {section['heading']}\n\n{block}"
            output = output.replace(placeholder, block)
        elif "heading" in section:
            output = re.sub(re.escape(placeholder) + r"\n{0,2}", "", output)
        else:
            raise ValueError(
                f"section {sid} has no repos; its heading in the template would dangle"
            )
    return output


def main(argv):
    if len(argv) != 2:
        print("usage: generate.py <repos.json>", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parent.parent
    repos = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    template = (root / "README.template.md").read_text(encoding="utf-8")
    sys.stdout.write(render(template, config, repos))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
