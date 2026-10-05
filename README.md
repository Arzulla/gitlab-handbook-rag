# gitlab-handbook-rag

## Data & license

- Content of the GitLab Handbook is © GitLab B.V. The
  [handbook repository](https://gitlab.com/gitlab-com/content-sites/handbook) is published
  under the MIT license (see its `LICENSE` file).
- The corpus is **downloaded at build time** (`make data`, shallow sparse clone at a pinned
  commit) and is **not redistributed** in this repository; `data/` is git-ignored.
- The **access model is simulated**: the handbook is public, and the role → section
  permissions in `config/access.yaml` are invented on top of its department structure
  to demonstrate permission-aware retrieval.
