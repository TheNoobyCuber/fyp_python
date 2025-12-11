#!/usr/bin/env python3
import sys
print("Python path:", sys.executable)

try:
    import pymysql
    print("✓ pymysql imported successfully")
    print(f"  Version: {pymysql.__version__}")
except ImportError as e:
    print("✗ Failed to import pymysql:", e)

try:
    from flask import Flask
    print("✓ Flask imported successfully")
except ImportError as e:
    print("✗ Failed to import Flask:", e)