"""Diagnosis engine: plain Python, no web framework imports (see README.md)."""

from engine.core import DISCLAIMER, ENGINE_VERSION, Engine, coverage_level, diagnose, vehicle_allows
from engine.types import ROUTE_QUESTION, Answer, Knowledge, Request, Result, Vehicle
from engine.v2 import ENGINE_VERSION_V2, EngineV2, make_engine, uncertainty_messages

__all__ = [
    "DISCLAIMER",
    "ENGINE_VERSION",
    "ENGINE_VERSION_V2",
    "ROUTE_QUESTION",
    "Answer",
    "Engine",
    "EngineV2",
    "Knowledge",
    "Request",
    "Result",
    "Vehicle",
    "coverage_level",
    "diagnose",
    "make_engine",
    "uncertainty_messages",
    "vehicle_allows",
]
