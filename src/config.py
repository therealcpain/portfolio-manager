"""
Configuration loader for Hedge Fund OS.
Reads config.yaml and exposes typed settings.
Advisory only — no live trading.
"""

from pathlib import Path
import yaml


ROOT_DIR = Path(__file__).parent.parent
CONFIG_PATH = ROOT_DIR / "config.yaml"
PORTFOLIO_DIR = ROOT_DIR / "portfolio"
REPORTS_DIR = ROOT_DIR / "reports"
BENCHMARKS_DIR = ROOT_DIR / "benchmarks"
ALT_PORTFOLIOS_DIR = ROOT_DIR / "alternative_portfolios"
SCHEMAS_DIR = ROOT_DIR / "schemas"
DATA_DIR = ROOT_DIR / "data"
SIMULATIONS_DIR = ROOT_DIR / "simulations"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_portfolio() -> dict:
    path = PORTFOLIO_DIR / "current_portfolio.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def load_thesis_log() -> dict:
    path = PORTFOLIO_DIR / "thesis_log.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def load_watchlist() -> dict:
    path = PORTFOLIO_DIR / "watchlist.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def load_benchmark_config() -> dict:
    path = BENCHMARKS_DIR / "benchmark_config.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def load_alternative_portfolio(name: str) -> dict:
    path = ALT_PORTFOLIOS_DIR / f"{name}.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


CONFIG = load_config()
STARTING_CAPITAL = CONFIG["portfolio"]["starting_capital"]
ADVISORY_DISCLAIMER = CONFIG["system"]["disclaimer"]
