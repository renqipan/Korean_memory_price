from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .backtest import BACKTEST_COLUMNS, build_prosperity_backtest
from .categories import (
    CORE_CATEGORY_KEY,
    DEFAULT_FETCH_HS_CODES,
    matches_category,
    parse_memory_categories,
)
from .charts import (
    render_category_price_trend_png,
    render_category_price_trends_png,
    render_memory_indicators_png,
    render_memory_score_png,
    render_overall_prosperity_png,
)
from .io_utils import read_trade_records, write_trade_records
from .kcs import KCSClient
from .metrics import (
    CATEGORY_INDEX_COLUMNS,
    INDEX_COLUMNS,
    UNIT_PRICE_COLUMNS,
    build_category_memory_indexes,
    build_memory_index,
    build_unit_price_rows,
    latest_summary,
)
from .prosperity import (
    MODEL_VERSION,
    OVERALL_MODEL_VERSION,
    OVERALL_PROSPERITY_COLUMNS,
    PROSPERITY_COLUMNS,
    build_overall_prosperity_index,
    build_prosperity_scores,
)
from .trass import load_trass_export
from .utils import current_month, month_to_yymm, parse_number, write_csv_rows
from .validation import EXTERNAL_VALIDATION_COLUMNS, build_external_validation


DEFAULT_HS_CODES = DEFAULT_FETCH_HS_CODES
CATEGORY_GROWTH_SUMMARY_CATEGORIES = ("dram", "flash_memory", "multichip_memory")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="korean-memory-price",
        description="Compute Korean memory export unit values from KCS/TRASS data.",
    )
    subparsers = parser.add_subparsers(required=True)

    kcs_fetch = subparsers.add_parser("kcs-fetch", help="Fetch monthly HS data from KCS OpenAPI.")
    add_kcs_args(kcs_fetch)
    kcs_fetch.add_argument("--out", required=True, help="Output trade CSV path.")
    kcs_fetch.set_defaults(func=cmd_kcs_fetch)

    trass_import = subparsers.add_parser("trass-import", help="Import a TRASS CSV/XLSX export.")
    trass_import.add_argument("--file", required=True, help="TRASS export file path.")
    trass_import.add_argument("--out", required=True, help="Output trade CSV path.")
    trass_import.set_defaults(func=cmd_trass_import)

    price = subparsers.add_parser("price", help="Compute unit values and the core memory index.")
    price.add_argument("--input", nargs="+", required=True, help="Trade CSV files from kcs-fetch/trass-import.")
    price.add_argument("--out", required=True, help="Unit value CSV path.")
    price.add_argument("--index-out", required=True, help="Composite memory index CSV path.")
    price.add_argument("--score-out", help="Optional memory prosperity score CSV path.")
    price.add_argument("--category-index-out", help="Optional category-level price index CSV path.")
    price.add_argument("--overall-out", help="Optional overall memory prosperity CSV path.")
    price.add_argument("--backtest-out", help="Optional historical prosperity backtest CSV path.")
    price.add_argument(
        "--external-benchmark",
        help="Optional external benchmark CSV for classification and price-proxy checks.",
    )
    price.add_argument(
        "--validation-out",
        help="External validation CSV path; requires --external-benchmark.",
    )
    add_category_args(price)
    price.set_defaults(func=cmd_price)

    chart = subparsers.add_parser("chart", help="Render PNG charts for memory prosperity.")
    chart.add_argument("--prosperity", required=True, help="memory_prosperity_score.csv path.")
    chart.add_argument("--category-index", help="memory_category_price_index.csv path.")
    chart.add_argument("--overall-prosperity", help="memory_overall_prosperity.csv path.")
    chart.add_argument("--outdir", required=True, help="Chart output directory.")
    chart.set_defaults(func=cmd_chart)

    validate = subparsers.add_parser(
        "validate",
        help="Compare a category index CSV with an external benchmark CSV.",
    )
    validate.add_argument("--category-index", required=True)
    validate.add_argument("--benchmark", required=True)
    validate.add_argument("--out", required=True)
    validate.set_defaults(func=cmd_validate)

    run = subparsers.add_parser("run", help="Run KCS fetch and memory prosperity calculation.")
    add_kcs_args(run)
    add_category_args(run)
    run.add_argument("--trass-file", action="append", default=[], help="Optional TRASS export file to merge.")
    run.add_argument("--no-charts", action="store_true", help="Do not render PNG charts.")
    run.add_argument(
        "--external-benchmark",
        help="Optional external benchmark CSV for classification and price-proxy checks.",
    )
    run.add_argument("--outdir", required=True, help="Output directory.")
    run.set_defaults(func=cmd_run)
    return parser


