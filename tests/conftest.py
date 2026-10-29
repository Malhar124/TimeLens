from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


@pytest.fixture
def minimal_paths() -> tuple[Path, Path]:
    return EX / "loan_minimal/loan_minimal.bpmn", EX / "loan_minimal/loan_minimal.rules.json"


@pytest.fixture
def full_paths() -> tuple[Path, Path]:
    return EX / "loan_full/loan_full.bpmn", EX / "loan_full/loan_full.rules.json"
