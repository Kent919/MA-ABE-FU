# Repository publication

The directory is ready to publish as the reproducibility repository for the manuscript.

Before using SSH, add the local public key to GitHub:

1. Open GitHub Settings.
2. Go to SSH and GPG keys.
3. Add the content of the local public key file, typically `~/.ssh/id_ed25519.pub`, as a new SSH key.
4. Verify with `ssh -T git@github.com`.

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