def add_kcs_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", required=True, help="Start month, YYYYMM.")
    parser.add_argument(
        "--end",
        required=True,
        help="End month, YYYYMM, or latest. 'latest' probes completed calendar months; finality is unverified.",
    )
    parser.add_argument("--hs", action="append", default=[], help="HS/HSK code. Can be repeated.")
    parser.add_argument("--service-key", help="KCS/data.go.kr service key. Defaults to DATA_GO_KR_SERVICE_KEY.")
    parser.add_argument(
        "--encoded-key",
        action="store_true",
        help="Use when the service key is already URL-encoded.",
    )
    parser.add_argument(
        "--endpoint",
        choices=["data-go-kr", "legacy"],
        default="data-go-kr",
        help="KCS API endpoint style.",
    )


def add_category_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        help=(
            "Add a category as name=hs1,hs2 or name:Label=hs1,hs2. "
            "Defaults separate memory ICs, solid-state media, and storage devices."
        ),
    )


def cmd_kcs_fetch(args: argparse.Namespace) -> int:
    records = fetch_kcs_records(args)
    write_trade_records(records, args.out)
    print(f"Wrote {len(records)} KCS trade rows to {args.out}")
    return 0


def cmd_trass_import(args: argparse.Namespace) -> int:
    records = load_trass_export(args.file)
    write_trade_records(records, args.out)
    print(f"Wrote {len(records)} TRASS trade rows to {args.out}")
    return 0


def cmd_price(args: argparse.Namespace) -> int:
    records = read_trade_records(args.input)
    unit_rows = build_unit_price_rows(records)
    categories = parse_categories(args)
    index_rows = build_core_memory_index(unit_rows, categories)
    category_rows = build_category_memory_indexes(unit_rows, categories)
    score_rows = build_prosperity_scores(index_rows)
    overall_rows = build_overall_prosperity_index(score_rows, category_rows)
    backtest_rows = build_prosperity_backtest(index_rows, score_rows)
    validation_rows = _build_requested_validation(args, category_rows)
    write_csv_rows(unit_rows, args.out, UNIT_PRICE_COLUMNS)
    write_csv_rows(index_rows, args.index_out, INDEX_COLUMNS)
    if args.category_index_out:
        write_csv_rows(category_rows, args.category_index_out, CATEGORY_INDEX_COLUMNS)
    if args.score_out:
        write_csv_rows(score_rows, args.score_out, PROSPERITY_COLUMNS)
    if args.overall_out:
        write_csv_rows(overall_rows, args.overall_out, OVERALL_PROSPERITY_COLUMNS)
    if args.backtest_out:
        write_csv_rows(backtest_rows, args.backtest_out, BACKTEST_COLUMNS)
    if validation_rows is not None:
        if not args.validation_out:
            raise SystemExit("--validation-out is required with --external-benchmark.")
        write_csv_rows(
            validation_rows,
            args.validation_out,
            EXTERNAL_VALIDATION_COLUMNS,
        )
    summary = latest_summary(index_rows)
    print(f"Wrote {len(unit_rows)} unit value rows to {args.out}")
    print(f"Wrote {len(index_rows)} memory index rows to {args.index_out}")
    if args.category_index_out:
        print(f"Wrote {len(category_rows)} category unit value index rows to {args.category_index_out}")
    if args.score_out:
        print(f"Wrote {len(score_rows)} memory prosperity score rows to {args.score_out}")
    if args.overall_out:
        print(f"Wrote {len(overall_rows)} overall memory prosperity rows to {args.overall_out}")
    if args.backtest_out:
        print(f"Wrote {len(backtest_rows)} prosperity backtest rows to {args.backtest_out}")
    if validation_rows is not None:
        print(f"Wrote {len(validation_rows)} external validation rows to {args.validation_out}")
    if summary:
        print(
            "Latest memory index: "
            f"{summary.get('month')} index={summary.get('memory_index')} "
            f"3m={summary.get('memory_index_mom_3m_pct')} "
            f"yoy={summary.get('memory_index_yoy_pct')}"
        )
    print_latest_category_growth_summary(category_rows)
    return 0


