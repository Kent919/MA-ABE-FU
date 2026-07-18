# Repository publication

The directory is ready to publish as the reproducibility repository for the manuscript.

```bash
git init -b main
git add .
git commit -m "Add MA-ABE-FU reproducibility package"
git remote add origin https://github.com/Kent919/MA-ABE-FU.git
git push -u origin main
```

If the remote already exists, replace the `git remote add` command with:

```bash
git remote set-url origin https://github.com/Kent919/MA-ABE-FU.git
```

The repository contains scripts, exact CSV/JSON outputs, five vector PDF figures, five 600 dpi TIFF figures, and the reference export. Public datasets should remain outside version control unless redistribution rights are clear.
