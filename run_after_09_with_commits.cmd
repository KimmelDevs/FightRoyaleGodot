@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist "project.godot" (
  echo ERROR: Extract this ZIP directly into your Godot project folder first.
  exit /b 1
)
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo ERROR: Git repository not initialized here.
  exit /b 1
)

call :apply "install_09b_third_person.py" "Fight Royale Godot Update 09B"
if errorlevel 1 exit /b 1
call :apply "install_10_duel_vs_cpu.py" "Fight Royale Godot Update 10"
if errorlevel 1 exit /b 1
call :apply "install_11_cpu_vs_cpu.py" "Fight Royale Godot Update 11"
if errorlevel 1 exit /b 1
call :apply "install_12a_advanced_ai.py" "Fight Royale Godot Update 12A"
if errorlevel 1 exit /b 1
call :apply "install_12b_projectile_defense.py" "Fight Royale Godot Update 12B"
if errorlevel 1 exit /b 1
call :apply "install_12c_whiff_punish.py" "Fight Royale Godot Update 12C"
if errorlevel 1 exit /b 1
call :apply "install_12d_master_ai.py" "Fight Royale Godot Update 12D"
if errorlevel 1 exit /b 1
call :apply "install_13a_ai_personalities.py" "Fight Royale Godot Update 13A"
if errorlevel 1 exit /b 1
call :apply "install_13b_tactical_identities.py" "Fight Royale Godot Update 13B"
if errorlevel 1 exit /b 1
call :apply "install_13c_adaptive_ai.py" "Fight Royale Godot Update 13C"
if errorlevel 1 exit /b 1
call :apply "install_14a_projectile_clashes.py" "Fight Royale Godot Update 14A"
if errorlevel 1 exit /b 1
call :apply "install_14b_projectile_visuals.py" "Fight Royale Godot Update 14B"
if errorlevel 1 exit /b 1
call :apply "install_14c_projectile_impacts.py" "Fight Royale Godot Update 14C"
if errorlevel 1 exit /b 1
call :apply "install_15a_status_foundation.py" "Fight Royale Godot Update 15A"
if errorlevel 1 exit /b 1
call :apply "install_15b_control_statuses.py" "Fight Royale Godot Update 15B"
if errorlevel 1 exit /b 1
call :apply "install_15c_damage_healing.py" "Fight Royale Godot Update 15C"
if errorlevel 1 exit /b 1
call :apply "install_15d_status_hud.py" "Fight Royale Godot Update 15D"
if errorlevel 1 exit /b 1
call :apply "install_16a_animation_lab.py" "Fight Royale Godot Update 16A"
if errorlevel 1 exit /b 1
call :apply "install_16b_advanced_animations.py" "Fight Royale Godot Update 16B"
if errorlevel 1 exit /b 1
call :apply "install_16c_animation_lab_tools.py" "Fight Royale Godot Update 16C"
if errorlevel 1 exit /b 1

echo.
echo All 20 updates processed.
exit /b 0


:apply
echo.
echo Installing %~1 ...
python "%~1"
if errorlevel 1 (
  echo ERROR: Installer failed: %~1. Stopping.
  exit /b 1
)
git add .
if errorlevel 1 (
  echo ERROR: git add failed. Stopping.
  exit /b 1
)
git diff --cached --quiet
if errorlevel 2 (
  echo ERROR: Cannot examine staged changes. Stopping.
  exit /b 1
)
if errorlevel 1 (
  git commit -m "%~2"
  if errorlevel 1 (
    echo ERROR: git commit failed. Stopping.
    exit /b 1
  )
) else (
  echo No new changes to commit for %~1.
)
exit /b 0