def _write_run_manifest(args, outdir, trade_path, all_records, index_rows):
    manifest = {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_start": args.start,
        "requested_end": args.end,
        "latest_observed_month": index_rows[-1]["month"] if index_rows else None,
        "publication_status": "unverified_not_necessarily_final",
        "raw_snapshot_dir": str(args.snapshot_dir),
        "trade_sha256": hashlib.sha256(trade_path.read_bytes()).hexdigest(),
        "record_count": len(all_records),
        "model_version": MODEL_VERSION,
        "overall_model_version": OVERALL_MODEL_VERSION,
        "warnings": [],
    }
    if index_rows and str(index_rows[-1]["month"]) >= current_month():
        manifest["warnings"].append("Explicit end month includes an incomplete calendar month")
    if index_rows:
        current_codes = set(str(index_rows[-1]["hs_codes"]).split(";"))
        prior_codes = {hs for row in index_rows[-13:-1] for hs in str(row["hs_codes"]).split(";")}
        missing = sorted(prior_codes - current_codes)
        if missing:
            manifest["warnings"].append(f"Latest month missing previously observed core HS codes: {missing}")
        if (parse_number(index_rows[-1].get("pricing_value_coverage_pct")) or 0) < 95:
            manifest["warnings"].append("Latest month pricing coverage below 95%")
    else:
        raise SystemExit("No core memory records returned; no successful run manifest written")
    snapshot_dir = Path(args.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    manifest["raw_response_sha256"] = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(snapshot_dir.glob("*.xml"))
    }
    content = json.dumps(manifest, indent=2) + "\n"
    (snapshot_dir / "run_manifest.json").write_text(content, encoding="utf-8")
    (outdir / "run_manifest.json").write_text(content, encoding="utf-8")
    print("Publication status: unverified (API availability is not proof of final statistics).")
    for warning in manifest["warnings"]:
        print(f"WARNING: {warning}")
    return 0


