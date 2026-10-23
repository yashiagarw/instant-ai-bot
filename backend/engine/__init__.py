"""Diagnosis engine: plain Python, no web framework imports (see README.md)."""

from engine.core import DISCLAIMER, ENGINE_VERSION, Engine, coverage_level, diagnose, vehicle_allows
from engine.types import ROUTE_QUESTION, Answer, Knowledge, Request, Result, Vehicle

__all__ = [
    "DISCLAIMER",
    "ENGINE_VERSION",
    "ROUTE_QUESTION",
    "Answer",
    "Engine",
    "Knowledge",
    "Request",
    "Result",
    "Vehicle",
    "coverage_level",
    "diagnose",
    "vehicle_allows",
]
