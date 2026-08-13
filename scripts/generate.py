#!/usr/bin/env python3
"""Render README.md from README.template.md, config.json and GitHub repo data.

Reads the JSON that `gh repo list --json ...` produces and writes the rendered
page to stdout. Pure with respect to the data: no network access, so the whole
renderer is testable against a fixture.
"""

import json
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
    """Bucket repos by topic. Exactly one section is the catch-all (topic: null).

    Raises ValueError if a repo matches more than one section, rather than
    guessing a precedence. An ambiguous repo is a topic mistake worth surfacing.
    """
    catch_all = [s["id"] for s in sections if s["topic"] is None]
    if len(catch_all) != 1:
        raise ValueError("config must define exactly one catch-all section")

    buckets = {s["id"]: [] for s in sections}
    for repo in repos:
        if repo["isPrivate"] or repo["name"] in exclude:
            continue
        names = topics_of(repo)
        matched = [s["id"] for s in sections if s["topic"] and s["topic"] in names]
        if len(matched) > 1:
            raise ValueError(
                f"{repo['name']} matches sections {', '.join(matched)}; "
                "remove one of its topics"
            )
        buckets[matched[0] if matched else catch_all[0]].append(repo)
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


def render_bullets(repos, user):
    lines = []
    for r in repos:
        count = r["stargazerCount"]
        stars = f"{count}{STAR} " if count else ""
        lines.append(f"- {stars}**[{r['name']}]({repo_url(user, r)})**: {r['description']}")
    return "\n".join(lines)


def render_inline(repos, user):
    return " ·\n".join(f"[{r['name']}]({repo_url(user, r)})" for r in repos)


RENDERERS = {"bullets": render_bullets, "inline": render_inline}


def render(template, config, repos):
    user = config["user"]
    buckets = assign(repos, config["sections"], config["exclude"])
    output = template.replace("{{total_stars}}", str(total_stars(repos)))
    for section in config["sections"]:
        sid = section["id"]
        ordered = sort_bucket(buckets[sid], config["featured"].get(sid, []))
        block = RENDERERS[section["style"]](ordered, user)
        output = output.replace("{{" + sid + "}}", block)
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
