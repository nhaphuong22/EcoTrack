@echo off
title EcoTrack Local CI Validation
powershell -ExecutionPolicy Bypass -File "%~dp0check_ci.ps1"
pause
