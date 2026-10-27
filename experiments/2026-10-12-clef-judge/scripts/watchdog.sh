#!/bin/zsh
# Unload clef-flash if macOS memory pressure goes critical (level 4). Logs pressure every 5s.
LOG=${0:h}/watchdog.log
while true; do
  lvl=$(sysctl -n kern.memorystatus_vm_pressure_level)
  swp=$(sysctl -n vm.swapusage | awk '{print $6}')
  echo "$(date +%T) pressure=$lvl swap_used=$swp" >> $LOG
  if [ "$lvl" -ge 4 ]; then echo "$(date +%T) CRITICAL -> ollama stop" >> $LOG; ollama stop clef-flash; fi
  sleep 5
done
