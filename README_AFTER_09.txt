FIGHT ROYALE GODOT — INSTALLERS AFTER UPDATE 09

Includes Update 09b, 10, 11, 12A–D, 13A–C, 14A–C, 15A–D and 16A–C.
Total: 20 standalone Python installers. Update 09 (Skills and Combos) is NOT included, since you already installed it.

1. Extract this ZIP DIRECTLY into your existing Godot project folder (the folder containing project.godot).
2. Open PowerShell in that folder (as usual).
3. Run: .\run_after_09_with_commits.cmd

The .cmd runs each Python installer in order, runs `git add .`, and commits the result before moving to the next update. It stops when an installer or Git command fails. Rerunning after a failure is possible, since installers are designed to be repeat-safe, but inspect any error and restore backups if necessary.

PowerShell command-by-command version: see terminal_commands_after_09.txt.

WARNING: `git add .` stages ALL changed/untracked files in the project, including VRMs/SFX or Godot caches. For GitHub's 100 MB per-file limit, consider a suitable .gitignore and Git LFS for large assets before running, or use the step-by-step commands to inspect `git status` first. Don't remove existing assets from your project.

These scripts were previously Python-tested against project copies; gameplay in your updated local Godot installation is not verified here. Update 16C requires the previous 16B; install sequentially.