def cmd_chart(args: argparse.Namespace) -> int:
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    prosperity_rows = _read_generic_csv(args.prosperity)
    score_path = outdir / "memory_prosperity_score.png"
    indicator_path = outdir / "memory_indicators.png"
    render_memory_score_png(prosperity_rows, score_path)
    render_memory_indicators_png(prosperity_rows, indicator_path)
    print(f"Wrote memory prosperity score chart to {score_path}")
    print(f"Wrote indicator chart to {indicator_path}")
    if args.overall_prosperity:
        overall_rows = _read_generic_csv(args.overall_prosperity)
        overall_path = outdir / "memory_overall_prosperity.png"
        render_overall_prosperity_png(overall_rows, overall_path)
        print(f"Wrote overall memory prosperity chart to {overall_path}")
    if args.category_index:
        category_rows = _read_generic_csv(args.category_index)
        category_trends_path = outdir / "memory_category_price_trends.png"
        render_category_price_trends_png(category_rows, category_trends_path)
        print(f"Wrote category price trend chart to {category_trends_path}")
        for category in sorted({str(row.get("category")) for row in category_rows if row.get("category")}):
            category_path = outdir / f"memory_price_trend_{category}.png"
            render_category_price_trend_png(category_rows, category, category_path)
            print(f"Wrote category price trend chart to {category_path}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    category_rows = _read_generic_csv(args.category_index)
    benchmark_rows = _read_generic_csv(args.benchmark)
    validation_rows = build_external_validation(category_rows, benchmark_rows)
    write_csv_rows(validation_rows, args.out, EXTERNAL_VALIDATION_COLUMNS)
    print(f"Wrote {len(validation_rows)} external validation rows to {args.out}")
    print_external_validation_summary(validation_rows)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    kcs_records = fetch_kcs_records(args)
    all_records = list(kcs_records)
    for trass_file in args.trass_file:
        all_records.extend(load_trass_export(trass_file))

    trade_path = outdir / "memory_trade.csv"
    unit_path = outdir / "memory_unit_prices.csv"
    index_path = outdir / "memory_price_index.csv"
    category_index_path = outdir / "memory_category_price_index.csv"
    score_path = outdir / "memory_prosperity_score.csv"
    overall_path = outdir / "memory_overall_prosperity.csv"
    backtest_path = outdir / "memory_prosperity_backtest.csv"
    validation_path = outdir / "memory_external_validation.csv"
    chart_dir = outdir / "charts"

    unit_rows = build_unit_price_rows(all_records)
    categories = parse_categories(args)
    index_rows = build_core_memory_index(unit_rows, categories)
    category_rows = build_category_memory_indexes(unit_rows, categories)
    score_rows = build_prosperity_scores(index_rows)
    overall_rows = build_overall_prosperity_index(score_rows, category_rows)
    backtest_rows = build_prosperity_backtest(index_rows, score_rows)
    validation_rows = _build_requested_validation(args, category_rows)
    if not index_rows:
        raise SystemExit("No core memory records returned; existing outputs were not replaced")
    write_trade_records(all_records, trade_path)
    write_csv_rows(unit_rows, unit_path, UNIT_PRICE_COLUMNS)
    write_csv_rows(index_rows, index_path, INDEX_COLUMNS)
    write_csv_rows(category_rows, category_index_path, CATEGORY_INDEX_COLUMNS)
    write_csv_rows(score_rows, score_path, PROSPERITY_COLUMNS)
    write_csv_rows(overall_rows, overall_path, OVERALL_PROSPERITY_COLUMNS)
    write_csv_rows(backtest_rows, backtest_path, BACKTEST_COLUMNS)
    if validation_rows is not None:
        write_csv_rows(
            validation_rows,
            validation_path,
            EXTERNAL_VALIDATION_COLUMNS,
        )

    if not args.no_charts:
        chart_dir.mkdir(parents=True, exist_ok=True)
        render_memory_score_png(score_rows, chart_dir / "memory_prosperity_score.png")
        render_overall_prosperity_png(overall_rows, chart_dir / "memory_overall_prosperity.png")
        render_memory_indicators_png(score_rows, chart_dir / "memory_indicators.png")
        render_category_price_trends_png(category_rows, chart_dir / "memory_category_price_trends.png")
        for category in sorted({str(row.get("category")) for row in category_rows if row.get("category")}):
            render_category_price_trend_png(
                category_rows,
                category,
                chart_dir / f"memory_price_trend_{category}.png",
            )

    print(f"Wrote trade data to {trade_path}")
    print(f"Wrote unit values to {unit_path}")
    print(f"Wrote memory index to {index_path}")
    print(f"Wrote category unit value index to {category_index_path}")
    print(f"Wrote memory prosperity score to {score_path}")
    print(f"Wrote overall memory prosperity to {overall_path}")
    print(f"Wrote prosperity backtest to {backtest_path}")
    if validation_rows is not None:
        print(f"Wrote external validation to {validation_path}")
        print_external_validation_summary(validation_rows)
    if not args.no_charts:
        print(f"Wrote charts to {chart_dir}")
    print_latest_category_growth_summary(category_rows)
    _write_run_manifest(args, outdir, trade_path, all_records, index_rows)
    return 0


def fetch_kcs_records(args: argparse.Namespace):
    service_key = (
        args.service_key
        or os.environ.get("DATA_GO_KR_SERVICE_KEY")
        or os.environ.get("KCS_SERVICE_KEY")
    )
    if not service_key:
        raise SystemExit("Missing service key. Set DATA_GO_KR_SERVICE_KEY or pass --service-key.")
    hs_codes = args.hs or DEFAULT_HS_CODES
    root = Path(args.outdir) if hasattr(args, "outdir") else Path(args.out).parent
    args.snapshot_dir = root / "raw" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8])
    client = KCSClient(
        service_key=service_key,
        endpoint=args.endpoint,
        service_key_encoded=args.encoded_key,
        snapshot_dir=args.snapshot_dir,
    )
    start_yymm = month_to_yymm(args.start)
    availability_hs_codes = hs_codes if args.hs else ["854232"]
    end_yymm = resolve_end_yymm(
        args.end,
        client,
        availability_hs_codes,
        start_yymm,
    )
    if start_yymm > end_yymm:
        raise SystemExit(
            f"Start month {start_yymm} must not be after end month {end_yymm}."
        )
    if str(args.end).strip().lower() == "latest":
        print(f"Resolved latest available KCS month: {end_yymm}")
    return client.fetch_many(start_yymm, end_yymm, hs_codes)


