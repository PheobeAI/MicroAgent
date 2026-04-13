# conftest.py - 确保项目根目录在 sys.path 中
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
