#!/usr/bin/env bash
# 2-second GPU and host-memory samples while a timed run is in flight.
# usage: tele.sh start|stop DIR [WORKER]   (WORKER: ssh destination of the other rank; omit for one Spark)
set -u
Q=~/qual-20261110; D=$(realpath -m "$2"); W=${3:-}
case $1 in
  start)
    mkdir -p "$D"; rm -f "$D"/host0-gpu.stop "$D"/host0-memory.stop
    nohup python3 $Q/tools/gpu_telemetry.py "$D/host0-gpu.jsonl" >/dev/null 2>&1 &
    nohup python3 $Q/tools/host_memory.py "$D/host0-memory.jsonl" >/dev/null 2>&1 &
    [[ -z $W ]] || ssh -o BatchMode=yes "$W" 'mkdir -p /tmp/qual-tele; rm -f /tmp/qual-tele/*
      nohup python3 ~/qual-20261110/tools/gpu_telemetry.py /tmp/qual-tele/host1-gpu.jsonl >/dev/null 2>&1 &
      nohup python3 ~/qual-20261110/tools/host_memory.py /tmp/qual-tele/host1-memory.jsonl >/dev/null 2>&1 &' ;;
  stop)
    touch "$D/host0-gpu.stop" "$D/host0-memory.stop"
    [[ -z $W ]] || { ssh -o BatchMode=yes "$W" 'touch /tmp/qual-tele/host1-gpu.stop /tmp/qual-tele/host1-memory.stop; sleep 3'
                     scp -q "$W":/tmp/qual-tele/host1-*.jsonl "$D/"; }
    sleep 3; rm -f "$D"/*.stop ;;
esac