def parse_categories(args: argparse.Namespace):
    try:
        return parse_memory_categories(getattr(args, "category", []))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def build_core_memory_index(unit_rows, categories):
    core_category = next(
        (category for category in categories if category.key == CORE_CATEGORY_KEY),
        None,
    )
    if core_category is None:
        raise SystemExit(
            f"Missing required core category {CORE_CATEGORY_KEY!r}."
        )
    core_rows = [
        row
        for row in unit_rows
        if matches_category(row.get("hs_code"), core_category)
    ]
    return build_memory_index(core_rows)


def resolve_end_yymm(
    end: str,
    client: KCSClient,
    hs_codes: list[str],
    start_yymm: str,
) -> str:
    if str(end).strip().lower() != "latest":
        return month_to_yymm(end)
    return client.find_latest_available_month(hs_codes, start_month=start_yymm)


def print_latest_category_growth_summary(category_rows: list[dict[str, object]]) -> None:
    for line in format_latest_category_growth_lines(category_rows):
        print(line)


def format_latest_category_growth_lines(
    category_rows: list[dict[str, object]],
    month_count: int = 2,
) -> list[str]:
    rows_by_key = {
        (str(row.get("month")), str(row.get("category"))): row
        for row in category_rows
    }
    labels_by_category = {
        str(row.get("category")): str(row.get("category_label") or row.get("category"))
        for row in category_rows
        if row.get("category")
    }
    months = sorted(
        {
            str(row.get("month"))
            for row in category_rows
            if str(row.get("category")) in CATEGORY_GROWTH_SUMMARY_CATEGORIES
            and row.get("month")
        }
    )
    if not months:
        return []
    lines = ["Latest semiconductor-memory unit value growth:"]
    for month in months[-month_count:]:
        lines.append(f"  {month}:")
        for category in CATEGORY_GROWTH_SUMMARY_CATEGORIES:
            label = labels_by_category.get(category, category)
            row = rows_by_key.get((month, category), {})
            lines.append(
                f"    {label}: "
                f"YoY {_format_pct(row.get('unit_price_yoy_pct'))}, "
                f"MoM {_format_pct(row.get('unit_price_mom_1m_pct'))}"
            )
    return lines


def print_external_validation_summary(rows: list[dict[str, object]]) -> None:
    if not rows:
        print("External validation: no overlapping observations.")
        return
    print("External validation:")
    for row in rows:
        print(
            f"  {row.get('benchmark_label') or row.get('benchmark_key')}: "
            f"{row.get('validation_status')} (n={row.get('sample_count')})"
        )


def _build_requested_validation(
    args: argparse.Namespace,
    category_rows: list[dict[str, object]],
) -> list[dict[str, object]] | None:
    benchmark_path = getattr(args, "external_benchmark", None)
    if not benchmark_path:
        return None
    return build_external_validation(
        category_rows,
        _read_generic_csv(benchmark_path),
    )


def _format_pct(value: object) -> str:
    number = parse_number(value)
    if number is None:
        return "N/A"
    return f"{number:+.2f}%"


def _read_generic_csv(path: str | Path) -> list[dict[str, str]]:
    from .utils import read_csv_rows

    return read_csv_rows(path)


if __name__ == "__main__":
    raise SystemExit(main())
