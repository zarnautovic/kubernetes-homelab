#!/usr/bin/env python3
# Thin wrapper: the real script lives next to its CronJob manifests so kustomize can ship it as a ConfigMap.
import os, runpy, sys
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kubernetes", "apps", "image-audit", "image-audit.py"), run_name="__main__")
