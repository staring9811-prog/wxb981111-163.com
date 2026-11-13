#!/bin/sh
cd "$(dirname "$0")" && git pull; (xdg-open play.html || open play.html) >/dev/null 2>&1
